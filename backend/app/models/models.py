from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, Enum, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class ProjectType(str, enum.Enum):
    GAME_UNITY = "game_unity"
    GAME_COCOS = "game_cocos"
    GAME_GODOT = "game_godot"
    WEB_SERVICE = "web_service"
    MOBILE_APP = "mobile_app"


class ProjectStatus(str, enum.Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    HELD = "held"  # 3회 실패 → 사람 개입 필요


class WorkerType(str, enum.Enum):
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"
    CODEX = "codex"
    GEMINI_CLI = "gemini_cli"
    ANTIGRAVITY = "antigravity"


class ModelType(str, enum.Enum):
    HAIKU = "haiku"
    DEEPSEEK_V3 = "deepseek_v3"
    DEEPSEEK_V4 = "deepseek_v4"
    GPT_4O_MINI = "gpt_4o_mini"
    GPT_4O = "gpt_4o"
    MINIMAX = "minimax"


# ──────────────────────────────────────
# Projects
# ──────────────────────────────────────
class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    project_type = Column(Enum(ProjectType), nullable=False)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.QUEUED)
    progress = Column(Float, default=0.0)  # 0.0 ~ 100.0

    # 기획서 원문
    spec_document = Column(Text, nullable=True)
    # PM이 분석한 결과
    analysis_result = Column(JSON, nullable=True)
    # PM이 세운 계획
    plan = Column(JSON, nullable=True)

    # 예산
    budget_limit = Column(Float, nullable=True)
    total_cost = Column(Float, default=0.0)

    # GitHub
    github_repo = Column(String(255), nullable=True)      # owner/repo
    github_branch = Column(String(100), default="main")
    github_clone_url = Column(String(500), nullable=True)

    # Workspace (local path where workers operate)
    workspace_path = Column(String(500), nullable=True)    # e.g. D:\Projects\my-game

    # Notion integration
    notion_page_id = Column(String(64), nullable=True)
    notion_page_url = Column(String(500), nullable=True)
    notion_last_content_hash = Column(String(32), nullable=True)   # sha256[:16] of last synced content
    notion_last_synced_at = Column(DateTime, nullable=True)

    # 메타
    priority = Column(Integer, default=5)  # 1(highest) ~ 10(lowest)
    archived = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    cost_logs = relationship("CostLog", back_populates="project", cascade="all, delete-orphan")


# ──────────────────────────────────────
# Tasks
# ──────────────────────────────────────
class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)

    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    instruction = Column(Text, nullable=True)  # 워커에게 전달할 지시서

    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(Integer, default=5)
    order = Column(Integer, default=0)  # 실행 순서

    # 의존성 (다른 task id 목록)
    dependencies = Column(JSON, default=list)

    # 할당
    assigned_worker = Column(Enum(WorkerType), nullable=True)
    assigned_model = Column(Enum(ModelType), nullable=True)  # PM 단계에서 사용된 모델

    # Fallback 추적
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    fallback_history = Column(JSON, default=list)  # [{worker, error, timestamp}]

    # 결과
    result = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    # 메타
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relations
    project = relationship("Project", back_populates="tasks")


# ──────────────────────────────────────
# Cost Tracking
# ──────────────────────────────────────
class CostLog(Base):
    __tablename__ = "cost_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

    model = Column(Enum(ModelType), nullable=False)
    stage = Column(String(50), nullable=False)  # analysis, decompose, instruction, review, fallback

    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)

    created_at = Column(DateTime, server_default=func.now())

    # Relations
    project = relationship("Project", back_populates="cost_logs")


# ──────────────────────────────────────
# Worker Status (persistent)
# ──────────────────────────────────────
class WorkerConfig(Base):
    __tablename__ = "worker_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    worker_type = Column(Enum(WorkerType), unique=True, nullable=False)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=5)  # fallback 순서

    # Worker-specific config (command paths, API endpoints, etc.)
    config = Column(JSON, default=dict)

    # Fallback mapping: which worker to try if this one fails
    fallback_worker = Column(Enum(WorkerType), nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ──────────────────────────────────────
# Model Pool Config
# ──────────────────────────────────────
class ModelConfig(Base):
    __tablename__ = "model_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_type = Column(Enum(ModelType), unique=True, nullable=False)
    enabled = Column(Boolean, default=True)

    # Pricing per 1M tokens
    input_price = Column(Float, nullable=False)   # USD per 1M input tokens
    output_price = Column(Float, nullable=False)  # USD per 1M output tokens

    # Capabilities (Haiku uses these to decide)
    max_context = Column(Integer, default=128000)
    strengths = Column(JSON, default=list)   # ["reasoning", "long_context", "fast", "cheap"]
    best_for = Column(JSON, default=list)    # ["analysis", "decompose", "instruction", "review"]

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ──────────────────────────────────────
# Users
# ──────────────────────────────────────
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), nullable=True)
    password_hash = Column(String(64), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.VIEWER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


# ──────────────────────────────────────
# Activity Log
# ──────────────────────────────────────
class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor_type = Column(String(20), nullable=False)   # pm, worker, system, user
    actor_name = Column(String(100), nullable=False)
    action = Column(String(255), nullable=False)
    detail = Column(JSON, nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# ──────────────────────────────────────
# System Settings (key-value store)
# ──────────────────────────────────────
class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
