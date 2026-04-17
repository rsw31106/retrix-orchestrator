"""
LangGraph Orchestration Graph.
Haiku 4.5 acts as PM orchestrator, dynamically selecting models for each stage.
"""
import json
import asyncio
import logging
from typing import TypedDict, Optional, Literal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import SessionLocal
from app.core.redis_manager import RedisManager, async_redis
import uuid
from app.services.model_pool import model_pool, ModelCallError, ModelResponse
from app.services.notifications import notify_project_completed, notify_project_failed, notify_budget_alert
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
    STAGE_COMPLETION_REPORT,
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


async def _generate_completion_report(project_id: int, db: Session):
    """Generate a PM completion report summarising what was done and next steps."""
    try:
        project = db.query(Project).get(project_id)
        if not project:
            return

        completed_tasks = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.COMPLETED,
        ).order_by(Task.order).all()

        task_lines = "\n".join(
            f"- [{i+1}] {t.title}: {(t.description or '')[:200]}"
            for i, t in enumerate(completed_tasks)
        )

        resp = await model_pool.call(
            model="haiku",
            system_prompt=get_pm_system_prompt(project_id=project_id),
            user_prompt=STAGE_COMPLETION_REPORT.format(
                project_name=project.name,
                completed_tasks=task_lines or "(no tasks recorded)",
                total_cost=project.total_cost or 0.0,
                progress=project.progress or 100.0,
            ),
            temperature=0.4,
            max_tokens=2048,
        )

        _log_cost(db, project_id, None, resp, "completion_report")

        try:
            report = _parse_json_response(resp.content)
            if isinstance(report, dict):
                project.completion_report = report
                db.commit()
                await RedisManager.publish_project_update(
                    project_id, {"completion_report": report}
                )
                await _log_activity("pm", "orchestrator", "Completion report generated", None, project_id)
        except ValueError:
            logger.warning(f"[completion_report] JSON parse failed for project {project_id}")
    except Exception as e:
        logger.error(f"[completion_report] Failed for project {project_id}: {e}")


# Fallback model chain: if model[i] fails, suggest model[i+1]
FALLBACK_MODEL_CHAIN = ["haiku", "gpt_4o_mini", "deepseek_v3", "deepseek_v4", "gpt_4o"]
CONFIRMATION_TIMEOUT_SECS = 300  # 5 minutes for model-switch confirmations


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


async def _request_analysis_approval(project_id: int, analysis: dict) -> bool:
    """Publish an analysis review request and wait indefinitely for user approval.
    Returns True if approved, False if denied."""
    conf_id = str(uuid.uuid4())[:8]

    data = {
        "id": conf_id,
        "confirmation_type": "analysis_review",
        "project_id": project_id,
        "summary": analysis.get("summary", ""),
        "project_type": analysis.get("project_type", ""),
        "tasks_estimate": analysis.get("estimated_tasks", analysis.get("task_count", "?")),
        "key_requirements": (analysis.get("key_requirements") or analysis.get("tech_requirements") or [])[:10],
        "risks": (analysis.get("risks") or [])[:5],
        "complexity": str(analysis.get("complexity", "")),
        "tech_stack": (analysis.get("tech_stack") or analysis.get("tech_requirements") or []),
        "full_analysis": analysis,
        "feedback_history": [],
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
        "Waiting for user approval before task decomposition",
        {"summary": str(analysis.get("summary", ""))[:200]},
        project_id,
    )

    response_key = f"retrix:confirmation:{conf_id}:response"
    while True:
        response = await async_redis.get(response_key)
        if response:
            await async_redis.hdel("retrix:confirmations", conf_id)
            await async_redis.delete(response_key)
            return response.startswith("approve:")
        await asyncio.sleep(2)


async def _handle_analysis_response(project_id: int, conf_id: str, analysis: dict, approved: bool):
    """Apply the result of an analysis approval (used both inline and after server restart)."""
    db = SessionLocal()
    try:
        proj = db.query(Project).get(project_id)
        if not proj:
            return
        if approved:
            proj.analysis_result = analysis
            if proj.pause_after_analysis:
                proj.status = ProjectStatus.PAUSED
                db.commit()
                await RedisManager.publish_project_update(
                    project_id,
                    {"status": "paused", "message": "분석 완료 — PM과 대화 후 태스크 분해를 시작하세요"},
                )
                await _log_activity(
                    "pm", "orchestrator",
                    "Analysis approved — paused for PM discussion before decompose",
                    None, project_id,
                )
                await _git_setup_develop(project_id)
                await _write_analysis_docs(project_id, analysis)
                await _git_commit(project_id, "docs: add project spec and PM analysis")
                return
            db.commit()
        else:
            proj.status = ProjectStatus.PAUSED
            proj.analysis_result = None
            db.commit()
    finally:
        db.close()

    if approved:
        await _log_activity("pm", "orchestrator", "Analysis approved — proceeding to decompose", None, project_id)
        await _git_setup_develop(project_id)
        await _write_analysis_docs(project_id, analysis)
        await _git_commit(project_id, "docs: add project spec and PM analysis")
        await resume_project_run(project_id)
    else:
        await RedisManager.publish_project_update(
            project_id, {"status": "paused", "message": "Analysis rejected — edit spec and resume to re-analyze"}
        )
        await _log_activity("pm", "orchestrator", "Analysis rejected by user — project paused", None, project_id)


async def _poll_pending_analysis_approval(project_id: int, conf_id: str, analysis: dict):
    """Re-attach to a pending analysis approval after server restart.
    Polls indefinitely until the user approves or rejects."""
    logger.info(f"[restart-recovery] Resuming analysis approval wait for project {project_id} conf {conf_id}")
    response_key = f"retrix:confirmation:{conf_id}:response"
    while True:
        response = await async_redis.get(response_key)
        if response:
            await async_redis.hdel("retrix:confirmations", conf_id)
            await async_redis.delete(response_key)
            approved = response.startswith("approve:")
            await _handle_analysis_response(project_id, conf_id, analysis, approved)
            return
        await asyncio.sleep(2)


async def resume_pending_analysis_approvals():
    """Called on server startup: find any analysis_review confirmations left in Redis
    and re-attach polling tasks so approvals are processed even after a restart."""
    try:
        raw_all = await async_redis.hgetall("retrix:confirmations")
    except Exception as e:
        logger.error(f"[restart-recovery] Failed to read pending confirmations: {e}")
        return

    for conf_id, raw in raw_all.items():
        try:
            conf_data = json.loads(raw)
        except Exception:
            continue
        if conf_data.get("confirmation_type") != "analysis_review":
            continue
        project_id = conf_data.get("project_id")
        analysis = conf_data.get("full_analysis") or {}
        if not project_id:
            continue
        asyncio.create_task(
            _poll_pending_analysis_approval(project_id, conf_id, analysis),
            name=f"analysis-approval-{conf_id}",
        )
        logger.info(f"[restart-recovery] Re-attached analysis approval poller for project {project_id} conf {conf_id}")


async def revise_analysis_with_feedback(
    conf_id: str,
    project_id: int,
    current_analysis: dict,
    user_message: str,
    feedback_history: list,
) -> tuple[str, dict]:
    """
    PM responds to user message in natural language AND optionally revises the analysis.
    Returns (pm_reply: str, revised_analysis: dict).
    """
    from app.core.database import SessionLocal as _SL
    from app.models.models import Project as _Project

    db = _SL()
    try:
        project = db.query(_Project).get(project_id)
        spec_document = project.spec_document or ""
    finally:
        db.close()

    history_text = ""
    for entry in feedback_history:
        role = "User" if entry["role"] == "user" else "PM"
        history_text += f"\n{role}: {entry['content']}"

    prompt = f"""You are the PM who analyzed a project specification. The user is reviewing your analysis and may ask questions or request changes.

Project Spec:
{spec_document}

Your Current Analysis:
{json.dumps(current_analysis, ensure_ascii=False, indent=2)}

Conversation so far:{history_text}

User: {user_message}

Respond in this exact JSON format (no markdown, no code fences):
{{
  "reply": "<your natural language response to the user — answer their question or confirm the change you made>",
  "analysis": {{ <the full updated analysis JSON, same schema as Current Analysis above. If no changes needed, return the current analysis unchanged> }}
}}

Rules:
- "reply" must be a helpful natural language message in the same language as the user's message
- If the user asks a question, answer it clearly in "reply"
- If the user requests a change, confirm what you changed in "reply" and update "analysis"
- If no changes are needed, keep "analysis" identical to Current Analysis
- NEVER omit either "reply" or "analysis" from your response"""

    selected_model = await haiku_select_model("analyze_spec", spec_document, project_id=project_id)

    async def _call(model: str) -> tuple[str, dict]:
        resp = await model_pool.call(
            model=model,
            system_prompt=get_pm_system_prompt(project_id=project_id),
            user_prompt=prompt,
            max_tokens=4096,
            temperature=0.4,
        )
        parsed = _parse_json_response(resp.content)
        reply = parsed.get("reply", "")
        analysis = parsed.get("analysis", current_analysis)
        if not isinstance(analysis, dict):
            analysis = current_analysis
        return reply, analysis

    try:
        reply, revised = await _call(selected_model)
    except ValueError:
        if selected_model != "haiku":
            logger.warning(f"[revise_analysis] {selected_model} returned non-JSON, retrying with haiku")
            try:
                reply, revised = await _call("haiku")
            except ValueError:
                # haiku도 JSON 반환 실패 — raw 응답을 reply로 사용하고 analysis는 유지
                logger.warning("[revise_analysis] haiku also returned non-JSON, using raw response as reply")
                try:
                    raw_resp = await model_pool.call(
                        model="haiku",
                        system_prompt=get_pm_system_prompt(project_id=project_id),
                        user_prompt=prompt,
                        max_tokens=1024,
                        temperature=0.4,
                    )
                    reply = raw_resp.content.strip()
                except Exception:
                    reply = "분석 내용을 검토했습니다. 추가 요청사항이 있으시면 말씀해 주세요."
                revised = current_analysis
        else:
            # haiku 단독 실패 — raw 응답을 reply로 사용
            logger.warning("[revise_analysis] haiku returned non-JSON, using raw response as reply")
            try:
                raw_resp = await model_pool.call(
                    model="haiku",
                    system_prompt=get_pm_system_prompt(project_id=project_id),
                    user_prompt=prompt,
                    max_tokens=1024,
                    temperature=0.4,
                )
                reply = raw_resp.content.strip()
            except Exception:
                reply = "분석 내용을 검토했습니다. 추가 요청사항이 있으시면 말씀해 주세요."
            revised = current_analysis

    # Update Redis confirmation data with revised analysis
    raw = await async_redis.hget("retrix:confirmations", conf_id)
    if raw:
        conf_data = json.loads(raw)
        conf_data.update({
            "summary": revised.get("summary", revised.get("features", [""])[0] if revised.get("features") else ""),
            "project_type": revised.get("project_type", conf_data.get("project_type", "")),
            "tasks_estimate": revised.get("estimated_tasks", revised.get("task_count", conf_data.get("tasks_estimate", "?"))),
            "key_requirements": (revised.get("key_requirements") or revised.get("tech_requirements") or [])[:10],
            "risks": (revised.get("risks") or [])[:5],
            "complexity": str(revised.get("complexity", conf_data.get("complexity", ""))),
            "tech_stack": (revised.get("tech_stack") or revised.get("tech_requirements") or []),
            "full_analysis": revised,
        })
        await async_redis.hset("retrix:confirmations", conf_id, json.dumps(conf_data))

    await _log_activity(
        "pm", selected_model,
        f"Analysis feedback response: {user_message[:100]}",
        None, project_id,
    )
    return reply, revised


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
            await notify_budget_alert(total_today, daily_budget)
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


async def _git_setup_develop(project_id: int):
    """Create and checkout develop branch for the project workspace (no-op if no repo)."""
    from app.services.github import github_service
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project or not project.github_repo or not project.workspace_path:
            return
        workspace = project.workspace_path
    finally:
        db.close()
    try:
        await github_service.setup_develop_branch(workspace)
        await _log_activity("pm", "orchestrator", "Git: develop branch created", None, project_id)
    except Exception as e:
        logger.warning(f"[git] develop branch setup failed for project {project_id}: {e}")


async def _git_commit(project_id: int, message: str):
    """Commit and push workspace changes to develop branch (no-op if no repo)."""
    from app.services.github import github_service
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project or not project.github_repo or not project.workspace_path:
            return
        workspace = project.workspace_path
    finally:
        db.close()
    try:
        committed = await github_service.git_commit_and_push(workspace, message)
        if committed:
            await _log_activity("pm", "orchestrator", f"Git commit: {message}", None, project_id)
    except Exception as e:
        logger.warning(f"[git] commit skipped for project {project_id}: {e}")


async def _git_merge_to_main(project_id: int):
    """Merge develop into main at project completion (no-op if no repo)."""
    from app.services.github import github_service
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project or not project.github_repo or not project.workspace_path:
            return
        workspace = project.workspace_path
        name = project.name
    finally:
        db.close()
    try:
        merged = await github_service.merge_develop_to_main(workspace, name)
        if merged:
            await _log_activity("pm", "orchestrator", "Git: develop merged into main", None, project_id)
    except Exception as e:
        logger.warning(f"[git] merge to main failed for project {project_id}: {e}")


async def _write_analysis_docs(project_id: int, analysis: dict):
    """Write SPEC.md and ANALYSIS.md into the workspace docs/ folder."""
    import os
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project or not project.workspace_path:
            return
        workspace = project.workspace_path
        spec = project.spec_document or ""
    finally:
        db.close()

    docs_dir = os.path.join(workspace, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    spec_path = os.path.join(docs_dir, "SPEC.md")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(f"# Project Specification\n\n{spec}\n")

    analysis_lines = ["# PM Analysis\n"]
    if analysis.get("summary"):
        analysis_lines.append(f"## Summary\n{analysis['summary']}\n")
    if analysis.get("project_type"):
        analysis_lines.append(f"**Type:** {analysis['project_type']}  \n")
    if analysis.get("complexity"):
        analysis_lines.append(f"**Complexity:** {analysis['complexity']}  \n")
    if analysis.get("tasks_estimate") or analysis.get("estimated_tasks"):
        est = analysis.get("tasks_estimate") or analysis.get("estimated_tasks")
        analysis_lines.append(f"**Estimated tasks:** {est}  \n")
    if analysis.get("tech_stack"):
        analysis_lines.append(f"\n## Tech Stack\n" + "\n".join(f"- {t}" for t in analysis["tech_stack"]) + "\n")
    if analysis.get("key_requirements"):
        analysis_lines.append(f"\n## Key Requirements\n" + "\n".join(f"- {r}" for r in analysis["key_requirements"]) + "\n")
    if analysis.get("risks"):
        analysis_lines.append(f"\n## Risks\n" + "\n".join(f"- {r}" for r in analysis["risks"]) + "\n")

    analysis_path = os.path.join(docs_dir, "ANALYSIS.md")
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write("\n".join(analysis_lines))


async def _write_task_plan(project_id: int, tasks_data: list):
    """Write docs/TASKS.md with the decomposed task plan."""
    import os
    db = SessionLocal()
    try:
        project = db.query(Project).get(project_id)
        if not project or not project.workspace_path:
            return
        workspace = project.workspace_path
    finally:
        db.close()

    docs_dir = os.path.join(workspace, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    lines = [f"# Task Plan ({len(tasks_data)} tasks)\n"]
    for i, t in enumerate(tasks_data, 1):
        priority = t.get("priority", "")
        worker = t.get("worker", "")
        lines.append(f"## Task {i}: {t.get('title', '')}")
        if priority or worker:
            meta = []
            if priority:
                meta.append(f"priority={priority}")
            if worker:
                meta.append(f"worker={worker}")
            lines.append(f"*{', '.join(meta)}*")
        if t.get("description"):
            lines.append(f"\n{t['description']}")
        if t.get("dependencies"):
            lines.append(f"\n**Dependencies:** {t['dependencies']}")
        lines.append("")

    tasks_path = os.path.join(docs_dir, "TASKS.md")
    with open(tasks_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


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

    # Rate limit 감지 — 실패(exit_code != 0)인 경우에만 검사해 오탐 방지
    # 성공한 출력 내용에 "rate limit"이라는 단어가 있어도 무시함
    RATE_LIMIT_PHRASES = [
        "you've hit your limit", "you have hit your limit",
        "rate limit exceeded", "quota exceeded", "too many requests",
        "usage limit exceeded", "daily limit reached", "api rate limit",
    ]
    # error와 output 둘 다 검사 (limit 메시지가 output으로 오는 경우 대응)
    combined_output = ((result.error or "") + " " + (result.output or "")).lower()
    is_rate_limited = (not result.success) and any(phrase in combined_output for phrase in RATE_LIMIT_PHRASES)

    task_status_val = None
    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if not task:
            return
        task.result = (result.output or "")[:10000]
        if is_rate_limited:
            # 다음 8am KST(UTC+9)로 재시도 예약 — DB는 UTC로 저장
            KST_OFFSET = timedelta(hours=9)
            now_utc = datetime.utcnow()
            now_kst = now_utc + KST_OFFSET
            # KST 기준 다음 08:00
            retry_kst = now_kst.replace(hour=8, minute=0, second=0, microsecond=0)
            if retry_kst <= now_kst:
                retry_kst += timedelta(days=1)
            retry_at = retry_kst - KST_OFFSET  # UTC로 변환해서 DB 저장
            task.status = TaskStatus.HELD
            task.scheduled_retry_at = retry_at
            task.error_message = f"Rate limited — scheduled retry at {retry_kst.strftime('%Y-%m-%d %H:%M KST')}"
            await RedisManager.publish_alert(
                "warning",
                f"Task rate-limited, scheduled retry at {retry_kst.strftime('%H:%M KST')}: {task.title}",
                {"project_id": project_id, "task_id": task_id, "retry_at": retry_at.isoformat()},
            )
        elif result.success:
            task.status = TaskStatus.REVIEW
            task.completed_at = datetime.utcnow()
            task.scheduled_retry_at = None
        else:
            task.retry_count = (task.retry_count or 0) + 1
            task.status = TaskStatus.FAILED
            task.error_message = (result.error or "")[:2000]
        task_status_val = task.status.value
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update task {task_id} status after execution: {e}")
        db.rollback()
        # 상태 업데이트 실패 시 FAILED로 강제 설정
        try:
            db.query(Task).filter(Task.id == task_id).update({
                "status": TaskStatus.FAILED,
                "error_message": f"Status update error: {str(e)[:500]}",
            })
            db.commit()
            task_status_val = TaskStatus.FAILED.value
        except Exception:
            task_status_val = TaskStatus.FAILED.value
    finally:
        db.close()

    try:
        await RedisManager.publish_task_update(
            project_id, task_id,
            {"status": task_status_val, "worker": worker_type, "branch": result.branch}
        )
    except Exception as e:
        logger.warning(f"Redis publish failed for task {task_id}: {e}")
    try:
        await RedisManager.set_worker_status(worker_type, {"status": "idle"})
    except Exception as e:
        logger.warning(f"Redis worker status update failed for {worker_type}: {e}")
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
    """Extract JSON from model response, handling markdown fences and surrounding text."""
    content = content.strip()

    # Strip markdown code fences
    if "```" in content:
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Extract first {...} or [...] block from response
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = content.find(start_char)
        end = content.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No valid JSON found in response: {content[:200]}")


# ──────────────────────────────────────
# Node: Haiku selects model for stage
# ──────────────────────────────────────
async def haiku_select_model(stage: str, context: str, project_id: int | None = None) -> str:
    """Select the best model for a given stage. Uses minimax (flat rate) for the decision itself."""
    prompt = f"""Given this stage and context, select the best model from the pool.
Stage: {stage}
Context length: {len(context)} chars
Context preview: {context[:500]}...

Models: haiku, deepseek_v3, deepseek_v4, gpt_4o_mini, gpt_4o, minimax

Rules:
- Long documents (>20K chars) → deepseek_v3 or deepseek_v4
- Complex reasoning / architecture → deepseek_v4
- Simple task instructions → minimax (flat rate, preferred for repetitive work)
- Critical decisions or ambiguous specs → gpt_4o (sparingly)
- Moderate complexity instructions → gpt_4o_mini
- Fast routing only → haiku

Default to minimax unless the task clearly requires stronger reasoning.

Respond with ONLY the model name, nothing else."""

    resp = await model_pool.call(
        model="minimax",
        system_prompt=get_pm_system_prompt(project_id=project_id),
        user_prompt=prompt,
        max_tokens=50,
    )
    model_name = resp.content.strip().lower().replace("-", "_").replace(" ", "")
    valid = {"haiku", "deepseek_v3", "deepseek_v4", "gpt_4o_mini", "gpt_4o", "minimax"}
    return model_name if model_name in valid else "minimax"


# ──────────────────────────────────────
# Node: Analyze Spec
# ──────────────────────────────────────
async def analyze_spec(state: ProjectState) -> ProjectState:
    analysis = None
    db = SessionLocal()
    try:
        project = db.query(Project).get(state["project_id"])

        # Skip re-analysis if already done (was previously approved) — go straight to decompose
        if project.analysis_result:
            await RedisManager.publish_project_update(
                project.id, {"status": "analyzed", "analysis": project.analysis_result, "model_used": "cached"}
            )
            return {**state, "stage": "decompose", "analysis": project.analysis_result, "error": None}

        project.status = ProjectStatus.ANALYZING
        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "analyzing", "message": "Analyzing spec document..."}
        )

        # Haiku selects which model should analyze the spec
        selected_model = await haiku_select_model("analyze_spec", state["spec_document"], project_id=state["project_id"])

        _analysis_prompt = STAGE_ANALYZE_SPEC + "\n\nSpec Document:\n" + state["spec_document"]
        resp = await _call_with_confirmation(
            model=selected_model,
            system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
            user_prompt=_analysis_prompt,
            max_tokens=4096,
            project_id=state["project_id"],
            task_id=None,
            stage="analyze_spec",
        )

        _log_cost(db, project.id, None, resp, "analysis")

        # If selected model returned unparseable JSON, fall back to haiku
        try:
            analysis = _parse_json_response(resp.content)
        except ValueError:
            logger.warning(f"[analyze_spec] {selected_model} returned unparseable response, retrying with haiku. Raw: {resp.content[:300]}")
            resp = await _call_with_confirmation(
                model="haiku",
                system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
                user_prompt=_analysis_prompt,
                max_tokens=4096,
                project_id=state["project_id"],
                task_id=None,
                stage="analyze_spec",
            )
            _log_cost(db, project.id, None, resp, "analysis")
            analysis = _parse_json_response(resp.content)
        # Save analysis_result only AFTER user approves (below) — don't cache pre-approval
        pt_val = analysis.get("project_type")
        if pt_val:
            from app.models.models import ProjectType
            try:
                project.project_type = ProjectType(pt_val)
                db.commit()
            except ValueError:
                pass

        await RedisManager.publish_project_update(
            project.id, {"status": "awaiting_approval", "analysis": analysis, "model_used": selected_model}
        )
        await _log_activity("pm", selected_model, "Spec analyzed — awaiting user approval", {"project_type": pt_val}, project.id)

    except Exception as e:
        await RedisManager.publish_alert("error", f"Spec analysis failed: {e}", {"project_id": state["project_id"]})
        return {**state, "stage": "fallback", "error": str(e)}
    finally:
        db.close()

    # ── Wait for user to review and approve the analysis ──
    approved = await _request_analysis_approval(state["project_id"], analysis)

    if approved:
        # Save analysis to DB now that user approved it
        db2 = SessionLocal()
        try:
            proj2 = db2.query(Project).get(state["project_id"])
            if proj2:
                proj2.analysis_result = analysis
                # If pause_after_analysis is set, stop here for PM discussion
                if proj2.pause_after_analysis:
                    proj2.status = ProjectStatus.PAUSED
                    db2.commit()
                    await RedisManager.publish_project_update(
                        state["project_id"],
                        {"status": "paused", "message": "분석 완료 — PM과 대화 후 태스크 분해를 시작하세요"},
                    )
                    await _log_activity(
                        "pm", "orchestrator",
                        "Analysis approved — paused for PM discussion before decompose",
                        None, state["project_id"],
                    )
                    return {**state, "stage": "complete", "analysis": analysis, "error": None}
                db2.commit()
        finally:
            db2.close()
        await _log_activity("pm", "orchestrator", "Analysis approved — proceeding to decompose", None, state["project_id"])
        return {**state, "stage": "decompose", "analysis": analysis, "error": None}
    else:
        # Rejected or timed out — pause so user can edit spec and resume
        db2 = SessionLocal()
        try:
            proj2 = db2.query(Project).get(state["project_id"])
            if proj2:
                proj2.status = ProjectStatus.PAUSED
                proj2.analysis_result = None
                db2.commit()
        finally:
            db2.close()
        await RedisManager.publish_project_update(
            state["project_id"], {"status": "paused", "message": "Analysis rejected — edit spec and resume to re-analyze"}
        )
        await _log_activity("pm", "orchestrator", "Analysis rejected by user — project paused", None, state["project_id"])
        return {**state, "stage": "complete", "analysis": analysis, "error": None}


# ──────────────────────────────────────
# Node: Decompose Tasks
# ──────────────────────────────────────
async def decompose_tasks(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        # Guard: never decompose twice — if tasks already exist, skip straight to instruct
        existing = db.query(Task).filter(Task.project_id == state["project_id"]).count()
        if existing > 0:
            await RedisManager.publish_project_update(
                state["project_id"], {"message": f"Tasks already exist ({existing}), skipping decomposition"}
            )
            await _log_activity("pm", "orchestrator", f"Decompose skipped — {existing} tasks already exist", None, state["project_id"])
            return {**state, "stage": "instruct", "tasks": [], "error": None}

        project = db.query(Project).get(state["project_id"])
        project.status = ProjectStatus.PLANNING
        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "planning", "message": "Decomposing into tasks..."}
        )

        context = json.dumps(state["analysis"], ensure_ascii=False)

        # Inject pre-decompose PM discussion notes (if any)
        pm_context = ""
        if project.pm_context_notes and project.pm_context_notes.strip():
            pm_context = (
                "\n\n## 사전 PM 협의 내용 (Pre-decomposition Discussion Notes)\n"
                "아래 내용은 태스크 설계 전 사용자와 PM이 협의한 내용이다. 반드시 이를 반영하여 태스크를 설계하라.\n\n"
                + project.pm_context_notes.strip()
            )

        selected_model = await haiku_select_model("decompose_tasks", context, project_id=state["project_id"])

        _decompose_prompt = STAGE_DECOMPOSE_TASKS + f"\n\nProject Analysis:\n{context}" + pm_context
        resp = await _call_with_confirmation(
            model=selected_model,
            system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
            user_prompt=_decompose_prompt,
            max_tokens=8192,
            project_id=state["project_id"],
            task_id=None,
            stage="decompose_tasks",
        )

        _log_cost(db, project.id, None, resp, "decompose")

        try:
            task_plan = _parse_json_response(resp.content)
        except ValueError:
            logger.warning(f"[decompose_tasks] {selected_model} returned unparseable response, retrying with haiku. Raw: {resp.content[:300]}")
            resp = await _call_with_confirmation(
                model="haiku",
                system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
                user_prompt=_decompose_prompt,
                max_tokens=8192,
                project_id=state["project_id"],
                task_id=None,
                stage="decompose_tasks",
            )
            _log_cost(db, project.id, None, resp, "decompose")
            task_plan = _parse_json_response(resp.content)
        project.plan = task_plan

        # Create Task records in DB
        valid_workers = {w.value for w in WorkerType}

        tasks_data = task_plan.get("tasks", [])
        for i, t in enumerate(tasks_data):
            raw_worker = (t.get("worker") or "").strip().lower().replace(" ", "_").replace("-", "_")
            worker = raw_worker if raw_worker in valid_workers else WorkerType.CLAUDE_CODE.value
            task = Task(
                project_id=project.id,
                title=t["title"],
                description=t.get("description", ""),
                priority=t.get("priority", 5),
                order=i,
                dependencies=t.get("dependencies", []),
                assigned_worker=worker,
                assigned_model=t.get("instruction_model"),
            )
            db.add(task)

        db.commit()

        await RedisManager.publish_project_update(
            project.id, {"status": "planned", "task_count": len(tasks_data), "model_used": selected_model}
        )
        await _log_activity("pm", selected_model, f"Decomposed into {len(tasks_data)} tasks", None, project.id)
        await _write_task_plan(project.id, tasks_data)
        await _git_commit(project.id, f"docs: task plan — {len(tasks_data)} tasks")

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
                f"Task: {task.title}\nComplexity hint: {task.description[:200]}",
                project_id=state["project_id"],
            )

            # Include previous failure history so the PM can write a better instruction
            previous_failures = ""
            is_retry = bool(task.fallback_history)
            if task.fallback_history:
                entries = task.fallback_history[-3:]  # last 3 attempts
                lines = []
                for e in entries:
                    error_str = e.get("error") or ""
                    # PM 리뷰 실패 이슈는 JSON 리스트 형식 — 전체를 bullet으로 표시
                    try:
                        issues = json.loads(error_str)
                        if isinstance(issues, list):
                            bullet_list = "\n".join(f"    • {issue}" for issue in issues)
                            lines.append(
                                f"  - Attempt {e.get('attempt', '?')}: [{e.get('worker', '?')}] "
                                f"PM Review REJECTED. Must fix ALL of the following:\n{bullet_list}"
                            )
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass
                    lines.append(
                        f"  - Attempt {e.get('attempt', '?')}: [{e.get('worker', '?')}] {error_str[:1000]}"
                    )
                previous_failures = (
                    "⚠️ RETRY CONTEXT — This task was previously attempted but REJECTED by PM review.\n"
                    "The worker's previous work exists in the workspace. DO NOT start from scratch.\n"
                    "Instead, FIX the specific issues below on top of the existing code:\n\n"
                    + "\n".join(lines)
                    + "\n\nAfter fixing, the instruction MUST tell the worker to output verification evidence:\n"
                    "  - Run `git log --oneline -5` and show output\n"
                    "  - Show directory tree of key folders (`ls -R` or `tree`)\n"
                    "  - Print actual contents of critical config files\n"
                    "  - Run any test commands and show results\n"
                )

            prompt = STAGE_GENERATE_INSTRUCTION.format(
                task_title=task.title,
                task_description=task.description,
                worker_type=task.assigned_worker,
                project_context=project_context[:2000],
                previous_failures=previous_failures,
            )

            resp = await _call_with_confirmation(
                model=selected_model,
                system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
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

        # Build name→id map from ALL project tasks so string deps can be resolved to IDs
        all_tasks = db.query(Task).filter(Task.project_id == project_id).all()
        name_to_id = {t.title: t.id for t in all_tasks}
        assigned_ids = {t.id for t in tasks}

        task_dicts = []
        for t in tasks:
            resolved_deps = []
            for dep in (t.dependencies or []):
                if isinstance(dep, int):
                    dep_id = dep
                else:
                    dep_id = name_to_id.get(dep)
                # Only add as ordering constraint if the dep is also being dispatched now
                # (already-completed deps don't need ordering)
                if dep_id and dep_id in assigned_ids:
                    resolved_deps.append(dep_id)
            task_dicts.append({"id": t.id, "dependencies": resolved_deps})
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

            # Stop if any task in this phase failed — don't run dependent phases
            phase_ids = [t["id"] for t in phase]
            db2 = SessionLocal()
            try:
                failed_in_phase = db2.query(Task).filter(
                    Task.id.in_(phase_ids),
                    Task.status == TaskStatus.FAILED,
                ).count()
            finally:
                db2.close()
            if failed_in_phase:
                await _log_activity("pm", "orchestrator",
                                    f"Phase stopped: {failed_in_phase} task(s) failed — routing to fallback",
                                    None, project_id)
                return {**state, "stage": "fallback", "error": None}

    except Exception as e:
        return {**state, "stage": "fallback", "error": str(e)}

    return {**state, "stage": "review", "error": None}


# ──────────────────────────────────────
# Node: Review Results
# ──────────────────────────────────────
async def review_results(state: ProjectState) -> ProjectState:
    db = SessionLocal()
    try:
        # If any tasks failed directly (worker exit_code != 0), handle fallback first
        direct_failed = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.FAILED,
        ).count()
        if direct_failed:
            await _log_activity("pm", "orchestrator",
                                f"{direct_failed} task(s) failed directly — routing to fallback",
                                None, state["project_id"])
            return {**state, "stage": "fallback", "error": None}

        tasks = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.REVIEW,
        ).all()

        all_approved = True
        for task in tasks:
            try:
                resp = await _call_with_confirmation(
                    model="haiku",  # Quality review — haiku's speed+quality worth the cost
                    system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
                    user_prompt=STAGE_REVIEW_RESULT.format(
                        task_title=task.title,
                        task_description=task.description,
                        worker_result=(task.result or "")[:6000],
                    ),
                    max_tokens=2048,
                    project_id=state["project_id"],
                    task_id=task.id,
                    stage="review",
                )

                _log_cost(db, state["project_id"], task.id, resp, "review")

                review = _parse_json_response(resp.content)
                if isinstance(review, list):
                    review = {"approved": False, "issues": review}

                if review.get("approved"):
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.utcnow()
                    db.commit()
                    await RedisManager.publish_task_update(
                        state["project_id"], task.id,
                        {"status": task.status.value, "review": review}
                    )
                    await _git_commit(
                        state["project_id"],
                        f"feat(task-{task.id}): {task.title}",
                    )
                else:
                    all_approved = False
                    task.status = TaskStatus.FAILED
                    task.error_message = json.dumps(review.get("issues", []))
                    db.commit()
                    await RedisManager.publish_task_update(
                        state["project_id"], task.id,
                        {"status": task.status.value, "review": review}
                    )
            except Exception as task_err:
                # 개별 task 리뷰 실패 → FAILED 처리 후 다음 task 계속
                logger.error(f"[review] Task {task.id} review failed: {task_err}")
                all_approved = False
                task.status = TaskStatus.FAILED
                task.error_message = f"Review error: {task_err}"
                db.commit()
                await RedisManager.publish_task_update(
                    state["project_id"], task.id,
                    {"status": task.status.value, "error": str(task_err)}
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

        # Check for pre-existing FAILED/HELD tasks that weren't in REVIEW
        remaining_failed = db.query(Task).filter(
            Task.project_id == project.id,
            Task.status.in_([TaskStatus.FAILED, TaskStatus.HELD]),
        ).count()

        if all_approved and not remaining_failed and project.progress >= 100:
            project.status = ProjectStatus.COMPLETED
            stage = "complete"
        elif not all_approved or remaining_failed > 0:
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
            await _git_merge_to_main(project.id)
            await _generate_completion_report(project.id, db)
            await notify_project_completed(project.name, project.id, project.total_cost, project.progress)
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
            Task.status.in_([TaskStatus.FAILED, TaskStatus.HELD]),
        ).all()

        for task in failed_tasks:
            was_held = task.status == TaskStatus.HELD
            if not was_held and task.retry_count >= task.max_retries:
                # 3회 실패 → HOLD + 대시보드 알림
                task.status = TaskStatus.HELD
                db.commit()

                await RedisManager.publish_alert(
                    "critical",
                    f"Task held after {task.max_retries} failures: {task.title}",
                    {"project_id": state["project_id"], "task_id": task.id},
                )
                project_for_name = db.query(Project).get(state["project_id"])
                if project_for_name:
                    await notify_project_failed(
                        project_for_name.name, state["project_id"],
                        f"Task '{task.title}' held after {task.max_retries} failures",
                    )
                continue

            # HELD tasks being re-evaluated after user resume: reset retry count
            if was_held:
                task.retry_count = 0

            # PM 리뷰 실패인지 워커 실행 실패인지 판별
            raw_error = task.error_message or state.get("error") or "Unknown"
            failure_type = "worker_execution"
            error_summary = raw_error[:500]
            try:
                parsed = json.loads(raw_error)
                if isinstance(parsed, list):
                    failure_type = "pm_review"
                    # 이슈 목록이 길면 요약: 앞 5개만 표시
                    issues_preview = parsed[:5]
                    if len(parsed) > 5:
                        issues_preview.append(f"... and {len(parsed) - 5} more issues")
                    error_summary = json.dumps(issues_preview, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass

            # MiniMax decides fallback strategy (flat rate, sufficient for structured routing)
            resp = await _call_with_confirmation(
                model="minimax",
                system_prompt=get_pm_system_prompt(project_id=state["project_id"]),
                user_prompt=STAGE_SELECT_FALLBACK.format(
                    failed_worker=task.assigned_worker,
                    failure_type=failure_type,
                    error_message=error_summary,
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

            try:
                decision = _parse_json_response(resp.content)
            except ValueError:
                # 모델이 JSON을 못 반환한 경우 — retry로 안전하게 기본 처리
                logger.warning(f"Fallback decision parse failed for task {task.id}, defaulting to retry")
                decision = {"action": "retry", "reason": "Model response parse failed"}
            action = decision.get("action", "hold")

            # Log fallback attempt
            history = list(task.fallback_history or [])
            history.append({
                "attempt": task.retry_count + 1,
                "action": action,
                "worker": task.assigned_worker,
                "to_worker": decision.get("target_worker"),
                "error": task.error_message or state.get("error", ""),
                "reason": decision.get("reason"),
                "timestamp": datetime.utcnow().isoformat(),
            })
            task.fallback_history = history
            flag_modified(task, "fallback_history")  # SQLAlchemy JSON column 변경 강제 감지
            task.retry_count += 1

            if action == "retry":
                # Reset to PENDING so instruct node regenerates instruction with failure context
                task.status = TaskStatus.PENDING
                task.error_message = None
            elif action == "fallback":
                task.assigned_worker = decision.get("target_worker", task.assigned_worker)
                # Reset to PENDING so instruct node picks correct worker's instruction style
                task.status = TaskStatus.PENDING
                task.error_message = None
                if decision.get("modified_instruction"):
                    mi = decision["modified_instruction"]
                    task.instruction = mi if isinstance(mi, str) else json.dumps(mi, ensure_ascii=False)
            elif action == "escalate":
                task.status = TaskStatus.PENDING
                if decision.get("modified_instruction"):
                    mi = decision["modified_instruction"]
                    task.instruction = mi if isinstance(mi, str) else json.dumps(mi, ensure_ascii=False)
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
            Task.status == TaskStatus.PENDING,
        ).count()
        assigned = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.ASSIGNED,
        ).count()
        review_remaining = db.query(Task).filter(
            Task.project_id == state["project_id"],
            Task.status == TaskStatus.REVIEW,
        ).count()

        if pending > 0:
            # PENDING tasks need instruction regeneration (with failure context)
            next_stage = "instruct"
        elif assigned > 0:
            next_stage = "dispatch"
        elif review_remaining > 0:
            # REVIEW tasks still waiting — go back to review
            next_stage = "review"
        else:
            # All tasks are HELD — pause project so user sees Resume button
            held = db.query(Task).filter(
                Task.project_id == state["project_id"],
                Task.status == TaskStatus.HELD,
            ).count()
            if held > 0:
                project = db.query(Project).get(state["project_id"])
                if project:
                    project.status = ProjectStatus.PAUSED
                    db.commit()
                    await RedisManager.publish_project_update(
                        state["project_id"], {"status": ProjectStatus.PAUSED.value}
                    )
            next_stage = "complete"
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
        return END


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

        # Reset stuck IN_PROGRESS tasks back to ASSIGNED for re-dispatch
        # (worker processes died when the backend was restarted)
        db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.IN_PROGRESS,
        ).update({"status": TaskStatus.ASSIGNED})
        db.commit()

        assigned_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.ASSIGNED,
        ).count()

        pending_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.PENDING,
        ).count()

        failed_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.FAILED,
        ).count()

        held_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.HELD,
        ).count()

        review_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.REVIEW,
        ).count()

        completed_count = db.query(Task).filter(
            Task.project_id == project_id,
            Task.status == TaskStatus.COMPLETED,
        ).count()
        total_task_count = (
            assigned_count + pending_count + review_count + failed_count + held_count + completed_count
        )

        if not project.analysis_result:
            # Analysis never completed — restart from the beginning
            resume_stage = "analyze"
        elif assigned_count > 0:
            resume_stage = "dispatch"
        elif pending_count > 0:
            resume_stage = "instruct"
        elif review_count > 0:
            # REVIEW tasks exist — PM should review them; fallback handled after
            resume_stage = "review"
        elif failed_count > 0 or held_count > 0:
            resume_stage = "fallback"
        elif total_task_count == 0:
            # Analysis done but no tasks created yet — need to decompose
            resume_stage = "decompose"
        else:
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
