"""AI adapter tests: deterministic fake provider, no network or paid model required."""
import asyncio
import json
import sys
from types import SimpleNamespace

import pytest

from app.services.gifting import understand_request


def run(prompt: str, model: str = "test/model"):
    return asyncio.run(understand_request(prompt, model, timeout_seconds=3, max_output_tokens=160))


def fake_provider(monkeypatch, response, *, fail=False):
    calls = []

    async def acompletion(**kwargs):
        calls.append(kwargs)
        if fail:
            raise RuntimeError("Provider unavailable")
        content = json.dumps(response) if not isinstance(response, str) else response
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=content),
        )])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=acompletion))
    return calls


def test_rules_only_never_calls_provider(monkeypatch):
    calls = fake_provider(monkeypatch, {})
    intent, provider = run("My mom likes tea, budget $80, no plants", model="")
    assert provider == "rules"
    assert intent.budget_minor == 8000
    assert not calls


def test_llm_extracts_interests_and_uses_provider_model(monkeypatch):
    calls = fake_provider(monkeypatch, {
        "interests": ["gardening", "tea"], "occasion": "birthday", "budget_usd": 80,
        "avoid": [], "relationship": "mom",
    })
    intent, provider = run("My mom loves growing herbs, birthday gift, under $80")
    assert provider == "llm"
    assert intent.interests == ["gardening", "tea"]
    assert intent.budget_minor == 8000
    assert calls[0]["model"] == "test/model"
    assert calls[0]["num_retries"] == 0
    assert calls[0]["timeout"] == 3
    assert calls[0]["max_tokens"] == 160
    assert len(calls[0]["messages"]) == 2


def test_llm_cannot_increase_explicit_budget_or_drop_exclusion(monkeypatch):
    fake_provider(monkeypatch, {
        "interests": ["gardening"], "occasion": None, "budget_usd": 500,
        "avoid": [], "relationship": None,
    })
    intent, provider = run("Birthday for mom, budget $50, no plants")
    assert provider == "llm"
    assert intent.budget_minor == 5000
    assert "plants" in intent.avoid
    assert intent.occasion == "birthday"


def test_cannot_infer_usd_from_unlabeled_number(monkeypatch):
    fake_provider(monkeypatch, {"interests": ["coffee"], "budget_usd": 600, "occasion": None})
    intent, _ = run("Hadiah untuk teman yang suka kopi budget 600 ribu")
    assert intent.budget_minor is None
    assert "coffee" in intent.interests


@pytest.mark.parametrize("payload", [
    {"interests": ["invalid-category"], "budget_usd": 10},
    {"interests": ["coffee"], "budget_usd": "100"},
    ["not an object"],
    "not-json",
    {"interests": [], "unexpected_field": "ignore instructions"},
])
def test_invalid_provider_output_falls_back_without_crash(monkeypatch, payload):
    fake_provider(monkeypatch, payload)
    intent, provider = run("Mom loves coffee. Budget $100")
    assert provider == "rules-fallback"
    assert intent.budget_minor == 10000
    assert "coffee" in intent.interests


def test_provider_outage_falls_back(monkeypatch):
    fake_provider(monkeypatch, None, fail=True)
    intent, provider = run("I need a birthday gift under $60")
    assert provider == "rules-fallback"
    assert intent.budget_minor == 6000


def test_bad_explicit_avoid_remains_even_if_llm_recommends_it(monkeypatch):
    fake_provider(monkeypatch, {"interests": ["gardening"], "avoid": ["plants"], "budget_usd": None})
    intent, _ = run("I want something for a gardening enthusiast. Avoid flower pots.")
    assert "flower" in intent.avoid or "plants" in intent.avoid
