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
    assert "gardening" in data["recommendations"][0]["reason"].lower()
    assert all(g["price_minor"] <= 10000 for g in data["recommendations"])
    assert all(g["demo_only"] for g in data["recommendations"])
    assert data["remaining_today"] == 2


def test_guest_daily_quota_enforced(client):
    body = {"prompt":"Help me choose a birthday present under $100"}
    for _ in range(3):
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
    assert len(data) == 100
    assert all(item["stock"] > 0 for item in data)



def test_featured_products_returns_six_without_limiting_catalog(client):
    """Homepage requests six; all 100 remain available to AI and catalog users."""
    response = client.get("/api/v1/products/featured")
    assert response.status_code == 200, response.text
    featured = response.json()
    assert len(featured) == 6
    assert [p["name"] for p in featured] == [
        "Artisan Coffee Ritual",
        "Garden Lover's Box",
        "Cozy Evening Box",
        "Book Lover Bundle",
        "Handmade Tea Box",
        "Mini Watercolor Studio",
    ]
    assert len({p["id"] for p in featured}) == 6
    full_catalog = client.get("/api/v1/products")
    assert full_catalog.status_code == 200
    assert len(full_catalog.json()) == 100
    assert all(p["id"] in {product["id"] for product in full_catalog.json()} for p in featured)


def test_featured_products_replace_unavailable_picks(client, database):
    """Unavailable editorial choices are excluded; alternatives fill six slots."""
    with database() as db:
        coffee = db.query(Product).filter_by(name="Artisan Coffee Ritual").one()
        coffee.stock = 0
        garden = db.query(Product).filter_by(name="Garden Lover's Box").one()
        garden.active = False
        db.commit()

    response = client.get("/api/v1/products/featured")
    assert response.status_code == 200, response.text
    featured = response.json()
    names = [p["name"] for p in featured]
    assert len(featured) == 6
    assert names[:4] == [
        "Cozy Evening Box",
        "Book Lover Bundle",
        "Handmade Tea Box",
        "Mini Watercolor Studio",
    ]
    assert "Artisan Coffee Ritual" not in names
    assert "Garden Lover's Box" not in names
    assert len(set(names)) == 6
    assert all(p["stock"] > 0 for p in featured)
    assert len(client.get("/api/v1/products").json()) == 98

def test_checkout_requires_config(client, token_factory):
    product = client.get("/api/v1/products").json()[0]
    response = client.post("/api/v1/checkout/paypal/orders", json={"product_id":product["id"], "shipping_address":{
                               "full_name":"Demo User", "address_line_1":"123 Sample Road",
                               "city":"Surakarta", "country":"Indonesia",
                           }},
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
