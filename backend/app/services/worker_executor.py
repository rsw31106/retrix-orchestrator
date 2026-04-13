"""
Worker Executor Service.
Handles actual subprocess invocation of each worker CLI tool.
Each worker operates on a git feature branch in the project workspace.
"""
import asyncio
import subprocess
import os
import shutil
import logging
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Timeout per worker invocation (seconds). 4h max per PM rules; default 30min.
DEFAULT_TIMEOUT = 1800  # 30 minutes


@dataclass
class WorkerResult:
    success: bool
    output: str          # stdout from the worker
    error: str           # stderr or exception message
    branch: str          # git branch used
    exit_code: int


# ──────────────────────────────────────
# Git helpers
# ──────────────────────────────────────

def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9-]", "-", text.lower())[:40].strip("-")


async def _git_create_branch(workspace: str, branch: str) -> bool:
    """Create and checkout a feature branch. Returns True on success."""
    proc = await asyncio.create_subprocess_exec(
        "git", "checkout", "-b", branch,
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Branch might already exist; try checkout
        proc2 = await asyncio.create_subprocess_exec(
            "git", "checkout", branch,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()
        return proc2.returncode == 0
    return True


async def _git_is_repo(workspace: str) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "git", "rev-parse", "--is-inside-work-tree",
        cwd=workspace,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    return proc.returncode == 0


async def _ensure_git_repo(workspace: str) -> bool:
    """Init git repo if not already one."""
    if not await _git_is_repo(workspace):
        proc = await asyncio.create_subprocess_exec(
            "git", "init",
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        # Initial commit so branching works
        proc2 = await asyncio.create_subprocess_exec(
            "git", "commit", "--allow-empty", "-m", "chore: init workspace",
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_AUTHOR_NAME": "Retrix", "GIT_AUTHOR_EMAIL": "retrix@local",
                 "GIT_COMMITTER_NAME": "Retrix", "GIT_COMMITTER_EMAIL": "retrix@local"},
        )
        await proc2.communicate()
    return True


# ──────────────────────────────────────
# Worker-specific invokers
# ──────────────────────────────────────

async def _run_subprocess(
    cmd: list[str],
    cwd: str,
    timeout: int = DEFAULT_TIMEOUT,
    env: Optional[dict] = None,
) -> tuple[int, str, str]:
    """Run a subprocess, capture stdout/stderr, enforce timeout."""
    merged_env = {**os.environ, **(env or {})}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        proc.kill()
        return -1, "", f"Worker timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


async def invoke_claude_code(instruction: str, workspace: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """
    Claude Code CLI: claude -p "<instruction>"
    Runs non-interactively (print mode) in the workspace directory.
    Requires 'claude' to be on PATH (npm install -g @anthropic-ai/claude-code).
    """
    if not shutil.which("claude"):
        return -1, "", "claude CLI not found on PATH. Install with: winget install Anthropic.ClaudeCode"

    cmd = ["claude", "-p", instruction, "--dangerously-skip-permissions"]
    return await _run_subprocess(cmd, cwd=workspace, timeout=timeout)


async def invoke_codex(instruction: str, workspace: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """
    OpenAI Codex CLI: codex --approval-mode full-auto "<instruction>"
    Requires 'codex' to be on PATH (npm install -g @openai/codex).
    """
    if not shutil.which("codex"):
        return -1, "", "codex CLI not found on PATH. Install with: npm install -g @openai/codex"

    codex_bin = shutil.which("codex")
    cmd = ["cmd", "/c", codex_bin, "exec", "--full-auto", instruction]
    return await _run_subprocess(cmd, cwd=workspace, timeout=timeout)


async def invoke_gemini_cli(instruction: str, workspace: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """
    Gemini CLI: gemini -p "<instruction>" -y
    -p  non-interactive (headless) mode
    -y  auto-approve all tool actions (YOLO mode)
    """
    cli = shutil.which("gemini") or shutil.which("gemini-cli")
    if not cli:
        return -1, "", "gemini CLI not found on PATH. Install with: npm install -g @google/generative-ai"

    cmd = [cli, "-p", instruction, "-y"]
    return await _run_subprocess(cmd, cwd=workspace, timeout=timeout)


async def invoke_cursor(instruction: str, workspace: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """
    Cursor standalone CLI: agent -p "<instruction>" --yolo
    -p     non-interactive (headless) mode
    --yolo auto-approve all tool actions
    Installed via: irm 'https://cursor.com/install?win32=true' | iex
    """
    agent_bin = os.path.expanduser(r"~\AppData\Local\cursor-agent\agent.cmd")
    if not os.path.exists(agent_bin):
        return -1, "", (
            "Cursor agent CLI not found. "
            "Install with: irm 'https://cursor.com/install?win32=true' | iex"
        )

    # On Windows, .cmd files must be invoked via cmd /c for correct arg passing.
    # --trust and -f both bypass workspace trust prompt; place before -p so they
    # are processed before the headless mode flag.
    cmd = ["cmd", "/c", agent_bin, "--trust", "-f", "-p", instruction, "--yolo"]
    return await _run_subprocess(cmd, cwd=workspace, timeout=timeout)


async def invoke_antigravity(instruction: str, workspace: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
    """
    Antigravity worker. Adjust cmd when the actual CLI is known.
    """
    if not shutil.which("antigravity"):
        return -1, "", "antigravity CLI not found on PATH."

    cmd = ["antigravity", "run", "--prompt", instruction]
    return await _run_subprocess(cmd, cwd=workspace, timeout=timeout)


# ──────────────────────────────────────
# Main dispatcher
# ──────────────────────────────────────

_INVOKERS = {
    "claude_code": invoke_claude_code,
    "codex": invoke_codex,
    "gemini_cli": invoke_gemini_cli,
    "cursor": invoke_cursor,
    "antigravity": invoke_antigravity,
}


async def execute_worker_task(
    task_id: int,
    task_title: str,
    worker_type: str,
    instruction: str,
    workspace: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> WorkerResult:
    """
    High-level entry point.
    1. Ensure workspace is a git repo.
    2. Create feature branch.
    3. Invoke the appropriate worker CLI.
    4. Return WorkerResult.
    """
    # Ensure workspace directory exists
    Path(workspace).mkdir(parents=True, exist_ok=True)

    # Ensure git repo
    try:
        await _ensure_git_repo(workspace)
    except Exception as e:
        logger.warning(f"Git init failed for {workspace}: {e} — proceeding without branch")

    # Create feature branch
    slug = _slugify(task_title)
    branch = f"feature/task-{task_id}-{slug}"
    branch_ok = False
    try:
        branch_ok = await _git_create_branch(workspace, branch)
    except Exception as e:
        logger.warning(f"Branch creation failed: {e}")

    if not branch_ok:
        branch = "main"

    # Invoke worker
    invoker = _INVOKERS.get(worker_type)
    if invoker is None:
        return WorkerResult(
            success=False,
            output="",
            error=f"Unknown worker type: {worker_type}",
            branch=branch,
            exit_code=-1,
        )

    logger.info(f"Dispatching task {task_id} to {worker_type} on branch {branch}")
    exit_code, stdout, stderr = await invoker(instruction, workspace, timeout)
    success = exit_code == 0

    return WorkerResult(
        success=success,
        output=stdout,
        error=stderr,
        branch=branch,
        exit_code=exit_code,
    )


# ──────────────────────────────────────
# Dependency-aware parallel dispatch
# ──────────────────────────────────────

def resolve_execution_phases(tasks: list) -> list[list]:
    """
    Topological sort → return ordered phases.
    Each phase is a list of task dicts that can run in parallel.
    tasks: list of dicts with 'id' and 'dependencies' (list of task ids).
    """
    id_to_task = {t["id"]: t for t in tasks}
    completed = set()
    phases = []

    remaining = list(tasks)
    while remaining:
        # Find tasks whose dependencies are all completed
        ready = [
            t for t in remaining
            if all(dep in completed for dep in (t.get("dependencies") or []))
        ]
        if not ready:
            # Circular or unresolvable — dump the rest as one phase
            phases.append(remaining)
            break
        phases.append(ready)
        for t in ready:
            completed.add(t["id"])
            remaining.remove(t)

    return phases
