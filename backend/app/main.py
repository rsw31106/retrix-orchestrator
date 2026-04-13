import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, BackgroundTasks, Query, UploadFile, File,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.database import engine, Base, get_db
from app.core.redis_manager import async_redis, RedisManager
from app.core.auth import (
    create_token, verify_token, verify_password,
    hash_password, get_current_user, require_admin, security,
)
from app.models.models import (
    Project, Task, CostLog, WorkerConfig, ModelConfig,
    ProjectStatus, TaskStatus, ModelType, WorkerType,
    User, ActivityLog, UserRole, SystemSetting,
)
from app.graph.orchestrator import run_project, dispatch_single_task, resume_project_run
from app.services.github import github_service

settings = get_settings()


# ──────────────────────────────────────
# Startup / Shutdown
# ──────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_model_configs()
    _seed_worker_configs()
    _seed_admin_user()
    yield
    await async_redis.close()
    await github_service.close()


def _migrate_schema():
    """Add any missing columns to existing tables without dropping data."""
    from sqlalchemy import text
    from app.core.database import SessionLocal
    migrations = [
        # projects table
        ("projects", "github_repo",     "ALTER TABLE projects ADD COLUMN github_repo VARCHAR(255) NULL"),
        ("projects", "github_branch",   "ALTER TABLE projects ADD COLUMN github_branch VARCHAR(100) DEFAULT 'main'"),
        ("projects", "github_clone_url","ALTER TABLE projects ADD COLUMN github_clone_url VARCHAR(500) NULL"),
        ("projects", "workspace_path",  "ALTER TABLE projects ADD COLUMN workspace_path VARCHAR(500) NULL"),
        ("projects", "archived",              "ALTER TABLE projects ADD COLUMN archived TINYINT(1) NOT NULL DEFAULT 0"),
        ("projects", "notion_page_id",        "ALTER TABLE projects ADD COLUMN notion_page_id VARCHAR(64) NULL"),
        ("projects", "notion_page_url",       "ALTER TABLE projects ADD COLUMN notion_page_url VARCHAR(500) NULL"),
        ("projects", "notion_last_content_hash", "ALTER TABLE projects ADD COLUMN notion_last_content_hash VARCHAR(32) NULL"),
        ("projects", "notion_last_synced_at", "ALTER TABLE projects ADD COLUMN notion_last_synced_at DATETIME NULL"),
        # tasks table
        ("tasks", "instruction", "ALTER TABLE tasks ADD COLUMN instruction TEXT NULL"),
        # worker_configs table
        ("worker_configs", "fallback_worker", "ALTER TABLE worker_configs ADD COLUMN fallback_worker VARCHAR(50) NULL"),
        ("worker_configs", "config",          "ALTER TABLE worker_configs ADD COLUMN config JSON NULL"),
        # system_settings table is created via create_all, but ensure key column exists
    ]
    db = SessionLocal()
    try:
        for table, col, sql in migrations:
            # Check if column exists before trying to add it
            result = db.execute(text(
                f"SELECT COUNT(*) FROM information_schema.columns "
                f"WHERE table_schema=DATABASE() AND table_name='{table}' AND column_name='{col}'"
            )).scalar()
            if result == 0:
                db.execute(text(sql))
                print(f"[MIGRATE] Added {table}.{col}")
        db.commit()
    except Exception as e:
        print(f"[MIGRATE] Error: {e}")
        db.rollback()
    finally:
        db.close()


def _seed_model_configs():
    from app.core.database import SessionLocal
    db = SessionLocal()
    if db.query(ModelConfig).count() == 0:
        configs = [
            ModelConfig(model_type=ModelType.HAIKU, input_price=1.0, output_price=5.0,
                        max_context=200000, strengths=["fast", "balanced", "coding"],
                        best_for=["routing", "review", "quick_decisions"]),
            ModelConfig(model_type=ModelType.DEEPSEEK_V3, input_price=0.14, output_price=0.28,
                        max_context=128000, strengths=["cheap", "long_context"],
                        best_for=["analysis", "bulk_processing"]),
            ModelConfig(model_type=ModelType.DEEPSEEK_V4, input_price=0.30, output_price=0.50,
                        max_context=1000000, strengths=["reasoning", "very_long_context"],
                        best_for=["decompose", "architecture"]),
            ModelConfig(model_type=ModelType.GPT_4O_MINI, input_price=0.15, output_price=0.60,
                        max_context=128000, strengths=["ultra_cheap", "fast"],
                        best_for=["instruction", "formatting", "templates"]),
            ModelConfig(model_type=ModelType.GPT_4O, input_price=2.50, output_price=10.0,
                        max_context=128000, strengths=["strong_reasoning", "all_around"],
                        best_for=["critical_decisions", "complex_review"]),
            ModelConfig(model_type=ModelType.MINIMAX, input_price=0.0, output_price=0.0,
                        max_context=128000, strengths=["unlimited", "flat_rate"],
                        best_for=["repetitive", "drafts", "high_volume"]),
        ]
        db.add_all(configs)
        db.commit()
    db.close()


def _seed_worker_configs():
    from app.core.database import SessionLocal
    db = SessionLocal()
    if db.query(WorkerConfig).count() == 0:
        configs = [
            WorkerConfig(worker_type=WorkerType.CLAUDE_CODE, priority=1,
                         fallback_worker=WorkerType.CURSOR,
                         config={"command": "claude", "type": "cli"}),
            WorkerConfig(worker_type=WorkerType.CURSOR, priority=2,
                         fallback_worker=WorkerType.CLAUDE_CODE,
                         config={"command": "cursor", "type": "ide"}),
            WorkerConfig(worker_type=WorkerType.CODEX, priority=3,
                         fallback_worker=WorkerType.GEMINI_CLI,
                         config={"command": "codex", "type": "cli"}),
            WorkerConfig(worker_type=WorkerType.GEMINI_CLI, priority=4,
                         fallback_worker=WorkerType.CODEX,
                         config={"command": "gemini", "type": "cli"}),
            WorkerConfig(worker_type=WorkerType.ANTIGRAVITY, priority=5,
                         fallback_worker=WorkerType.CLAUDE_CODE,
                         config={"command": "antigravity", "type": "cli"}),
        ]
        db.add_all(configs)
        db.commit()
    db.close()


def _seed_admin_user():
    """Ensure admin user exists in the users table."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == settings.admin_username).first()
        if not existing:
            password_hash = settings.admin_password_hash or hash_password("retrix2024!")
            admin = User(
                username=settings.admin_username,
                password_hash=password_hash,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(admin)
            db.commit()
        elif existing.password_hash != settings.admin_password_hash and settings.admin_password_hash:
            # Sync hash from .env if it was changed externally
            existing.password_hash = settings.admin_password_hash
            db.commit()
    finally:
        db.close()


app = FastAPI(title="Retrix", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://retrix.rebitgames.com", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class ProjectCreate(BaseModel):
    name: str
    project_type: str
    description: Optional[str] = None
    spec_document: str
    budget_limit: Optional[float] = None
    priority: int = 5
    workspace_path: Optional[str] = None
    github_create_repo: bool = False
    github_repo_name: Optional[str] = None
    github_private: bool = True
    notion_page_url: Optional[str] = None   # optional: attach Notion page on creation


class NotionConnectRequest(BaseModel):
    notion_page_url: str


class NotionSyncApplyRequest(BaseModel):
    confirmed: bool
    change_summary: str   # echo back PM's summary for logging


class TaskRetry(BaseModel):
    worker_override: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "viewer"


class UserRoleUpdate(BaseModel):
    role: str


class UserPasswordReset(BaseModel):
    new_password: str


class PMChatMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str


class PMChatRequest(BaseModel):
    messages: list[PMChatMessage]
    project_id: Optional[int] = None


class ModelConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    input_price: Optional[float] = None
    output_price: Optional[float] = None


class WorkerConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    fallback_worker: Optional[str] = None


class SettingsUpdate(BaseModel):
    daily_budget: Optional[float] = None
    project_budget: Optional[float] = None
    slack_webhook: Optional[str] = None
    notion_api_key: Optional[str] = None
    models: Optional[dict[str, ModelConfigUpdate]] = None
    workers: Optional[dict[str, WorkerConfigUpdate]] = None


class PMRulesUpdate(BaseModel):
    rules: str


# ──────────────────────────────────────
# Auth (public - no token required)
# ──────────────────────────────────────
@app.post("/api/auth/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == body.username, User.is_active == True
    ).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_token(user.username, role=user.role.value)
    return {"token": token, "username": user.username, "role": user.role.value, "expires_in": 72 * 3600}


@app.get("/api/auth/verify")
def verify_auth(user: dict = Depends(get_current_user)):
    return {"valid": True, "username": user["sub"], "role": user.get("role", "viewer")}


@app.post("/api/auth/change-password")
def change_password(body: PasswordChange, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    db_user = db.query(User).filter(User.username == user["sub"]).first()
    if not db_user or not verify_password(body.current_password, db_user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    db_user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"status": "changed"}


# ──────────────────────────────────────
# Projects (protected)
# ──────────────────────────────────────
@app.get("/api/projects")
def list_projects(
    archived: bool = Query(False),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    q = db.query(Project).filter(Project.archived == archived)
    projects = q.order_by(Project.priority, Project.created_at.desc()).all()
    return [{
        "id": p.id,
        "name": p.name,
        "project_type": p.project_type.value if p.project_type else None,
        "status": p.status.value,
        "progress": p.progress,
        "total_cost": p.total_cost,
        "priority": p.priority,
        "archived": p.archived,
        "github_repo": p.github_repo,
        "workspace_path": p.workspace_path,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "task_count": len(p.tasks),
    } for p in projects]


@app.get("/api/projects/{project_id}")
def get_project(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    tasks = [{
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "status": t.status.value,
        "priority": t.priority,
        "assigned_worker": t.assigned_worker.value if t.assigned_worker else None,
        "assigned_model": t.assigned_model.value if t.assigned_model else None,
        "retry_count": t.retry_count,
        "fallback_history": t.fallback_history,
        "error_message": t.error_message,
        "instruction": t.instruction,
        "result": t.result,
    } for t in project.tasks]
    return {
        "id": project.id,
        "name": project.name,
        "project_type": project.project_type.value if project.project_type else None,
        "status": project.status.value,
        "progress": project.progress,
        "description": project.description,
        "analysis_result": project.analysis_result,
        "plan": project.plan,
        "total_cost": project.total_cost,
        "budget_limit": project.budget_limit,
        "priority": project.priority,
        "github_repo": project.github_repo,
        "github_clone_url": project.github_clone_url,
        "workspace_path": project.workspace_path,
        "notion_page_id": project.notion_page_id,
        "notion_page_url": project.notion_page_url,
        "notion_last_synced_at": project.notion_last_synced_at.isoformat() if project.notion_last_synced_at else None,
        "tasks": tasks,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }


@app.post("/api/projects")
async def create_project(
    body: ProjectCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    # Determine workspace path
    workspace = body.workspace_path
    if not workspace:
        # Auto-generate: D:\Projects\{project-name}
        safe_name = body.name.lower().replace(" ", "-").replace("/", "-")
        workspace = os.path.join(settings.workspace_root, safe_name)

    # Notion page fetch (if URL provided)
    notion_page_id = None
    notion_content_hash = None
    spec_from_notion = body.spec_document
    notion_page_url_stored = None
    if body.notion_page_url:
        try:
            from app.services.notion import extract_page_id, fetch_page_as_markdown, compute_hash
            import datetime as _dt
            notion_page_id = extract_page_id(body.notion_page_url)
            _title, notion_md = await fetch_page_as_markdown(notion_page_id)
            if notion_md and not body.spec_document:
                spec_from_notion = notion_md
            notion_content_hash = compute_hash(notion_md)
            notion_page_url_stored = body.notion_page_url
        except Exception as e:
            print(f"[WARN] Notion fetch failed: {e}")

    project = Project(
        name=body.name,
        project_type=body.project_type,
        description=body.description,
        spec_document=spec_from_notion,
        budget_limit=body.budget_limit or settings.project_budget_limit,
        priority=body.priority,
        workspace_path=workspace,
        notion_page_id=notion_page_id,
        notion_page_url=notion_page_url_stored,
        notion_last_content_hash=notion_content_hash,
    )
    if notion_content_hash:
        import datetime as _dt
        project.notion_last_synced_at = _dt.datetime.utcnow()

    # GitHub repo creation
    if body.github_create_repo and settings.github_token:
        try:
            repo_name = body.github_repo_name or body.name.lower().replace(" ", "-")
            repo_info = await github_service.create_repo(
                name=repo_name,
                description=body.description or f"Retrix project: {body.name}",
                private=body.github_private,
                org=settings.github_org or None,
            )
            project.github_repo = repo_info["full_name"]
            project.github_clone_url = repo_info["clone_url"]
        except Exception as e:
            # Don't fail project creation if GitHub fails
            print(f"[WARN] GitHub repo creation failed: {e}")

    db.add(project)
    db.commit()
    db.refresh(project)

    # Create workspace directory
    try:
        os.makedirs(workspace, exist_ok=True)
    except Exception as e:
        print(f"[WARN] Could not create workspace dir: {e}")

    # Clone repo into workspace if GitHub was set up
    if project.github_clone_url:
        background_tasks.add_task(_git_clone, project.github_clone_url, workspace)

    # Start orchestration
    background_tasks.add_task(run_project, project.id, spec_from_notion)
    background_tasks.add_task(
        _log_activity, "user", user["sub"],
        f"Created project: {project.name}",
        {"project_type": body.project_type, "priority": body.priority},
        project.id, None,
    )

    return {
        "id": project.id,
        "status": "queued",
        "workspace_path": workspace,
        "github_repo": project.github_repo,
        "message": "Project created, orchestration starting...",
    }


async def _git_clone(clone_url: str, target_dir: str):
    """Clone GitHub repo into workspace directory."""
    import subprocess
    try:
        # If dir already has files, init and add remote instead
        if os.listdir(target_dir):
            subprocess.run(["git", "init"], cwd=target_dir, check=True, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=target_dir, capture_output=True)
            subprocess.run(["git", "fetch", "origin"], cwd=target_dir, check=True, capture_output=True)
        else:
            subprocess.run(["git", "clone", clone_url, target_dir], check=True, capture_output=True)
    except Exception as e:
        print(f"[WARN] Git clone failed: {e}")


@app.post("/api/projects/{project_id}/pause")
def pause_project(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404)
    project.status = ProjectStatus.PAUSED
    db.commit()
    return {"status": "paused"}


@app.post("/api/projects/{project_id}/resume")
async def resume_project(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404)
    project.status = ProjectStatus.IN_PROGRESS
    db.commit()
    background_tasks.add_task(resume_project_run, project.id)
    return {"status": "resumed"}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404)
    db.delete(project)
    db.commit()
    return {"status": "deleted"}


@app.post("/api/projects/{project_id}/archive")
def archive_project(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404)
    project.archived = True
    db.commit()
    return {"status": "archived"}


@app.post("/api/projects/{project_id}/unarchive")
def unarchive_project(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404)
    project.archived = False
    db.commit()
    return {"status": "unarchived"}


# ──────────────────────────────────────
# Notion Integration (protected)
# ──────────────────────────────────────
@app.post("/api/projects/{project_id}/notion/connect")
async def notion_connect(
    project_id: int,
    body: NotionConnectRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Attach a Notion page to an existing project and import its content as spec."""
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    from app.services.notion import extract_page_id, fetch_page_as_markdown, compute_hash
    import datetime as _dt

    try:
        page_id = extract_page_id(body.notion_page_url)
        title, content = await fetch_page_as_markdown(page_id)
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch Notion page: {e}")

    project.notion_page_id = page_id
    project.notion_page_url = body.notion_page_url
    project.notion_last_content_hash = compute_hash(content)
    project.notion_last_synced_at = _dt.datetime.utcnow()
    if not project.spec_document and content:
        project.spec_document = content
    db.commit()

    await _log_activity("user", user["sub"], f"Connected Notion page to project: {project.name}",
                        detail={"page_id": page_id, "notion_url": body.notion_page_url},
                        project_id=project_id, db=db)
    return {"status": "connected", "page_id": page_id, "title": title}


@app.get("/api/projects/{project_id}/notion/sync-preview")
async def notion_sync_preview(
    project_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Fetch current Notion content, detect changes, ask PM to summarize diff and suggest tasks."""
    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.notion_page_id:
        raise HTTPException(400, "No Notion page connected to this project")

    from app.services.notion import fetch_page_as_markdown, compute_hash
    from app.services.model_pool import model_pool

    try:
        title, new_content = await fetch_page_as_markdown(project.notion_page_id)
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch Notion page: {e}")

    new_hash = compute_hash(new_content)
    if new_hash == project.notion_last_content_hash:
        return {"changed": False, "message": "Notion page has not changed since last sync."}

    old_spec = project.spec_document or ""

    # Ask PM to analyze the diff
    pm_prompt = f"""The project spec document has been updated on Notion. Analyze what changed and suggest development tasks.

Project: {project.name}
Project Type: {project.project_type.value}

=== PREVIOUS SPEC ===
{old_spec[:3000]}

=== UPDATED SPEC (from Notion) ===
{new_content[:3000]}

Please provide:
1. A concise summary of what changed (bullet points)
2. A list of suggested new development tasks based on the changes

Format your response as:
## Changes Summary
- ...

## Suggested Tasks
1. [Task title] — [brief description]
2. ...

Be specific and actionable. Respond in the same language as the spec document."""

    response = await model_pool.call(
        model="haiku",
        system_prompt="You are Retrix PM analyzing spec document changes to plan development work.",
        user_prompt=pm_prompt,
        temperature=0.3,
        max_tokens=2000,
    )

    return {
        "changed": True,
        "title": title,
        "new_hash": new_hash,
        "pm_analysis": response.content,
        "tokens": response.input_tokens + response.output_tokens,
        "cost": response.cost_usd,
    }


@app.post("/api/projects/{project_id}/notion/sync-apply")
async def notion_sync_apply(
    project_id: int,
    body: NotionSyncApplyRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """User confirmed the sync. Update spec and create new tasks from PM's analysis."""
    if not body.confirmed:
        return {"status": "cancelled"}

    project = db.query(Project).get(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project.notion_page_id:
        raise HTTPException(400, "No Notion page connected to this project")

    from app.services.notion import fetch_page_as_markdown, compute_hash
    from app.services.model_pool import model_pool
    import datetime as _dt

    try:
        _title, new_content = await fetch_page_as_markdown(project.notion_page_id)
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch Notion page: {e}")

    # Update spec and hash
    project.spec_document = new_content
    project.notion_last_content_hash = compute_hash(new_content)
    project.notion_last_synced_at = _dt.datetime.utcnow()

    # Ask PM to produce structured task list from the analysis
    task_prompt = f"""Based on this analysis of spec changes, generate a structured list of new development tasks.

{body.change_summary}

Project: {project.name}

Return ONLY a JSON array in this exact format (no markdown, no explanation):
[
  {{"title": "Task title", "description": "What needs to be done", "priority": 5}},
  ...
]"""

    task_response = await model_pool.call(
        model="haiku",
        system_prompt="You are Retrix PM. Output only valid JSON arrays, no extra text.",
        user_prompt=task_prompt,
        temperature=0.2,
        max_tokens=2000,
    )

    # Parse tasks and create them
    created_tasks = []
    try:
        raw = task_response.content.strip()
        # Strip possible markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        task_defs = json.loads(raw.strip())
        if not isinstance(task_defs, list):
            task_defs = []
    except Exception:
        task_defs = []

    # Determine next order value
    max_order = db.query(Task).filter(Task.project_id == project_id).count()
    for i, td in enumerate(task_defs):
        t = Task(
            project_id=project_id,
            title=td.get("title", "Untitled task"),
            description=td.get("description", ""),
            priority=td.get("priority", 5),
            order=max_order + i,
            status=TaskStatus.PENDING,
        )
        db.add(t)
        created_tasks.append(t.title)

    db.commit()

    await _log_activity("user", user["sub"],
                        f"Applied Notion sync for project: {project.name}",
                        detail={"tasks_created": len(created_tasks), "change_summary": body.change_summary[:300]},
                        project_id=project_id, db=db)

    # If project is paused/completed, resume it
    if project.status in (ProjectStatus.COMPLETED, ProjectStatus.PAUSED):
        project.status = ProjectStatus.IN_PROGRESS
        db.commit()
        background_tasks.add_task(resume_project_run, project_id)

    return {"status": "applied", "tasks_created": len(created_tasks), "task_titles": created_tasks}


# ──────────────────────────────────────
# Tasks (protected)
# ──────────────────────────────────────
@app.post("/api/tasks/{task_id}/retry")
async def retry_task(
    task_id: int, body: TaskRetry,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404)
    task.status = TaskStatus.ASSIGNED
    task.error_message = None
    if body.worker_override:
        task.assigned_worker = body.worker_override
    db.commit()
    background_tasks.add_task(dispatch_single_task, task_id)
    return {"status": "retrying", "task_id": task.id}


@app.post("/api/tasks/{task_id}/hold")
def hold_task(task_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404)
    task.status = TaskStatus.HELD
    db.commit()
    return {"status": "held"}


class InstructionUpdate(BaseModel):
    instruction: str


@app.patch("/api/tasks/{task_id}/instruction")
def update_task_instruction(
    task_id: int,
    body: InstructionUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    task = db.query(Task).get(task_id)
    if not task:
        raise HTTPException(404)
    task.instruction = body.instruction
    db.commit()
    return {"status": "updated"}


# ──────────────────────────────────────
# Model Switch Confirmations
# ──────────────────────────────────────

class ConfirmationResponse(BaseModel):
    approved: bool
    model: Optional[str] = None


@app.get("/api/confirmations")
async def list_confirmations(user: dict = Depends(get_current_user)):
    """List all pending model switch confirmation requests."""
    raw = await async_redis.hgetall("retrix:confirmations")
    items = [json.loads(v) for v in raw.values()]
    items.sort(key=lambda x: x.get("created_at", ""))
    return items


@app.post("/api/confirmations/{conf_id}/respond")
async def respond_confirmation(
    conf_id: str,
    body: ConfirmationResponse,
    user: dict = Depends(get_current_user),
):
    """Respond to a pending model switch confirmation."""
    response_key = f"retrix:confirmation:{conf_id}:response"
    if body.approved:
        chosen = body.model or "haiku"
        await async_redis.setex(response_key, 600, f"approve:{chosen}")
    else:
        await async_redis.setex(response_key, 600, "deny")
    # Remove from pending list immediately so UI clears
    await async_redis.hdel("retrix:confirmations", conf_id)
    return {"status": "ok"}


# ──────────────────────────────────────
# GitHub (protected)
# ──────────────────────────────────────
@app.post("/api/github/create-repo")
async def create_github_repo(
    name: str,
    description: str = "",
    private: bool = True,
    user: dict = Depends(get_current_user),
):
    if not settings.github_token:
        raise HTTPException(400, "GitHub token not configured in .env")
    repo = await github_service.create_repo(
        name=name,
        description=description,
        private=private,
        org=settings.github_org or None,
    )
    return repo


@app.get("/api/github/repos/{owner}/{repo}")
async def get_github_repo(owner: str, repo: str, user: dict = Depends(get_current_user)):
    return await github_service.get_repo_info(owner, repo)


# ──────────────────────────────────────
# Costs & Dashboard (protected)
# ──────────────────────────────────────
@app.get("/api/costs/today")
async def get_today_costs(user: dict = Depends(get_current_user)):
    return await RedisManager.get_today_costs()


@app.get("/api/costs/history")
async def get_cost_history(days: int = Query(30, ge=1, le=90), user: dict = Depends(get_current_user)):
    import datetime
    history = []
    today = datetime.date.today()
    for i in range(days - 1, -1, -1):
        date = today - datetime.timedelta(days=i)
        raw = await async_redis.hgetall(f"retrix:costs:{date.isoformat()}")
        entry = {"date": date.isoformat(), "total": 0.0}
        for k, v in raw.items():
            entry[k] = float(v)
        history.append(entry)
    return history


@app.get("/api/costs/by-project/{project_id}")
def get_project_costs(project_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    logs = db.query(CostLog).filter(CostLog.project_id == project_id).all()
    total = sum(l.cost_usd for l in logs)
    by_model = {}
    for l in logs:
        m = l.model.value if hasattr(l.model, 'value') else l.model
        by_model[m] = by_model.get(m, 0) + l.cost_usd
    return {"total": total, "by_model": by_model, "log_count": len(logs)}


@app.get("/api/workers/status")
async def get_worker_status(user: dict = Depends(get_current_user)):
    return await RedisManager.get_all_worker_status()


@app.get("/api/dashboard/summary")
async def dashboard_summary(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    projects = db.query(Project).all()
    costs = await RedisManager.get_today_costs()
    workers = await RedisManager.get_all_worker_status()

    return {
        "projects": {
            "total": len(projects),
            "active": sum(1 for p in projects if p.status in (
                ProjectStatus.ANALYZING, ProjectStatus.PLANNING, ProjectStatus.IN_PROGRESS)),
            "completed": sum(1 for p in projects if p.status == ProjectStatus.COMPLETED),
            "paused": sum(1 for p in projects if p.status == ProjectStatus.PAUSED),
            "failed": sum(1 for p in projects if p.status == ProjectStatus.FAILED),
        },
        "costs_today": costs,
        "workers": workers,
    }


# ──────────────────────────────────────
# Spec Document Upload (protected)
# ──────────────────────────────────────
@app.post("/api/upload/spec")
async def upload_spec(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Parse an uploaded spec document and return its text content.
    Supports: .md (plain text), .pdf (pypdf), .docx (python-docx).
    """
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("md", "txt", "pdf", "docx"):
        raise HTTPException(400, f"Unsupported file type: .{ext}. Use .md, .txt, .pdf, or .docx")

    data = await file.read()

    try:
        if ext in ("md", "txt"):
            text = data.decode("utf-8", errors="replace")

        elif ext == "pdf":
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(pages).strip()
            if not text:
                raise HTTPException(422, "PDF appears to have no extractable text (might be scanned image).")

        elif ext == "docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to parse {ext.upper()} file: {e}")

    return {"filename": filename, "text": text, "char_count": len(text)}


# ──────────────────────────────────────
# Activity Log helper
# ──────────────────────────────────────
async def _log_activity(
    actor_type: str, actor_name: str, action: str,
    detail=None, project_id=None, task_id=None,
    db: Session = None,
):
    import datetime
    log = ActivityLog(
        actor_type=actor_type,
        actor_name=actor_name,
        action=action,
        detail=detail,
        project_id=project_id,
        task_id=task_id,
    )
    if db:
        db.add(log)
        db.commit()
    else:
        from app.core.database import SessionLocal
        _db = SessionLocal()
        try:
            _db.add(log)
            _db.commit()
        finally:
            _db.close()
    await RedisManager.publish_activity(actor_type, actor_name, action, detail, project_id, task_id)


# ──────────────────────────────────────
# User Management (admin only)
# ──────────────────────────────────────
@app.get("/api/users")
def list_users(db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    users = db.query(User).order_by(User.created_at).all()
    return [{
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role.value,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    } for u in users]


@app.post("/api/users")
async def create_user(body: UserCreate, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, f"Username '{body.username}' already exists")
    if body.role not in ("admin", "viewer"):
        raise HTTPException(400, "Role must be 'admin' or 'viewer'")
    new_user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=UserRole(body.role),
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    await _log_activity("user", user["sub"], f"Created account: {body.username} ({body.role})", db=db)
    return {"id": new_user.id, "username": new_user.username, "role": new_user.role.value}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.username == user["sub"]:
        raise HTTPException(400, "Cannot delete your own account")
    username = target.username
    db.delete(target)
    db.commit()
    await _log_activity("user", user["sub"], f"Deleted account: {username}", db=db)
    return {"status": "deleted"}


@app.patch("/api/users/{user_id}/role")
async def update_user_role(user_id: int, body: UserRoleUpdate, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    if body.role not in ("admin", "viewer"):
        raise HTTPException(400, "Role must be 'admin' or 'viewer'")
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    old_role = target.role.value
    target.role = UserRole(body.role)
    db.commit()
    await _log_activity("user", user["sub"], f"Changed {target.username} role: {old_role} -> {body.role}", db=db)
    return {"status": "updated", "role": body.role}


@app.post("/api/users/{user_id}/change-password")
async def admin_change_password(user_id: int, body: UserPasswordReset, db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    target = db.query(User).get(user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.password_hash = hash_password(body.new_password)
    db.commit()
    await _log_activity("user", user["sub"], f"Reset password for: {target.username}", db=db)
    return {"status": "changed"}


# ──────────────────────────────────────
# Activity Log (protected)
# ──────────────────────────────────────
@app.get("/api/activity")
def get_activity(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    project_id: Optional[int] = None,
    actor_type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    query = db.query(ActivityLog).order_by(ActivityLog.created_at.desc())
    if project_id:
        query = query.filter(ActivityLog.project_id == project_id)
    if actor_type:
        query = query.filter(ActivityLog.actor_type == actor_type)
    total = query.count()
    logs = query.offset(offset).limit(limit).all()
    return {
        "total": total,
        "logs": [{
            "id": l.id,
            "actor_type": l.actor_type,
            "actor_name": l.actor_name,
            "action": l.action,
            "detail": l.detail,
            "project_id": l.project_id,
            "task_id": l.task_id,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
    }


# ──────────────────────────────────────
# PM Chat (protected)
# ──────────────────────────────────────
@app.post("/api/pm/chat")
async def pm_chat(
    body: PMChatRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from app.services.model_pool import model_pool

    # Build context about current system state
    projects = db.query(Project).order_by(Project.created_at.desc()).limit(20).all()
    context_lines = ["=== Current Retrix System Status ==="]
    for p in projects:
        completed = sum(1 for t in p.tasks if t.status == TaskStatus.COMPLETED)
        total_tasks = len(p.tasks)
        context_lines.append(
            f"- [{p.status.value.upper()}] {p.name} | {completed}/{total_tasks} tasks | cost: ${p.total_cost:.4f}"
        )

    if body.project_id:
        proj = db.query(Project).get(body.project_id)
        if proj:
            context_lines.append(f"\n=== Focused Project: {proj.name} ===")
            context_lines.append(f"Status: {proj.status.value} | Progress: {proj.progress:.1f}%")
            context_lines.append(f"Budget: ${proj.total_cost:.4f} / ${proj.budget_limit or 0:.2f}")
            if proj.tasks:
                context_lines.append("Tasks:")
                for t in proj.tasks:
                    context_lines.append(
                        f"  [{t.status.value}] {t.title} (worker: {t.assigned_worker.value if t.assigned_worker else 'unassigned'})"
                    )

    system_ctx = "\n".join(context_lines)

    system_prompt = f"""You are Retrix PM (Project Manager), an AI assistant managing software development projects.
You have full visibility into all projects, tasks, costs, and worker status.
You can answer questions, give status updates, analyze problems, and provide recommendations.
Be concise, direct, and use technical language. Respond in the same language as the user.

{system_ctx}"""

    # Build combined prompt from history (keep last 10 turns to stay within token budget)
    recent_messages = body.messages[-11:]  # last 10 turns + current
    history_text = ""
    for msg in recent_messages[:-1]:
        prefix = "User" if msg.role == "user" else "PM"
        # Truncate each history message to 1000 chars to limit token usage
        history_text += f"{prefix}: {msg.content[:1000]}\n"

    last_user = recent_messages[-1].content if recent_messages else ""
    full_user_prompt = (history_text + f"User: {last_user}").strip() if history_text else last_user

    response = await model_pool.call(
        model="haiku",
        system_prompt=system_prompt,
        user_prompt=full_user_prompt,
        temperature=0.5,
        max_tokens=1500,
    )

    reply = response.content
    await _log_activity(
        "pm", "Haiku-PM",
        f"Chat reply to {user['sub']}",
        detail={"user_message": last_user[:200], "reply_preview": reply[:200]},
        project_id=body.project_id,
        db=db,
    )
    return {"reply": reply, "tokens": response.input_tokens + response.output_tokens, "cost": response.cost_usd}


# ──────────────────────────────────────
# Settings (admin protected)
# ──────────────────────────────────────
def _get_setting(db: Session, key: str, default: str = None) -> Optional[str]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return row.value if row else default


def _set_setting(db: Session, key: str, value: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value))
    db.commit()


@app.get("/api/settings")
def get_settings_api(db: Session = Depends(get_db), user: dict = Depends(require_admin)):
    daily_budget = float(_get_setting(db, "daily_budget_limit", str(settings.daily_budget_limit)))
    project_budget = float(_get_setting(db, "project_budget_limit", str(settings.project_budget_limit)))

    model_configs = db.query(ModelConfig).all()
    worker_configs = db.query(WorkerConfig).all()

    slack_webhook = _get_setting(db, "slack_webhook", settings.slack_webhook_url)
    # Return notion_api_key masked — just indicate if set
    notion_key_raw = _get_setting(db, "notion_api_key", settings.notion_api_key)
    notion_api_key = ("secret_" + "*" * 8) if notion_key_raw else ""

    return {
        "daily_budget": daily_budget,
        "project_budget": project_budget,
        "slack_webhook": slack_webhook,
        "notion_api_key": notion_api_key,
        "models": [{
            "key": m.model_type.value,
            "enabled": m.enabled,
            "input_price": m.input_price,
            "output_price": m.output_price,
            "max_context": m.max_context,
            "strengths": m.strengths,
            "best_for": m.best_for,
        } for m in model_configs],
        "workers": [{
            "key": w.worker_type.value,
            "enabled": w.enabled,
            "priority": w.priority,
            "fallback_worker": w.fallback_worker.value if w.fallback_worker else None,
            "config": w.config,
        } for w in worker_configs],
    }


@app.put("/api/settings")
async def update_settings_api(
    body: SettingsUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    if body.daily_budget is not None:
        _set_setting(db, "daily_budget_limit", str(body.daily_budget))
    if body.project_budget is not None:
        _set_setting(db, "project_budget_limit", str(body.project_budget))
    if body.slack_webhook is not None:
        _set_setting(db, "slack_webhook", body.slack_webhook)
    if body.notion_api_key is not None:
        # Only save if it's a real key (not the masked placeholder returned by GET)
        if body.notion_api_key == "" or not body.notion_api_key.startswith("secret_****"):
            _set_setting(db, "notion_api_key", body.notion_api_key)

    if body.models:
        for key, upd in body.models.items():
            try:
                mtype = ModelType(key)
            except ValueError:
                continue
            mc = db.query(ModelConfig).filter(ModelConfig.model_type == mtype).first()
            if mc:
                if upd.enabled is not None:
                    mc.enabled = upd.enabled
                if upd.input_price is not None:
                    mc.input_price = upd.input_price
                if upd.output_price is not None:
                    mc.output_price = upd.output_price
        db.commit()

    if body.workers:
        for key, upd in body.workers.items():
            try:
                wtype = WorkerType(key)
            except ValueError:
                continue
            wc = db.query(WorkerConfig).filter(WorkerConfig.worker_type == wtype).first()
            if wc:
                if upd.enabled is not None:
                    wc.enabled = upd.enabled
                if upd.priority is not None:
                    wc.priority = upd.priority
                if upd.fallback_worker is not None:
                    try:
                        wc.fallback_worker = WorkerType(upd.fallback_worker)
                    except ValueError:
                        pass
        db.commit()

    await _log_activity("user", user["sub"], "Updated system settings", db=db)
    return {"status": "saved"}


# ──────────────────────────────────────
# PM Rules (admin protected)
# ──────────────────────────────────────
@app.get("/api/pm/rules")
def get_pm_rules(db: Session = Depends(get_db), user: dict = Depends(get_current_user)):
    from app.graph.rules import PM_ABSOLUTE_RULES
    # DB override takes priority over file
    db_rules = _get_setting(db, "pm_rules")
    return {"rules": db_rules if db_rules is not None else PM_ABSOLUTE_RULES}


@app.put("/api/pm/rules")
async def update_pm_rules(
    body: PMRulesUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    _set_setting(db, "pm_rules", body.rules)
    await _log_activity("user", user["sub"], "Updated PM rules", db=db)
    return {"status": "saved"}


# ──────────────────────────────────────
# WebSocket (token via query param)
# ──────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        for ws in list(self.active):
            try:
                await ws.send_text(message)
            except:
                self.disconnect(ws)


ws_manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: Optional[str] = Query(None)):
    # Verify token for WebSocket
    if not token or not verify_token(token):
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(ws)

    async def redis_listener():
        pubsub = async_redis.pubsub()
        await pubsub.subscribe(
            RedisManager.CHANNEL_PROJECT,
            RedisManager.CHANNEL_TASK,
            RedisManager.CHANNEL_WORKER,
            RedisManager.CHANNEL_ALERT,
            RedisManager.CHANNEL_ACTIVITY,
            RedisManager.CHANNEL_CONFIRMATION,
        )
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await ws_manager.broadcast(message["data"])
        except asyncio.CancelledError:
            await pubsub.unsubscribe()

    listener_task = asyncio.create_task(redis_listener())

    try:
        while True:
            data = await ws.receive_text()
            try:
                cmd = json.loads(data)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
        listener_task.cancel()
