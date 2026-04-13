"""
Notification service — currently supports Slack webhooks.
Called on project complete, project failed, and daily budget alerts.
"""
import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _get_slack_url() -> str:
    """Prefer DB-stored webhook URL over env value."""
    try:
        from app.core.database import SessionLocal
        from app.models.models import SystemSetting
        db = SessionLocal()
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == "slack_webhook").first()
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception:
        pass
    return get_settings().slack_webhook_url


async def _post_slack(payload: dict) -> None:
    url = _get_slack_url()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
    except Exception as e:
        logger.warning("Slack notification failed: %s", e)


async def notify_project_completed(project_name: str, project_id: int, total_cost: float, progress: float) -> None:
    await _post_slack({
        "text": f":white_check_mark: *Project completed*: `{project_name}`",
        "attachments": [
            {
                "color": "#2da44e",
                "fields": [
                    {"title": "Project ID", "value": str(project_id), "short": True},
                    {"title": "Progress",   "value": f"{progress:.1f}%",  "short": True},
                    {"title": "Total Cost", "value": f"${total_cost:.4f}", "short": True},
                ],
            }
        ],
    })


async def notify_project_failed(project_name: str, project_id: int, reason: str = "") -> None:
    await _post_slack({
        "text": f":x: *Project failed*: `{project_name}`",
        "attachments": [
            {
                "color": "#cf222e",
                "fields": [
                    {"title": "Project ID", "value": str(project_id), "short": True},
                    {"title": "Reason",     "value": reason[:300] or "See task logs", "short": False},
                ],
            }
        ],
    })


async def notify_budget_alert(daily_total: float, daily_budget: float) -> None:
    pct = int(daily_total / daily_budget * 100) if daily_budget else 0
    await _post_slack({
        "text": f":warning: *Daily budget alert* — {pct}% used",
        "attachments": [
            {
                "color": "#d29922",
                "fields": [
                    {"title": "Spent Today", "value": f"${daily_total:.4f}", "short": True},
                    {"title": "Daily Limit", "value": f"${daily_budget:.2f}",  "short": True},
                ],
            }
        ],
    })
