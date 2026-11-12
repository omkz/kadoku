"""Concierge questions and natural replies stay grounded in the demo catalog."""
import asyncio
import sys
from types import SimpleNamespace

from app.core.auth import optional_user
from app.main import app
from app.services.concierge import concierge_reply, clarification_for
from app.services.gifting import Intent


def test_clarifying_question_then_product_in_same_conversation(client):
    app.dependency_overrides[optional_user] = lambda: "concierge-test-user"
    try:
        first = client.post("/api/v1/gifts/recommendations", json={
            "prompt": "I need a present for my sister.",
        })
        assert first.status_code == 200
        first_data = first.json()
        assert first_data["clarification"]
        assert first_data["recommendations"] == []
        assert first_data["context"]["interests"] == []

        second = client.post("/api/v1/gifts/recommendations", json={
            "prompt": "She loves coffee and my budget is $60.",
            "context": first_data["context"],
        })
        assert second.status_code == 200, second.text
        data = second.json()
        assert data["clarification"] is None
        assert data["recommendations"]
        assert "coffee" in data["context"]["interests"]
        assert data["context"]["budget_minor"] == 6000
        assert data["recommendations"][0]["name"] in data["summary"]
        assert all(p["price_minor"] <= 6000 for p in data["recommendations"])
    finally:
        app.dependency_overrides.pop(optional_user, None)


def test_clarification_is_not_triggered_when_interests_known():
    assert clarification_for(Intent(interests=["coffee"])) is None
    assert clarification_for(Intent(budget_minor=5000)) is not None


def test_llm_can_write_natural_grounded_reply(monkeypatch):
    calls = []

    async def acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="I'd pick Artisan Coffee Ritual for a coffee lover. It's a thoughtful way to mark the occasion."),
        )])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=acompletion))
    product = SimpleNamespace(name="Artisan Coffee Ritual", description="Coffee tasting set", category="coffee")
    result, provider = asyncio.run(concierge_reply(
        product, "Matches their interest in coffee.", Intent(interests=["coffee"]),
        "She loves coffee", "test/model", timeout_seconds=3, max_output_tokens=180,
    ))
    assert provider == "llm"
    assert product.name in result
    assert calls[0]["model"] == "test/model"
    assert "chosen_catalog_product" in calls[0]["messages"][1]["content"]


def test_unverified_price_in_model_reply_falls_back(monkeypatch):
    async def acompletion(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop",
            message=SimpleNamespace(content="Artisan Coffee Ritual is only $999 and ships tomorrow."),
        )])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=acompletion))
    product = SimpleNamespace(name="Artisan Coffee Ritual", description="Coffee tasting set", category="coffee")
    result, provider = asyncio.run(concierge_reply(
        product, "Matches their interest in coffee.", Intent(interests=["coffee"], budget_minor=6000),
        "Gift for a coffee lover", "test/model", timeout_seconds=3, max_output_tokens=180,
    ))
    assert provider == "rules-fallback"
    assert "$999" not in result
    assert product.name in result
