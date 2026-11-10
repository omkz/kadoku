"""Privacy and aggregation regressions for AG Studio analytics data."""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.models import Order, Product


def auth_headers(token_factory, subject="test-user-a"):
    return {"Authorization": f"Bearer {token_factory(sub=subject)}"}


def test_analytics_fails_closed_and_validates_window(
    client, token_factory, monkeypatch,
):
    path = "/api/v1/admin/analytics"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=auth_headers(token_factory)).status_code == 403
    monkeypatch.setattr(get_settings(), "admin_user_ids", "test-user-a")
    h = auth_headers(token_factory)
    assert client.get(path + "?days=0", headers=h).status_code == 422
    assert client.get(path + "?days=3650", headers=h).status_code == 422
    assert client.get(path + "?days=7", headers=h).status_code == 200
    initial = client.get(path, headers=h).json()
    assert initial["environment"] == "sandbox"
    assert initial["currency"] == "USD"
    assert initial["summary"]["catalog_products"] == 100
    assert initial["summary"]["orders"] == 0
    assert len(initial["catalog"]) == 100
    assert initial["product_performance"] == []
    assert initial["daily_orders"] == []


def test_analytics_aggregates_sandbox_payments_without_exposing_pii(
    client, database, token_factory, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "test-user-a")
    with database() as db:
        product = db.scalar(select(Product).limit(1))
        now = datetime.now(timezone.utc)
        orders = [
            Order(
                product_id=product.id, price_snapshot_minor=4250,
                status="paid", fulfillment_status="unfulfilled",
                currency="USD", user_id="private-customer",
                shipping_address={
                    "full_name": "Sensitive Example Buyer",
                    "address_line_1": "Address Must Not Leak",
                    "phone_number": "99999",
                },
                paypal_order_id="SENSITIVE_PROVIDER_ORDER",
                created_at=now - timedelta(days=1),
            ),
            Order(
                product_id=product.id, price_snapshot_minor=2500,
                status="paid", fulfillment_status="shipped",
                currency="USD", created_at=now - timedelta(days=1),
            ),
            Order(
                product_id=product.id, price_snapshot_minor=1999,
                status="approval_pending", currency="USD",
                created_at=now - timedelta(days=1),
            ),
            Order(
                product_id=product.id, price_snapshot_minor=4250,
                status="cancelled", currency="USD",
                created_at=now - timedelta(days=1),
            ),
            Order(
                product_id=product.id, price_snapshot_minor=9999,
                status="paid", currency="USD",
                created_at=now - timedelta(days=50),
            ),
        ]
        db.add_all(orders)
        db.commit()
        product_id = product.id

    h = auth_headers(token_factory)
    response = client.get("/api/v1/admin/analytics?days=30", headers=h)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["orders"] == 4
    assert data["summary"]["paid_orders"] == 2
    assert data["summary"]["awaiting_fulfillment"] == 1
    assert data["summary"]["sandbox_captured_minor"] == 6750
    assert len(data["product_performance"]) == 1
    top = data["product_performance"][0]
    assert top["product_id"] == product_id
    assert top["orders"] == 4
    assert top["paid_orders"] == 2
    assert top["approval_pending"] == 1
    assert top["cancelled"] == 1
    assert top["sandbox_captured_usd"] == 67.50
    assert sum(row["orders"] for row in data["daily_orders"]) == 4
    assert {row["fulfillment_status"] for row in data["fulfillment_statuses"]} == {
        "unfulfilled", "shipped",
    }

    raw = json.dumps(data)
    for secret in (
        "Sensitive Example Buyer", "Address Must Not Leak",
        "99999", "private-customer", "SENSITIVE_PROVIDER_ORDER",
        "shipping_address", "paypal_order_id", "user_id",
    ):
        assert secret not in raw
    older = client.get("/api/v1/admin/analytics?days=90", headers=h)
    assert older.status_code == 200
    assert older.json()["summary"]["orders"] == 5
    assert older.json()["summary"]["sandbox_captured_minor"] == 16749
