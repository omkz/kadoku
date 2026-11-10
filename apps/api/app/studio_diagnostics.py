"""Safe, two-stage Gemini/LiteLLM smoke test for Kadoku Studio AI.

Run from apps/api:
    uv run --extra ai python -m app.studio_diagnostics

Sends two small, synthetic requests: plain text, then one minimal function.
Prints only the LiteLLM exception class/status and exception *type* chain.
Never prints API keys, prompts, provider response bodies or error messages.
Does not enable LiteLLM debug logs.
"""
from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Awaitable, Callable

from app.core.config import get_settings


def _exception_types(exc: BaseException) -> str:
    """A bounded diagnostic signature that does not expose exception messages."""
    types: list[str] = []
    visited: set[int] = set()
    current: BaseException | None = exc
    while current is not None and len(types) < 4 and id(current) not in visited:
        visited.add(id(current))
        types.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return " -> ".join(types)


async def _probe(
    name: str,
    params: dict[str, Any],
    completion: Callable[..., Awaitable[Any]],
) -> bool:
    try:
        response = await completion(**params)
    except Exception as exc:
        code = getattr(exc, "status_code", None)
        code = code if isinstance(code, int) else "unknown"
        print(f"{name}: FAIL | status={code} | exceptions={_exception_types(exc)}")
        return False
    choices = getattr(response, "choices", None)
    if not choices:
        print(f"{name}: FAIL | response contains no choices")
        return False
    print(f"{name}: OK")
    return True


async def run() -> int:
    settings = get_settings()
    model = (settings.studio_agent_model or settings.ai_model).strip()
    if model.startswith("gemini/"):
        provider_key = (settings.gemini_api_key or settings.google_api_key).strip()
    elif model.startswith("openai/"):
        provider_key = settings.openai_api_key.strip()
    else:
        print("Model prefix is unsupported by this diagnostic. Set STUDIO_AGENT_MODEL=gemini/<model>.")
        return 2
    if not model or not provider_key:
        print("Studio model or provider key is missing from apps/api/.env.")
        return 2

    try:
        from litellm import acompletion
        litellm_version = version("litellm")
    except (ImportError, PackageNotFoundError):
        print("LiteLLM is unavailable. Install it with: uv sync --extra ai")
        return 2

    print(f"LiteLLM: {litellm_version}")
    print(f"Model: {model}")
    print("Credential: configured (never printed)")
    base = {
        "model": model,
        "api_key": provider_key,
        "temperature": 0,
        "max_tokens": 512,
        "timeout": 25,
        "num_retries": 0,
    }
    basic = await _probe(
        "Plain text",
        {**base, "messages": [{"role": "user", "content": "Reply with just OK."}]},
        acompletion,
    )
    if not basic:
        print("Result: basic provider call failed. Check connectivity, key access, model, quota and LiteLLM compatibility before testing AG Studio tools.")
        return 1

    tool = {
        "type": "function",
        "function": {
            "name": "report_status",
            "description": "Return the status string",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
            },
        },
    }
    calling = await _probe(
        "Minimal tool calling",
        {
            **base,
            "messages": [{"role": "user", "content": "Use report_status to report OK."}],
            "tools": [tool],
            "tool_choice": "auto",
        },
        acompletion,
    )
    if not calling:
        print("Result: text works but minimal tools fail. Investigate Gemini function calling and LiteLLM adapter compatibility.")
        return 1

    print("Result: basic model and small tool requests work. The AG Studio error likely depends on its larger tool schemas, conversation, or runtime request size.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
