"""
Model Pool: Unified interface for all AI model APIs.
Haiku orchestrator calls these through a single interface.
"""
import httpx
import json
import time
from typing import Optional
from dataclasses import dataclass
from app.core.config import get_settings
from app.core.redis_manager import RedisManager

settings = get_settings()


@dataclass
class ModelResponse:
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float


# Pricing per 1M tokens (input, output)
MODEL_PRICING = {
    "haiku": (1.0, 5.0),
    "deepseek_v3": (0.14, 0.28),
    "deepseek_v4": (0.30, 0.50),
    "gpt_4o_mini": (0.15, 0.60),
    "gpt_4o": (2.50, 10.0),
    "minimax": (0.0, 0.0),  # 월정액
}


def _calc_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    prices = MODEL_PRICING.get(model, (0, 0))
    return (input_tokens / 1_000_000 * prices[0]) + (output_tokens / 1_000_000 * prices[1])


class ModelPool:
    """Unified model API caller."""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=120.0)

    async def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """Route to appropriate API based on model name."""
        start = time.time()

        try:
            if model == "haiku":
                resp = await self._call_anthropic(system_prompt, user_prompt, temperature, max_tokens)
            elif model in ("deepseek_v3", "deepseek_v4"):
                resp = await self._call_deepseek(model, system_prompt, user_prompt, temperature, max_tokens)
            elif model in ("gpt_4o_mini", "gpt_4o"):
                resp = await self._call_openai(model, system_prompt, user_prompt, temperature, max_tokens)
            elif model == "minimax":
                resp = await self._call_minimax(system_prompt, user_prompt, temperature, max_tokens)
            else:
                raise ValueError(f"Unknown model: {model}")
        except Exception as e:
            raise ModelCallError(model=model, error=str(e))

        latency = (time.time() - start) * 1000
        cost = _calc_cost(model, resp["input_tokens"], resp["output_tokens"])

        # Track cost in Redis
        await RedisManager.track_cost(model, resp["input_tokens"], resp["output_tokens"], cost)

        return ModelResponse(
            content=resp["content"],
            model=model,
            input_tokens=resp["input_tokens"],
            output_tokens=resp["output_tokens"],
            cost_usd=cost,
            latency_ms=latency,
        )

    async def _call_anthropic(self, system: str, user: str, temp: float, max_tok: int) -> dict:
        resp = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": max_tok,
                "temperature": temp,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["content"][0]["text"],
            "input_tokens": data["usage"]["input_tokens"],
            "output_tokens": data["usage"]["output_tokens"],
        }

    async def _call_deepseek(self, model: str, system: str, user: str, temp: float, max_tok: int) -> dict:
        # DeepSeek uses OpenAI-compatible API
        model_name = "deepseek-chat" if model == "deepseek_v3" else "deepseek-reasoner"
        resp = await self.client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "temperature": temp,
                "max_tokens": max_tok,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": data["usage"]["prompt_tokens"],
            "output_tokens": data["usage"]["completion_tokens"],
        }

    async def _call_openai(self, model: str, system: str, user: str, temp: float, max_tok: int) -> dict:
        model_name = "gpt-4o-mini" if model == "gpt_4o_mini" else "gpt-4o"
        resp = await self.client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "temperature": temp,
                "max_tokens": max_tok,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "input_tokens": data["usage"]["prompt_tokens"],
            "output_tokens": data["usage"]["completion_tokens"],
        }

    async def _call_minimax(self, system: str, user: str, temp: float, max_tok: int) -> dict:
        # MiniMax API - adjust endpoint as needed
        resp = await self.client.post(
            "https://api.minimax.chat/v1/text/chatcompletion_v2",
            headers={
                "Authorization": f"Bearer {settings.minimax_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "MiniMax-Text-01",
                "temperature": temp,
                "max_tokens": max_tok,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})
        return {
            "content": choice.get("message", {}).get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        }

    async def close(self):
        await self.client.aclose()


class ModelCallError(Exception):
    def __init__(self, model: str, error: str):
        self.model = model
        self.error = error
        super().__init__(f"Model {model} call failed: {error}")


# Singleton
model_pool = ModelPool()
