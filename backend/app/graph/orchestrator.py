"""
LangGraph Orchestration Graph.
Haiku 4.5 acts as PM orchestrator, dynamically selecting models for each stage.
"""
import json
import asyncio
from typing import TypedDict, Optional, Literal
from datetime import datetime

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.redis_manager import RedisManager, async_redis
import uuid
from app.services.model_pool import model_pool, ModelCallError, ModelResponse
from app.models.models import (
    Project, Task, CostLog, ActivityLog, ProjectStatus, TaskStatus,
    ModelType, WorkerType,
)
from app.graph.prompts import (
    get_pm_system_prompt,
    STAGE_ANALYZE_SPEC,
    STAGE_DECOMPOSE_TASKS,
    STAGE_GENERATE_INSTRUCTION,
    STAGE_REVIEW_RESULT,
    STAGE_SELECT_FALLBACK,
)


# ──────────────────────────────────────
# State Definition
# ──────────────────────────────────────
class ProjectState(TypedDict):
    project_id: int
    stage: str  # analyze | decompose | instruct | dispatch | review | fallback | complete
    spec_document: str
    analysis: Optional[dict]
    tasks: Optional[list]
    current_task_id: Optional[int]
    current_task_result: Optional[str]
    error: Optional[str]
    fallback_count: int


# ──────────────────────────────────────
# Helper: save cost log
# ──────────────────────────────────────
def _log_cost(db: Session, project_id: int, task_id: int, resp: ModelResponse, stage: str):
    log = CostLog(
        project_id=project_id,
        task_id=task_id,
        model=resp.model,
        stage=stage,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        cost_usd=resp.cost_usd,
    )
    db.add(log)
    db.commit()
    # Check daily budget threshold asynchronously (fire and forget)
    import asyncio
    try:
        asyncio.get_running_loop().create_task(_check_daily_budget_alert())
    except RuntimeError:
        pass  # No running loop (e.g. sync test context)


# Fallback model chain: if model[i] fails, suggest model[i+1]
FALLBACK_MODEL_CHAIN = ["haiku", "gpt_4o_mini", "deepseek_v3", "deepseek_v4", "gpt_4o"]
CONFIRMATION_TIMEOUT_SECS = 300  # 5 minutes


async def _request_model_switch_confirmation(
    project_id: int,
    task_id: Optional[int],
    current_model: str,
    suggested_model: str,
    reason: str,
    stage: str,
) -> tuple[bool, str]:
    """Publish a confirmation request and wait for user response via dashboard.
    Returns (approved, model_to_use).
    Times out after CONFIRMATION_TIMEOUT_SECS and denies."""
    conf_id = str(uuid.uuid4())[:8]

    data = {
        "id": conf_id,
        "project_id": project_id,
        "task_id": task_id,
        "current_model": current_model,
        "suggested_model": suggested_model,
        "reason": reason[:500],
        "stage": stage,
        "created_at": datetime.utcnow().isoformat(),
    }

    await async_redis.hset("retrix:confirmations", conf_id, json.dumps(data))
    await RedisManager.publish_event(
        RedisManager.CHANNEL_CONFIRMATION,
        "confirmation_request",
        data,
    )
    await _log_activity(
        "pm", "orchestrator",
        f"Waiting for model switch confirmation: {current_model} → {suggested_model}",
        {"reason": reason[:200], "stage": stage},
        project_id, task_id,
    )

    response_key = f"retrix:confirmation:{conf_id}:response"
    for _ in range(CONFIRMATION_TIMEOUT_SECS):
        response = await async_redis.get(response_key)
        if response:
            await async_redis.hdel("retrix:confirmations", conf_id)
            await async_redis.delete(response_key)
            if response.startswith("approve:"):
                chosen = response.split(":", 1)[1]
                return True, chosen
            return False, current_model
        await asyncio.sleep(1)

    # Timed out → deny
    await async_redis.hdel("retrix:confirmations", conf_id)
    await RedisManager.publish_alert(
        "warning",
        f"Model switch confirmation timed out — task will be held",
        {"conf_id": conf_id, "project_id": project_id, "stage": stage},
    )
    return False, current_model


async def _call_with_confirmation(
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    project_id: int,
    task_id: Optional[int],
    stage: str,
    temperature: float = 0.3,
) -> "ModelResponse":
    """Call model; on failure ask user whether to switch to a fallback model."""
    try:
        return await model_pool.call(
            model, system_prompt, user_prompt,
            temperature=temperature, max_tokens=max_tokens,
        )
    except ModelCallError as e:
        idx = FALLBACK_MODEL_CHAIN.index(model) if model in FALLBACK_MODEL_CHAIN else -1
        suggested = (
            FALLBACK_MODEL_CHAIN[idx + 1]
            if idx + 1 < len(FALLBACK_MODEL_CHAIN)
            else FALLBACK_MODEL_CHAIN[-1]
        )

        approved, chosen_model = await _request_model_switch_confirmation(
            project_id, task_id, model, suggested, str(e), stage
        )

        if approved:
            await _log_activity(
                "pm", "orchestrator",
                f"Model switched: {model} → {chosen_model} (user approved)",
                None, project_id, task_id,
            )
            return await model_pool.call(
                chosen_model, system_prompt, user_prompt,
                temperature=temperature, max_tokens=max_tokens,
            )
        else:
            await _log_activity(
                "pm", "orchestrator",
                f"Model switch denied by user — task will be held",
                {"failed_model": model}, project_id, task_id,
            )
            raise


async def _check_daily_budget_alert():
    """Publish a warning alert if daily costs have crossed 80% of the daily budget."""
    try:
        from app.core.config import get_settings as _get_settings
        from app.core.database import SessionLocal as _SL
        _s = _get_settings()
        _db = _SL()
        try:
            from app.models.models import SystemSetting
            row = _db.query(SystemSetting).filter(SystemSetting.key == "daily_budget_limit").first()
            daily_budget = float(row.value) if row else _s.daily_budget_limit
        finally:
            _db.close()

        if not daily_budget or daily_budget <= 0:
            return

        costs = await RedisManager.get_today_costs()
        total_today = costs.get("total", 0.0)

        threshold = daily_budget * 0.8
        # Use a Redis flag to avoid spamming the same alert repeatedly
        already_alerted = await async_redis.get("retrix:daily_budget_alert_sent")
        if total_today >= threshold and not already_alerted:
            await async_redis.setex("retrix:daily_budget_alert_sent", 3600, "1")
            await RedisManager.publish_alert(
                "warning",
                f"Daily spend ${total_today:.2f} has reached 80% of the ${daily_budget:.2f} daily budget",
                {"total_today": total_today, "daily_budget": daily_budget, "threshold_pct": 80},
            )
    except Exception as e:
        print(f"[DAILY BUDGET ALERT] {e}")


async def _log_activity(actor_type: str, actor_name: str, action: str,
                        detail=None, project_id=None, task_id=None):
    """Log an activity entry to DB and publish via Redis."""
    db = SessionLocal()
    try:
        log = ActivityLog(
            actor_type=actor_type,
            actor_name=actor_name,
            action=action,
            detail=detail,
            project_id=project_id,
            task_id=task_id,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        print(f"[ACTIVITY LOG ERROR] {e}")
    finally:
        db.close()
    try:
        await RedisManager.publish_activity(actor_type, actor_name, action, detail, project_id, task_id)
    except Exception:
        pass


async def _dispatch_task(project_id: int, task_id: int, workspace: str):
    """Dispatch a single task to its assigned worker and update status."""
    from app.services.worker_executor import execute_worker_task

    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if not task:
            return
        worker_type = task.assigned_worker.value if hasattr(task.assigned_worker, "value") else (task.assigned_worker or "claude_code")
        instruction = task.instruction or task.description or task.title
        task_title = task.title
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()

    await RedisManager.publish_task_update(project_id, task_id, {"status": "in_progress", "worker": worker_type})
    await RedisManager.set_worker_status(worker_type, {"task_id": task_id, "task_title": task_title, "status": "working"})
    await _log_activity("worker", worker_type, f"Started task: {task_title}", None, project_id, task_id)

    result = await execute_worker_task(
        task_id=task_id,
        task_title=task_title,
        worker_type=worker_type,
        instruction=instruction,
        workspace=workspace,
    )

    task_status_val = None
    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if not task:
            return
        task.result = (result.output or "")[:10000]
        if result.success:
            task.status = TaskStatus.REVIEW
            task.completed_at = datetime.utcnow()
        else:
            task.retry_count = (task.retry_count or 0) + 1
            task.status = TaskStatus.FAILED
            task.error_message = (result.error or "")[:2000]
        task_status_val = task.status.value
        db.commit()
    finally:
        db.close()

    await RedisManager.publish_task_update(
        project_id, task_id,
        {"status": task_status_val, "worker": worker_type, "branch": result.branch}
    )
    await RedisManager.set_worker_status(worker_type, {"status": "idle"})
    action = f"Task {'completed' if result.success else 'failed'}: {task_title}"
    await _log_activity("worker", worker_type, action, {"exit_code": result.exit_code}, project_id, task_id)


async def dispatch_single_task(task_id: int):
    """Entry point for retry — fetch project workspace then dispatch."""
    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if not task:
            return
        project = db.query(Project).get(task.project_id)
        if not project:
            return
        project_id = project.id
        workspace = project.workspace_path or f"/tmp/retrix/{project_id}"
    finally:
        db.close()
    await _dispatch_task(project_id, task_id, workspace)


def _parse_json_response(content: str) -> dict:
    """Extract JSON from model response, handling markdown fences."""
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    return json.loads(content)


# ──────────────────────────────────────
# Node: Haiku selects model for stage
# ──────────────────────────────────────
async def haiku_select_model(stage: str, context: str) -> str:
    """Haiku decides which model to use for a given stage."""
    prompt = f"""Given this stage and context, select the best model from the pool.
Stage: {stage}
Context length: {len(context)} chars
Context preview: {context[:500]}...

Models: haiku, deepseek_v3, deepseek_v4, gpt_4o_mini, gpt_4o, minimax

Rules:
- Long documents (>20K chars) → deepseek_v3 or deepseek_v4
- Complex reasoning → deepseek_v4
- Simple/repetitive → gpt_4o_mini or minimax
- Critical decisions → gpt_4o (use sparingly)
- Quick routing → haiku

Respond with ONLY the model name, nothing else."""

    resp = await model_pool.call(
        model="haiku",
        system_prompt=get_pm_system_prompt(),
        user_prompt=prompt,
        max_tokens=50,
    )
    model_name = resp.content.strip().lower().replace("-", "_").replace(" ", "")
    valid = {"haiku", "deepseek_v3", "deepseek_v4", "gpt_4o_mini", "gpt_4o", "minimax"}
    return model_name if model_name in valid else "haiku"


# ──────────────────────────────────────
# Node: Analyze Spec
# ──────────────────────────────────────
async def analyze_spec(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        project = db.query(Project).get(state["project_id"])
        project.status = ProjectStatus.ANALYZING
        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "analyzing", "message": "Analyzing spec document..."}
        )

        # Haiku selects which model should analyze the spec
        selected_model = await haiku_select_model("analyze_spec", state["spec_document"])

        resp = await _call_with_confirmation(
            model=selected_model,
            system_prompt=get_pm_system_prompt(),
            user_prompt=STAGE_ANALYZE_SPEC + "\n\nSpec Document:\n" + state["spec_document"],
            max_tokens=4096,
            project_id=state["project_id"],
            task_id=None,
            stage="analyze_spec",
        )

        _log_cost(db, project.id, None, resp, "analysis")

        analysis = _parse_json_response(resp.content)
        project.analysis_result = analysis
        pt_val = analysis.get("project_type")
        if pt_val:
            from app.models.models import ProjectType
            try:
                project.project_type = ProjectType(pt_val)
            except ValueError:
                pass  # keep existing value if unknown
        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "analyzed", "analysis": analysis, "model_used": selected_model}
        )
        await _log_activity("pm", selected_model, "Spec analyzed", {"project_type": pt_val}, project.id)

        return {**state, "stage": "decompose", "analysis": analysis, "error": None}

    except Exception as e:
        await RedisManager.publish_alert("error", f"Spec analysis failed: {e}", {"project_id": state["project_id"]})
        return {**state, "stage": "fallback", "error": str(e)}
    finally:
        db.close()


# ──────────────────────────────────────
# Node: Decompose Tasks
# ──────────────────────────────────────
async def decompose_tasks(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        project = db.query(Project).get(state["project_id"])
        project.status = ProjectStatus.PLANNING
        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "planning", "message": "Decomposing into tasks..."}
        )

        context = json.dumps(state["analysis"], ensure_ascii=False)
        selected_model = await haiku_select_model("decompose_tasks", context)

        resp = await _call_with_confirmation(
            model=selected_model,
            system_prompt=get_pm_system_prompt(),
            user_prompt=STAGE_DECOMPOSE_TASKS + f"\n\nProject Analysis:\n{context}",
            max_tokens=8192,
            project_id=state["project_id"],
            task_id=None,
            stage="decompose_tasks",
        )

        _log_cost(db, project.id, None, resp, "decompose")

        task_plan = _parse_json_response(resp.content)
        project.plan = task_plan

        # Create Task records in DB
        tasks_data = task_plan.get("tasks", [])
        for i, t in enumerate(tasks_data):
            task = Task(
                project_id=project.id,
                title=t["title"],
                description=t.get("description", ""),
                priority=t.get("priority", 5),
                order=i,
                dependencies=t.get("dependencies", []),
                assigned_worker=t.get("worker"),
                assigned_model=t.get("instruction_model"),
            )
            db.add(task)

        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "planned", "task_count": len(tasks_data), "model_used": selected_model}
        )
        await _log_activity("pm", selected_model, f"Decomposed into {len(tasks_data)} tasks", None, project.id)

        return {**state, "stage": "instruct", "tasks": tasks_data, "error": None}

    except Exception as e:
        await RedisManager.publish_alert("error", f"Task decomposition failed: {e}", {"project_id": state["project_id"]})
        return {**state, "stage": "fallback", "error": str(e)}
    finally:
        db.close()


# ──────────────────────────────────────
# Node: Generate Worker Instructions
# ──────────────────────────────────────
async def generate_instructions(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        project = db.query(Project).get(state["project_id"])
        project.status = ProjectStatus.IN_PROGRESS
        db.commit()
        budget_limit = project.budget_limit

        tasks = db.query(Task).filter(
            Task.project_id == project.id,
            Task.status == TaskStatus.PENDING,
        ).order_by(Task.order).all()

        project_context = json.dumps(state["analysis"], ensure_ascii=False)

        for task in tasks:
            # Budget check before each instruction call
            if budget_limit:
                project = db.query(Project).get(state["project_id"])
                if project.total_cost >= budget_limit:
                    project.status = ProjectStatus.PAUSED
                    db.commit()
                    await RedisManager.publish_project_update(
                        state["project_id"], {"status": "paused", "message": "Budget limit reached during planning"}
                    )
                    await RedisManager.publish_alert(
                        "critical",
                        f"Project paused: budget limit ${budget_limit:.2f} reached",
                        {"project_id": state["project_id"], "total_cost": project.total_cost},
                    )
                    return {**state, "stage": "dispatch", "error": None}
            # Haiku selects model for instruction generation
            selected_model = await haiku_select_model(
                "generate_instruction",
                f"Task: {task.title}\nComplexity hint: {task.description[:200]}"
            )

            prompt = STAGE_GENERATE_INSTRUCTION.format(
                task_title=task.title,
                task_description=task.description,
                worker_type=task.assigned_worker,
                project_context=project_context[:2000],
            )

            resp = await _call_with_confirmation(
                model=selected_model,
                system_prompt=get_pm_system_prompt(),
                user_prompt=prompt,
                max_tokens=4096,
                project_id=state["project_id"],
                task_id=task.id,
                stage="generate_instruction",
            )

            _log_cost(db, project.id, task.id, resp, "instruction")

            task.instruction = resp.content
            task.status = TaskStatus.ASSIGNED
            db.commit()

            await RedisManager.publish_task_update(
                project.id, task.id,
                {"status": "assigned", "worker": task.assigned_worker, "model_used": selected_model}
            )
            await _log_activity("pm", selected_model, f"Instruction generated: {task.title}", None, project.id, task.id)

        return {**state, "stage": "dispatch", "error": None}

    except Exception as e:
        await RedisManager.publish_alert("error", f"Instruction generation failed: {e}", {"project_id": state["project_id"]})
        return {**state, "stage": "fallback", "error": str(e)}
    finally:
        db.close()


# ──────────────────────────────────────
# Node: Dispatch to Workers
# ──────────────────────────────────────
async def dispatch_workers(state: ProjectState) -> ProjectState:
    """Dispatch ASSIGNED tasks to workers using dependency-aware parallel phases."""
    from app.services.worker_executor import resolve_execution_phases

    project_id = state["project_id"]

    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        workspace = project.workspace_path or f"/tmp/retrix/{project_id}"
        budget_limit = project.budget_limit
        tasks = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.ASSIGNED,
        ).order_by(Task.order).all()

        task_dicts = [
            {"id": t.id, "dependencies": t.dependencies or []}
            for t in tasks
        ]
    finally:
        db.close()

    if not task_dicts:
        return {**state, "stage": "review", "error": None}

    await _log_activity("pm", "orchestrator", f"Dispatching {len(task_dicts)} tasks", None, project_id)

    try:
        phases = resolve_execution_phases(task_dicts)
    except Exception as e:
        phases = [[t] for t in task_dicts]

    try:
        for phase in phases:
            # Check pause / budget before each phase
            db = SessionLocal()
            try:
                project = db.query(Project).get(project_id)
                if project.status == ProjectStatus.PAUSED:
                    await _log_activity("pm", "orchestrator", "Dispatch paused by user", None, project_id)
                    return {**state, "stage": "review", "error": None}
                if budget_limit and project.total_cost >= budget_limit:
                    project.status = ProjectStatus.PAUSED
                    db.commit()
                    await RedisManager.publish_project_update(
                        project_id, {"status": "paused", "message": "Budget limit reached"}
                    )
                    await RedisManager.publish_alert(
                        "critical",
                        f"Project paused: budget limit ${budget_limit:.2f} reached",
                        {"project_id": project_id, "total_cost": project.total_cost},
                    )
                    await _log_activity("pm", "orchestrator", "Project paused: budget limit reached",
                                        {"budget_limit": budget_limit, "total_cost": project.total_cost}, project_id)
                    return {**state, "stage": "review", "error": None}
            finally:
                db.close()

            await asyncio.gather(*[
                _dispatch_task(project_id, t["id"], workspace)
                for t in phase
            ])
    except Exception as e:
        return {**state, "stage": "fallback", "error": str(e)}

    return {**state, "stage": "review", "error": None}


# ──────────────────────────────────────
# Node: Review Results
# ──────────────────────────────────────
async def review_results(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        tasks = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.REVIEW,
        ).all()

        all_approved = True
        for task in tasks:
            resp = await _call_with_confirmation(
                model="haiku",
                system_prompt=get_pm_system_prompt(),
                user_prompt=STAGE_REVIEW_RESULT.format(
                    task_title=task.title,
                    task_description=task.description,
                    worker_result=task.result[:3000],
                ),
                max_tokens=2048,
                project_id=state["project_id"],
                task_id=task.id,
                stage="review",
            )

            _log_cost(db, state["project_id"], task.id, resp, "review")

            review = _parse_json_response(resp.content)

            if review.get("approved"):
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
            else:
                all_approved = False
                task.status = TaskStatus.FAILED
                task.error_message = json.dumps(review.get("issues", []))

            db.commit()

            await RedisManager.publish_task_update(
                state["project_id"], task.id,
                {"status": task.status.value, "review": review}
            )

        # Update project progress and total cost
        from sqlalchemy import func
        project = db.query(Project).get(state["project_id"])
        total = db.query(Task).filter(Task.project_id == project.id).count()
        completed = db.query(Task).filter(
            Task.project_id == project.id,
            Task.status == TaskStatus.COMPLETED,
        ).count()
        project.progress = (completed / total * 100) if total > 0 else 0
        total_cost = db.query(func.sum(CostLog.cost_usd)).filter(
            CostLog.project_id == project.id
        ).scalar()
        project.total_cost = float(total_cost or 0)

        if all_approved and project.progress >= 100:
            project.status = ProjectStatus.COMPLETED
            stage = "complete"
        elif not all_approved:
            stage = "fallback"
        else:
            stage = "dispatch"  # More tasks to process

        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": project.status.value, "progress": project.progress}
        )

        if stage == "complete":
            await _log_activity("pm", "orchestrator", f"Project completed: {project.name}",
                                {"progress": project.progress, "total_cost": project.total_cost}, project.id)
        elif stage == "fallback":
            await _log_activity("pm", "orchestrator", f"Project has failed tasks: {project.name}",
                                {"progress": project.progress}, project.id)

        return {**state, "stage": stage, "error": None}

    except Exception as e:
        return {**state, "stage": "fallback", "error": str(e)}
    finally:
        db.close()


# ──────────────────────────────────────
# Node: Fallback Handler
# ──────────────────────────────────────
async def handle_fallback(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        failed_tasks = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.FAILED,
        ).all()

        for task in failed_tasks:
            if task.retry_count >= task.max_retries:
                # 3회 실패 → HOLD + 대시보드 알림
                task.status = TaskStatus.HELD
                db.commit()

                await RedisManager.publish_alert(
                    "critical",
                    f"Task held after {task.max_retries} failures: {task.title}",
                    {"project_id": state["project_id"], "task_id": task.id},
                )
                continue

            # Haiku decides fallback strategy
            resp = await _call_with_confirmation(
                model="haiku",
                system_prompt=get_pm_system_prompt(),
                user_prompt=STAGE_SELECT_FALLBACK.format(
                    failed_worker=task.assigned_worker,
                    error_message=task.error_message or state.get("error", "Unknown"),
                    retry_count=task.retry_count,
                    max_retries=task.max_retries,
                    task_title=task.title,
                ),
                max_tokens=1024,
                project_id=state["project_id"],
                task_id=task.id,
                stage="fallback",
            )

            _log_cost(db, state["project_id"], task.id, resp, "fallback")

            decision = _parse_json_response(resp.content)
            action = decision.get("action", "hold")

            # Log fallback attempt
            history = task.fallback_history or []
            history.append({
                "attempt": task.retry_count + 1,
                "action": action,
                "from_worker": task.assigned_worker,
                "to_worker": decision.get("target_worker"),
                "reason": decision.get("reason"),
                "timestamp": datetime.utcnow().isoformat(),
            })
            task.fallback_history = history
            task.retry_count += 1

            if action == "retry":
                task.status = TaskStatus.ASSIGNED
                task.error_message = None
            elif action == "fallback":
                task.assigned_worker = decision.get("target_worker", task.assigned_worker)
                task.status = TaskStatus.ASSIGNED
                task.error_message = None
                if decision.get("modified_instruction"):
                    task.instruction = decision["modified_instruction"]
            elif action == "escalate":
                task.status = TaskStatus.ASSIGNED
                if decision.get("modified_instruction"):
                    task.instruction = decision["modified_instruction"]
            else:  # hold
                task.status = TaskStatus.HELD
                await RedisManager.publish_alert(
                    "warning",
                    f"Task needs human intervention: {task.title}",
                    {"project_id": state["project_id"], "task_id": task.id, "reason": decision.get("reason")},
                )

            db.commit()

            await RedisManager.publish_task_update(
                state["project_id"], task.id,
                {"status": task.status.value, "fallback": decision}
            )

        # Check if any tasks still need processing
        pending = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status.in_([TaskStatus.ASSIGNED, TaskStatus.PENDING]),
        ).count()

        next_stage = "dispatch" if pending > 0 else "complete"
        return {**state, "stage": next_stage, "fallback_count": state.get("fallback_count", 0) + 1, "error": None}

    except Exception as e:
        await RedisManager.publish_alert("critical", f"Fallback handler crashed: {e}")
        return {**state, "stage": "complete", "error": str(e)}
    finally:
        db.close()


# ──────────────────────────────────────
# Router: decide next node
# ──────────────────────────────────────
def route_next(state: ProjectState) -> str:
    stage = state.get("stage", "analyze")
    if stage == "analyze":
        return "analyze"
    elif stage == "decompose":
        return "decompose"
    elif stage == "instruct":
        return "instruct"
    elif stage == "dispatch":
        return "dispatch"
    elif stage == "review":
        return "review"
    elif stage == "fallback":
        return "fallback"
    else:
        return "end"


# ──────────────────────────────────────
# Build Graph
# ──────────────────────────────────────
def build_orchestrator_graph() -> StateGraph:
    graph = StateGraph(ProjectState)

    # Add nodes
    graph.add_node("analyze", analyze_spec)
    graph.add_node("decompose", decompose_tasks)
    graph.add_node("instruct", generate_instructions)
    graph.add_node("dispatch", dispatch_workers)
    graph.add_node("review", review_results)
    graph.add_node("fallback", handle_fallback)

    # Entry point
    graph.set_conditional_entry_point(route_next)

    # Edges
    graph.add_conditional_edges("analyze", route_next)
    graph.add_conditional_edges("decompose", route_next)
    graph.add_conditional_edges("instruct", route_next)
    graph.add_conditional_edges("dispatch", route_next)
    graph.add_conditional_edges("review", route_next)
    graph.add_conditional_edges("fallback", route_next)

    return graph.compile()


# Singleton graph instance
orchestrator = build_orchestrator_graph()


async def run_project(project_id: int, spec_document: str):
    """Entry point: run the full orchestration pipeline for a project."""
    initial_state: ProjectState = {
        "project_id": project_id,
        "stage": "analyze",
        "spec_document": spec_document,
        "analysis": None,
        "tasks": None,
        "current_task_id": None,
        "current_task_result": None,
        "error": None,
        "fallback_count": 0,
    }

    result = await orchestrator.ainvoke(initial_state)
    return result


async def resume_project_run(project_id: int):
    """Resume an existing project without re-analyzing or re-decomposing.

    Determines the correct resume stage from existing task statuses:
    - ASSIGNED tasks exist → skip to dispatch (instructions already generated)
    - Only PENDING tasks exist → skip to instruct (tasks exist but need instructions)
    - Neither → nothing to do, mark completed if all tasks are done
    """
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project:
            return
        spec_document = project.spec_document or ""
        analysis = project.analysis_result or {}

        assigned_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.ASSIGNED,
        ).count()

        pending_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.PENDING,
        ).count()

        in_progress_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.IN_PROGRESS,
        ).count()

        if assigned_count > 0 or in_progress_count > 0:
            resume_stage = "dispatch"
        elif pending_count > 0:
            resume_stage = "instruct"
        else:
            # All tasks are completed/failed/held — go to review to update progress
            resume_stage = "review"

    finally:
        db.close()

    await _log_activity("pm", "orchestrator", f"Resuming project from stage: {resume_stage}", None, project_id)

    initial_state: ProjectState = {
        "project_id": project_id,
        "stage": resume_stage,
        "spec_document": spec_document,
        "analysis": analysis,
        "tasks": None,
        "current_task_id": None,
        "current_task_result": None,
        "error": None,
        "fallback_count": 0,
    }

    result = await orchestrator.ainvoke(initial_state)
    return result
