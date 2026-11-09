from app.models import Product
from app.services.gifting import Intent, extract_intent_rules, recommend


def test_understands_gardening_budget_and_exclusion():
    intent = extract_intent_rules("Mom's birthday. She loves gardening. Budget $50, no plants.")
    assert intent.budget_minor == 5000
    assert "gardening" in intent.interests
    assert "plants" in intent.avoid
    assert intent.occasion == "birthday"


def test_recommendations_grounded_and_max_three(client):
    response = client.post("/api/v1/gifts/recommendations", json={"prompt":"My mom loves gardening. Budget $100."})
    assert response.status_code == 200, response.text
    data = response.json()
    assert 1 <= len(data["recommendations"]) <= 3
    assert data["recommendations"][0]["name"] == "Garden Lover's Box"
    assert all(g["price_minor"] <= 10000 for g in data["recommendations"])
    assert all(g["demo_only"] for g in data["recommendations"])
    assert data["remaining_today"] == 0


def test_guest_daily_quota_enforced(client):
    body = {"prompt":"Help me choose a birthday present under $100"}
    assert client.post("/api/v1/gifts/recommendations", json=body).status_code == 200
    assert client.post("/api/v1/gifts/recommendations", json=body).status_code == 429


def test_budget_filters_above_budget(client):
    response = client.post("/api/v1/gifts/recommendations", json={"prompt":"I need a $40 gift for someone who loves tea."})
    assert response.status_code == 200
    assert all(p["price_minor"] <= 4000 for p in response.json()["recommendations"])


def test_recipient_requires_login(client):
    response = client.post("/api/v1/recipients", json={"name":"Mom", "interests":["tea"]})
    assert response.status_code == 401


def test_product_catalog(client):
    data = client.get("/api/v1/products").json()
    assert len(data) == 12
    assert all(item["stock"] > 0 for item in data)


def test_checkout_requires_config(client, token_factory):
    product = client.get("/api/v1/products").json()[0]
    response = client.post("/api/v1/checkout/paypal/orders", json={"product_id":product["id"]},
                           headers={"Authorization": f"Bearer {token_factory()}"})
    assert response.status_code == 503


def test_person_and_birthday_persist_with_owner_authorization(client):
    from app.main import app
    from app.core.auth import required_user
    app.dependency_overrides[required_user] = lambda: "user-a"
    try:
        response = client.post("/api/v1/recipients", json={"name":"Mom","interests":["gardening","tea"]})
        assert response.status_code == 201, response.text
        recipient_id = response.json()["id"]
        birthday = client.post("/api/v1/occasions", json={
            "recipient_id":recipient_id,"kind":"birthday","month":2,"day":29,"reminder_enabled":False,
        })
        assert birthday.status_code == 201, birthday.text
        assert birthday.json()["year"] is None
        assert client.get("/api/v1/recipients").json()[0]["name"] == "Mom"
        assert len(client.get("/api/v1/occasions").json()) == 1
        bad = client.post("/api/v1/occasions", json={
            "recipient_id":recipient_id,"kind":"birthday","month":2,"day":30,
        })
        assert bad.status_code == 422
        app.dependency_overrides[required_user] = lambda: "user-b"
        assert client.get("/api/v1/recipients").json() == []
        assert client.get("/api/v1/occasions").json() == []
        assert client.delete(f"/api/v1/recipients/{recipient_id}").status_code == 404
    finally:
        app.dependency_overrides.pop(required_user, None)
