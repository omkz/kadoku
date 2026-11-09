"""Conversation refinement tests use the real FastAPI route and demo catalog."""
import pytest

from app.core.auth import optional_user
from app.main import app
from app.schemas.gifts import GiftContext
from app.services.conversation import refine_request
from app.services.gifting import Intent


def test_context_roundtrip_cheaper_and_personal(client):
    # Simulate an authenticated user so multiple paid-model-free turns are allowed.
    app.dependency_overrides[optional_user] = lambda: "user-conversation"
    initial = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "My mom loves gardening. Birthday present, budget $100.",
    })
    assert initial.status_code == 200, initial.text
    first = initial.json()
    assert first["context"]["budget_minor"] == 10000
    assert "gardening" in first["context"]["interests"]
    assert first["context"]["top_pick_price_minor"] == first["recommendations"][0]["price_minor"]

    cheaper = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Make it cheaper",
        "context": first["context"],
    })
    assert cheaper.status_code == 200, cheaper.text
    second = cheaper.json()
    assert second["recommendations"]
    assert all(g["price_minor"] < first["recommendations"][0]["price_minor"] for g in second["recommendations"])
    assert second["context"]["budget_minor"] < first["context"]["top_pick_price_minor"]

    personal = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Something more personal",
        "context": first["context"],
    })
    assert personal.status_code == 200, personal.text
    third = personal.json()
    assert third["recommendations"][0]["name"] == "Engraved Garden Set"
    assert third["context"]["prefer_personal"] is True
    assert third["context"]["budget_minor"] == 10000
    assert third["context"]["interests"] == first["context"]["interests"]


def test_followup_keeps_exclusions_and_allows_explicit_budget_override(client):
    app.dependency_overrides[optional_user] = lambda: "user-preferences"
    first = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Birthday for my mom who loves gardening. Budget $100, no plants.",
    }).json()
    followup = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Actually, under $50",
        "context": first["context"],
    })
    assert followup.status_code == 200, followup.text
    data = followup.json()
    assert data["context"]["budget_minor"] == 5000
    assert "plants" in data["context"]["avoid"]
    assert all(g["price_minor"] <= 5000 for g in data["recommendations"])


def test_followup_does_not_invent_usd_from_idr(client):
    app.dependency_overrides[optional_user] = lambda: "user-idr"
    first = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Mom loves tea. My budget is $80.",
    }).json()
    followup = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "Budget 600 ribu rupiah",
        "context": first["context"],
    })
    assert followup.status_code == 200
    assert followup.json()["context"]["budget_minor"] == 8000


@pytest.mark.parametrize("payload", [
    {"prompt":"ok"},
    {"prompt":"Make it cheaper", "context":{"budget_minor":-10}},
    {"prompt":"Make it cheaper", "context":{"budget_minor":999999999}},
    {"prompt":"Make it cheaper", "context":{"extra":"untrusted"}},
    {"prompt":"Make it cheaper", "context":{"interests":["x"*100]}},
    {"prompt":"Make it cheaper", "context":{"avoid":["x"]*30}},
])
def test_rejects_short_initial_message_or_invalid_context(client, payload):
    assert client.post("/api/v1/gifts/recommendations", json=payload).status_code == 422


def test_context_is_optional_and_backward_compatible(client):
    r = client.post("/api/v1/gifts/recommendations", json={
        "prompt": "My mom likes tea. Budget $60.",
    })
    assert r.status_code == 200
    ctx = GiftContext.model_validate(r.json()["context"])
    assert ctx.budget_minor == 6000


def test_cheaper_without_known_top_pick_does_not_invent_discount():
    previous = GiftContext(budget_minor=7000, interests=["tea"])
    next_intent, personalized = refine_request(
        Intent(), previous, "Something cheaper",
    )
    assert next_intent.budget_minor == 7000
    assert not personalized


def test_explicit_new_usd_budget_wins_over_cheaper_command():
    previous = GiftContext(budget_minor=7000, top_pick_price_minor=6000)
    next_intent, _ = refine_request(
        Intent(budget_minor=5000), previous, "Cheaper, budget $50",
    )
    assert next_intent.budget_minor == 5000
