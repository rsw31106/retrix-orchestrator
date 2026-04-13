import redis.asyncio as aioredis
import redis
import json
from typing import Optional, Any
from app.core.config import get_settings

settings = get_settings()

# Async redis for WebSocket pub/sub
async_redis = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)

# Sync redis for LangGraph state
sync_redis = redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


class RedisManager:
    """Manages real-time state and pub/sub for dashboard."""

    CHANNEL_PROJECT = "retrix:projects"
    CHANNEL_TASK = "retrix:tasks"
    CHANNEL_WORKER = "retrix:workers"
    CHANNEL_ALERT = "retrix:alerts"
    CHANNEL_ACTIVITY = "retrix:activity"
    CHANNEL_CONFIRMATION = "retrix:confirmations"

    @staticmethod
    async def publish_event(channel: str, event_type: str, data: dict):
        """Publish event for WebSocket subscribers."""
        message = json.dumps({
            "type": event_type,
            "data": data,
        })
        await async_redis.publish(channel, message)

    @staticmethod
    async def publish_project_update(project_id: int, data: dict):
        await RedisManager.publish_event(
            RedisManager.CHANNEL_PROJECT,
            "project_update",
            {"project_id": project_id, **data},
        )

    @staticmethod
    async def publish_task_update(project_id: int, task_id: int, data: dict):
        await RedisManager.publish_event(
            RedisManager.CHANNEL_TASK,
            "task_update",
            {"project_id": project_id, "task_id": task_id, **data},
        )

    @staticmethod
    async def publish_alert(level: str, message: str, data: dict = None):
        await RedisManager.publish_event(
            RedisManager.CHANNEL_ALERT,
            "alert",
            {"level": level, "message": message, "details": data or {}},
        )

    @staticmethod
    async def set_worker_status(worker_name: str, status: dict):
        await async_redis.hset(
            "retrix:worker_status", worker_name, json.dumps(status)
        )
        await RedisManager.publish_event(
            RedisManager.CHANNEL_WORKER,
            "worker_update",
            {"worker": worker_name, **status},
        )

    @staticmethod
    async def get_all_worker_status() -> dict:
        raw = await async_redis.hgetall("retrix:worker_status")
        return {k: json.loads(v) for k, v in raw.items()}

    @staticmethod
    async def publish_activity(actor_type: str, actor_name: str, action: str,
                               detail=None, project_id=None, task_id=None):
        """Publish activity event for real-time feed."""
        import datetime
        await RedisManager.publish_event(
            RedisManager.CHANNEL_ACTIVITY,
            "activity",
            {
                "actor_type": actor_type,
                "actor_name": actor_name,
                "action": action,
                "detail": detail,
                "project_id": project_id,
                "task_id": task_id,
                "created_at": datetime.datetime.utcnow().isoformat(),
            },
        )

    @staticmethod
    async def track_cost(model: str, input_tokens: int, output_tokens: int, cost: float):
        """Track API costs in Redis for real-time dashboard."""
        import datetime
        today = datetime.date.today().isoformat()
        pipe = async_redis.pipeline()
        pipe.hincrbyfloat(f"retrix:costs:{today}", model, cost)
        pipe.hincrbyfloat(f"retrix:costs:{today}", "total", cost)
        await pipe.execute()

    @staticmethod
    async def get_today_costs() -> dict:
        import datetime
        today = datetime.date.today().isoformat()
        raw = await async_redis.hgetall(f"retrix:costs:{today}")
        return {k: float(v) for k, v in raw.items()}
