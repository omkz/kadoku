"""LLM adapter must honor provider keys loaded from apps/api/.env.

Pydantic Settings does not export secrets to os.environ; passing a key to
LiteLLM is necessary when the API runs via uv/uvicorn on localhost.
"""
import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from app.core import config
from app.integrations.llm import extract_intent_json


@pytest.mark.parametrize("model,key_field,expected", [
    ("gemini/gemini-2.5-flash", "gemini_api_key", "test-gemini-secret"),
    ("gemini/gemini-2.5-flash", "google_api_key", "test-google-secret"),
    ("openai/gpt-5-mini", "openai_api_key", "test-openai-secret"),
])
def test_env_settings_key_forwarded_to_litellm(
    monkeypatch, model, key_field, expected,
):
    values = {"gemini_api_key": "", "google_api_key": "", "openai_api_key": ""}
    values[key_field] = expected
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(**values))
    captured = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=json.dumps({
                    "interests": ["tea"],
                    "occasion": "birthday",
                    "budget_usd": 50,
                    "avoid": [],
                    "relationship": "mother",
                })),
            )
        ])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))
    result = asyncio.run(extract_intent_json(
        "I need a birthday gift for my mother who likes tea. $50.",
        model, timeout_seconds=12, max_output_tokens=240,
    ))
    assert result["interests"] == ["tea"]
    assert len(captured) == 1
    assert captured[0]["api_key"] == expected
    assert captured[0]["model"] == model


def test_env_settings_prefers_gemini_key_over_google_key(monkeypatch):
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        gemini_api_key="first-secret",
        google_api_key="second-secret",
        openai_api_key="",
    ))
    captured = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="{}"))
        ])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))
    asyncio.run(extract_intent_json(
        "Gift for someone who likes tea", "gemini/gemini-2.5-flash",
        timeout_seconds=12, max_output_tokens=240,
    ))
    assert captured[0]["api_key"] == "first-secret"
