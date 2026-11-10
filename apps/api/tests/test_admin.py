"""Admin security and real catalog/order operations over the test database."""
from sqlalchemy import select

from app.core.config import get_settings
from app.models import Order, Product


def admin_headers(token_factory):
    return {"Authorization": f"Bearer {token_factory(sub='test-user-a')}"}


def test_admin_api_fails_closed_for_guests_and_non_admins(client, token_factory, monkeypatch):
    urls = [
        "/api/v1/admin/overview",
        "/api/v1/admin/products",
        "/api/v1/admin/orders",
        "/api/v1/admin/customers",
    ]
    for url in urls:
        assert client.get(url).status_code == 401
        assert client.get(url, headers=admin_headers(token_factory)).status_code == 403

    monkeypatch.setattr(get_settings(), "admin_user_ids", "admin-another-account")
    for url in urls:
        assert client.get(url, headers=admin_headers(token_factory)).status_code == 403
    assert client.post("/api/v1/admin/products", json={
        "name": "Unauthorized gift", "description": "Not real", "category": "test",
        "price_minor": 100, "stock": 1,
    }, headers=admin_headers(token_factory)).status_code == 403


def test_admin_catalog_create_edit_disable_and_server_pagination(
    client, token_factory, monkeypatch
):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "other-user, test-user-a ")
    headers = admin_headers(token_factory)
    overview = client.get("/api/v1/admin/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["products_total"] == 100
    assert overview.json()["orders_total"] == 0

    page = client.get("/api/v1/admin/products?page_size=7", headers=headers)
    assert page.status_code == 200
    assert len(page.json()["items"]) == 7
    assert page.json()["total"] == 100
    assert client.get("/api/v1/admin/products?page_size=101", headers=headers).status_code == 422

    payload = {
        "name": "  Test Olive Gift  ", "description": "  A demo-only gift  ",
        "category": "  gifts  ", "price_minor": 2500, "stock": 3,
        "emoji": "🌿", "interests": [" Gardening ", "gardening"],
        "occasions": ["Birthday"],
    }
    created = client.post("/api/v1/admin/products", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["name"] == "Test Olive Gift"
    assert data["currency"] == "USD"
    assert data["demo_only"] is True
    assert data["interests"] == ["gardening"]
    assert data["occasions"] == ["birthday"]
    product_id = data["id"]

    filtered = client.get(
        "/api/v1/admin/products?search=olive&page_size=10", headers=headers
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["id"] == product_id

    patched = client.patch(f"/api/v1/admin/products/{product_id}", json={
        "price_minor": 3900, "stock": 0, "active": False,
        "styles": ["Personal"],
    }, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["price_minor"] == 3900
    assert patched.json()["stock"] == 0
    assert patched.json()["active"] is False
    assert patched.json()["styles"] == ["personal"]

    assert client.get("/api/v1/admin/products?active=false", headers=headers).json()["total"] == 1
    assert all(p["id"] != product_id for p in client.get("/api/v1/products").json())
    assert client.patch(f"/api/v1/admin/products/{product_id}", json={"stock": None}, headers=headers).status_code == 422
    assert client.patch(f"/api/v1/admin/products/{product_id}", json={}, headers=headers).status_code == 400
    assert client.patch("/api/v1/admin/products/does-not-exist", json={"active": False}, headers=headers).status_code == 404
    assert client.post("/api/v1/admin/products", json={
        "name": "Bad price", "description": "Invalid", "category": "test",
        "price_minor": -1, "stock": 4,
    }, headers=headers).status_code == 422
    assert client.post("/api/v1/admin/products", json={
        "name": "Not allowed", "description": "Invalid", "category": "test",
        "price_minor": 1, "stock": 4, "demo_only": False,
    }, headers=headers).status_code == 422


def test_admin_orders_list_all_buyers_without_shipping_pii(
    client, database, token_factory, monkeypatch
):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "test-user-a")
    with database() as db:
        product = db.scalar(select(Product).limit(1))
        db.add(Order(
            product_id=product.id,
            user_id="different-account-12345678",
            status="paid", currency="USD", price_snapshot_minor=4200,
            shipping_address={"full_name": "Private Buyer", "address_line_1": "Hidden"},
            paypal_order_id="sandbox-order-1",
        ))
        db.add(Order(
            product_id=product.id,
            user_id=None, status="approval_pending",
            currency="USD", price_snapshot_minor=4200,
        ))
        db.commit()

    headers = admin_headers(token_factory)
    overview = client.get("/api/v1/admin/overview", headers=headers)
    assert overview.status_code == 200
    assert overview.json()["orders_total"] == 2
    assert overview.json()["orders_paid"] == 1
    assert overview.json()["sandbox_paid_minor"] == 4200

    paid = client.get("/api/v1/admin/orders?status=paid", headers=headers)
    assert paid.status_code == 200
    assert paid.json()["total"] == 1
    order = paid.json()["items"][0]
    assert order["price_minor"] == 4200
    assert order["buyer_ref"] == "…12345678"
    assert "shipping_address" not in order
    assert "paypal_order_id" not in order

    all_rows = client.get("/api/v1/admin/orders?page_size=1", headers=headers)
    assert all_rows.status_code == 200
    assert len(all_rows.json()["items"]) == 1
    assert all_rows.json()["total"] == 2
    assert client.get("/api/v1/admin/orders?page_size=999", headers=headers).status_code == 422
    assert client.patch(f"/api/v1/admin/orders/{order['id']}", json={"status": "paid"}, headers=headers).status_code in (404, 405)



def test_admin_customers_is_paginated_and_excludes_guest_and_private_data(
    client, database, token_factory, monkeypatch
):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "test-user-a")
    with database() as db:
        product = db.scalar(select(Product).limit(1))
        db.add_all([
            Order(
                product_id=product.id, user_id="customer-11111111",
                status="paid", currency="USD", price_snapshot_minor=2500,
                shipping_address={"full_name": "Never expose this"},
                paypal_order_id="sandbox-private-1",
            ),
            Order(
                product_id=product.id, user_id="customer-11111111",
                status="pending", currency="USD", price_snapshot_minor=5000,
            ),
            Order(
                product_id=product.id, user_id="customer-22222222",
                status="paid", currency="USD", price_snapshot_minor=3300,
            ),
            Order(
                product_id=product.id, user_id=None,
                status="paid", currency="USD", price_snapshot_minor=4400,
            ),
        ])
        db.commit()

    headers = admin_headers(token_factory)
    result = client.get("/api/v1/admin/customers?page_size=1", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["total"] == 2
    assert len(result.json()["items"]) == 1
    next_page = client.get("/api/v1/admin/customers?page=2&page_size=1", headers=headers)
    assert next_page.status_code == 200
    assert next_page.json()["total"] == 2
    buyers = result.json()["items"] + next_page.json()["items"]
    assert {b["buyer_ref"] for b in buyers} == {"…11111111", "…22222222"}
    first = next(b for b in buyers if b["buyer_ref"] == "…11111111")
    assert first["orders_total"] == 2
    assert first["paid_orders"] == 1
    assert first["sandbox_paid_minor"] == 2500
    assert "email" not in first
    assert "shipping_address" not in first
    assert "user_id" not in first
    assert client.get("/api/v1/admin/customers?page_size=101", headers=headers).status_code == 422
