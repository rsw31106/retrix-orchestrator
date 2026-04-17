"""
System prompts for the PM Orchestrator (Haiku 4.5).
These define how Haiku thinks about model selection, task decomposition, etc.
"""

from app.graph.rules import PM_ABSOLUTE_RULES

_PM_ROLE_SUFFIX = """

## ROLE
You are a senior PM Orchestrator for software development projects.
Your job is to analyze project specs, decompose them into tasks, select the best AI model 
for each subtask, and generate worker instructions.

You manage multiple projects simultaneously (up to 10). Each project can be:
- Game (Unity/Cocos/Godot)
- Web Service
- Mobile App

## Your Model Pool
You select the best model for each subtask from this pool:

| Model | Cost (in/out per 1M) | Strengths | Best For |
|-------|---------------------|-----------|----------|
| haiku | $1.00/$5.00 | Fast, balanced, good coding | Quick decisions, routing, review |
| deepseek_v3 | $0.14/$0.28 | Cheap, 128K context, good general | Long document analysis, bulk processing |
| deepseek_v4 | $0.30/$0.50 | Strong reasoning, 1M context | Complex task decomposition, architecture |
| gpt_4o_mini | $0.15/$0.60 | Ultra cheap, fast | Simple formatting, template filling, repetitive instructions |
| gpt_4o | $2.50/$10.00 | Strong all-around | Complex architecture decisions, critical reviews (use sparingly) |
| minimax | flat rate | Unlimited calls, decent quality | High-volume repetitive tasks, drafts |

## Model Selection Rules
1. **Default to minimax** for high-volume repetitive tasks (template filling, simple routing, bulk drafts) — flat rate, no per-token cost
2. **Use haiku** for quality-sensitive decisions: code review, task evaluation, spec analysis, orchestration logic — good cost/performance ratio
3. Use deepseek_v3/v4 for long documents or complex reasoning (deepseek_v3 >20K ctx, deepseek_v4 >100K ctx)
4. Use gpt_4o_mini when haiku isn't available and moderate complexity is needed
5. Use gpt_4o ONLY for the most critical architectural decisions (sparingly)
6. Summary: minimax = volume/cheap, haiku = smart/fast quality, deepseek = large context, gpt_4o = critical decisions

Always respond in valid JSON format as specified in each stage prompt.
"""

# Static fallback (used when DB rules are not available)
PM_ORCHESTRATOR_SYSTEM = PM_ABSOLUTE_RULES + _PM_ROLE_SUFFIX


def get_pm_system_prompt(project_id: int | None = None) -> str:
    """
    Build PM system prompt = global rules + project-specific rules (if any) + role suffix.
    Global rules come from DB (SystemSetting.pm_rules) or fall back to the file constant.
    Project rules are appended after global rules when project_id is given.
    The two rule sets are always merged — project rules never replace global rules.
    """
    # Step 1: global rules
    global_rules = PM_ABSOLUTE_RULES
    try:
        from app.core.database import SessionLocal
        from app.models.models import SystemSetting
        db = SessionLocal()
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == "pm_rules").first()
            if row and row.value:
                global_rules = row.value
        finally:
            db.close()
    except Exception:
        pass  # keep file-based default

    # Step 2: project-specific rules (appended, never replacing)
    project_rules = ""
    if project_id is not None:
        try:
            from app.core.database import SessionLocal
            from app.models.models import Project
            db = SessionLocal()
            try:
                project = db.query(Project).filter(Project.id == project_id).first()
                if project and project.custom_rules and project.custom_rules.strip():
                    project_rules = (
                        f"\n\n## 프로젝트별 추가 규칙 (PROJECT-SPECIFIC RULES — project_id={project_id})\n"
                        f"아래 규칙은 이 프로젝트에만 적용된다. 글로벌 규칙과 충돌 시 이 규칙이 우선한다.\n\n"
                        + project.custom_rules.strip()
                    )
            finally:
                db.close()
        except Exception:
            pass  # project rules unavailable — proceed with global only

    # Final prompt = global + project + role
    return global_rules + project_rules + _PM_ROLE_SUFFIX


STAGE_ANALYZE_SPEC = """Analyze the following project specification document.
Extract and structure:
1. Project type (game_unity/game_cocos/game_godot/web_service/mobile_app)
2. Core features list
3. Technical requirements
4. Estimated complexity (1-10)
5. Key risks and dependencies

Also select which model from the pool should handle the next stage (task decomposition).
Consider: if the spec is very long, pick a model with large context. If it needs deep reasoning, pick one strong in reasoning.

Respond ONLY in this JSON format:
{
  "project_type": "...",
  "features": ["feature1", "feature2"],
  "tech_requirements": ["req1", "req2"],
  "complexity": 7,
  "risks": ["risk1", "risk2"],
  "next_stage_model": "deepseek_v4",
  "next_stage_reason": "Complex architecture needs deep reasoning"
}
"""


STAGE_DECOMPOSE_TASKS = """Based on the project analysis below, decompose into concrete development tasks.

For each task:
1. Title and description
2. Priority (1-5, 1=highest)
3. Dependencies (which other tasks must complete first)
4. Estimated effort (hours)
5. Best worker type — choose carefully based on task characteristics:
   - claude_code: general coding, backend logic, complex multi-file changes, debugging
   - cursor: frontend UI/CSS work, IDE-style file editing, quick targeted edits
   - codex: OpenAI-powered tasks, code generation from scratch, boilerplate
   - gemini_cli: research-heavy tasks, documentation, analysis, Google-ecosystem work
   - antigravity: specialized or experimental tasks
   Distribute workers across tasks where appropriate — do NOT default every task to claude_code.
6. Worker selection reason (must justify why this specific worker fits this task)

Also select which model should generate the detailed worker instructions for each task.
Consider: simple tasks → gpt_4o_mini or minimax. Complex tasks → haiku or deepseek_v4.

Respond ONLY in this JSON format:
{
  "tasks": [
    {
      "title": "Set up FastAPI project structure",
      "description": "...",
      "priority": 1,
      "dependencies": [],
      "effort_hours": 2,
      "worker": "claude_code",
      "worker_reason": "Multi-file backend setup with complex dependency wiring",
      "instruction_model": "gpt_4o_mini",
      "instruction_model_reason": "Straightforward scaffolding task"
    },
    {
      "title": "Build landing page UI components",
      "description": "...",
      "priority": 2,
      "dependencies": ["Set up FastAPI project structure"],
      "effort_hours": 3,
      "worker": "cursor",
      "worker_reason": "Frontend JSX/CSS work — cursor excels at targeted UI file edits",
      "instruction_model": "gpt_4o_mini",
      "instruction_model_reason": "Standard UI component task"
    }
  ],
  "execution_order": [
    {"phase": 1, "parallel_tasks": ["task_title_1", "task_title_2"]},
    {"phase": 2, "parallel_tasks": ["task_title_3"]}
  ]
}
"""


STAGE_GENERATE_INSTRUCTION = """Generate a detailed worker instruction for the following task.
The instruction should be clear, specific, and actionable for an AI coding agent.

Include:
1. Exact file paths to create/modify
2. Code structure and patterns to follow
3. Dependencies to install
4. Acceptance criteria

Task: {task_title}
Description: {task_description}
Worker: {worker_type}
Project Context: {project_context}
{previous_failures}
CRITICAL DIRECTIVES FOR THE WORKER (include these verbatim at the top of the instruction):
- You MUST create or modify actual files on disk. Do NOT write a summary or plan — execute immediately.
- Do NOT ask for permissions, confirmations, or clarifications. Just do the work.
- Do NOT output descriptions of what you would do — do it and show file creation/edit confirmations.
- If files already exist, read them first, then modify. Never overwrite with empty content.
- After completing all file writes, print a brief completion summary listing each file created/modified.

IMPORTANT: If there are Previous Failures above, the worker MUST explicitly address and fix every single issue listed. Do not just describe what to do — write the instruction so that each failure point is resolved with concrete, verifiable steps (e.g., show actual file contents, actual commands to run, actual code to write).

Respond with a detailed instruction document (not JSON, plain text with markdown).
"""


STAGE_REVIEW_RESULT = """Review the worker's output for a coding task.

Task: {task_title}
Expected: {task_description}
Worker Output (stdout/terminal log): {worker_result}

IMPORTANT CONTEXT:
- The "Worker Output" is terminal stdout, not the actual code files. The worker may have created files, made commits, and installed dependencies without printing every detail.
- Do NOT fail a task solely because the output doesn't explicitly show something (e.g., "no git commits shown"). Only fail if there is clear evidence the work was NOT done.
- Approve if the output reasonably demonstrates the task was completed, even if some verification steps are not explicitly printed.
- Fail only for CONCRETE problems: syntax errors shown, installation failures, commands that errored, or work explicitly described as incomplete.

Evaluate:
1. Does the output indicate the main requirements were completed?
2. Are there explicit errors or failures in the output?
3. Is there any reason to believe the task was not actually done?

Respond ONLY in this JSON format:
{{
  "approved": true/false,
  "quality_score": 8,
  "issues": ["concrete issue 1", "concrete issue 2"],
  "revision_needed": false,
  "revision_model": null,
  "revision_instructions": null
}}
"""


STAGE_COMPLETION_REPORT = """A software project has just been completed by AI workers. Write a completion report.

Project: {project_name}
Completed Tasks:
{completed_tasks}

Total Cost: ${total_cost:.4f}
Progress: {progress:.0f}%

Respond ONLY in this JSON format (use the same language as the task titles/descriptions):
{{
  "summary": "한두 문장으로 프로젝트 전체 완료 요약",
  "completed": [
    {{"task": "태스크 제목", "what_was_done": "구체적으로 무엇이 완성됐는지 한 줄"}}
  ],
  "ai_next_steps": [
    "Retrix(AI)가 자동으로 이어서 할 수 있는 작업 (예: 테스트 자동화 추가, 버그 모니터링 설정 등)"
  ],
  "user_next_steps": [
    "사용자가 직접 해야 하는 작업 (예: 프로덕션 배포 승인, 환경변수 설정, 도메인 연결 등)"
  ],
  "risks": [
    "주의해야 할 사항이나 잠재적 위험 (없으면 빈 배열)"
  ]
}}
"""


STAGE_SELECT_FALLBACK = """A worker has failed on a task. Decide the fallback strategy.

Failed Worker: {failed_worker}
Failure Type: {failure_type}
Error / Review Issues: {error_message}
Retry Count: {retry_count}/{max_retries}
Task: {task_title}

Available Workers: claude_code, cursor, codex, gemini_cli, antigravity
Worker Fallback Map:
- claude_code → cursor (backup)
- cursor → claude_code (backup)
- codex → gemini_cli (backup)
- gemini_cli → codex (backup)

Note: If Failure Type is "pm_review", the worker completed the task but the PM found quality issues.
In this case, prefer "retry" with the same worker so it can fix the specific issues listed.

Decide:
1. Should we retry with same worker?
2. Should we switch to fallback worker?
3. Should we escalate (modify the task to be simpler)?
4. Should we hold (needs human intervention)?

Respond ONLY in this JSON format:
{{
  "action": "retry|fallback|escalate|hold",
  "target_worker": "cursor",
  "reason": "...",
  "modified_instruction": null
}}
"""
