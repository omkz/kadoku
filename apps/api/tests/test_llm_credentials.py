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
    ("nebius/zai-org/GLM-5.3-Flash", "nebius_api_key", "test-nebius-secret"),
])
def test_env_settings_key_forwarded_to_litellm(
    monkeypatch, model, key_field, expected,
):
    values = {"gemini_api_key": "", "google_api_key": "", "openai_api_key": "", "nebius_api_key": ""}
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
    if model.startswith("nebius/"):
        assert captured[0]["api_base"] == "https://api.tokenfactory.nebius.com/v1"
    else:
        assert "api_base" not in captured[0]


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


def test_nebius_grounded_reply_uses_same_key_and_endpoint(monkeypatch):
    from app.integrations.llm import generate_grounded_reply

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        nebius_api_key="test-nebius-secret",
    ))
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="Artisan Coffee Ritual is a thoughtful gift for a coffee lover."),
        )])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))
    reply = asyncio.run(generate_grounded_reply(
        "nebius/zai-org/GLM-5.3-Flash",
        latest_message="Coffee gift for my friend",
        product={"name": "Artisan Coffee Ritual", "description": "Tasting set",
                 "reason": "Matches their interest in coffee.", "category": "coffee"},
        preferences={"interests": ["coffee"]},
        timeout_seconds=12, max_output_tokens=240,
    ))
    assert "Artisan Coffee Ritual" in reply
    assert len(calls) == 1
    assert calls[0]["api_key"] == "test-nebius-secret"
    assert calls[0]["api_base"] == "https://api.tokenfactory.nebius.com/v1"
    assert calls[0]["model"] == "nebius/zai-org/GLM-5.3-Flash"


def test_missing_nebius_key_falls_back_without_calling_provider(monkeypatch):
    from app.services.gifting import understand_request

    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(nebius_api_key=""))
    calls = []

    async def fake_acompletion(**kwargs):
        calls.append(kwargs)
        raise AssertionError("Provider must not be called without a Nebius key")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_acompletion))
    intent, provider = asyncio.run(understand_request(
        "Gift for my mother who loves coffee, budget $40",
        "nebius/zai-org/GLM-5.3-Flash",
        timeout_seconds=12, max_output_tokens=240,
    ))
    assert provider == "rules-fallback"
    assert intent.budget_minor == 4000
    assert "coffee" in intent.interests
    assert not calls
