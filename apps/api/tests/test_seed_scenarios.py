"""Synthetic order scenario seed: safety, idempotency, and analytics integration."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import Occasion, Order, Product, Recipient
from app.seed_scenarios import DAYS_AGO, seed_demo_scenarios


@pytest.fixture(autouse=True)
def allow_local_demo(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")


def test_seed_orders_are_idempotent_and_all_states_are_present(database):
    now = datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    with database() as db:
        before_products = db.scalar(select(func.count(Product.id)))
        assert db.scalar(select(func.count(Order.id))) == 0
        added = seed_demo_scenarios(db, now=now)
        assert added == {"orders": len(DAYS_AGO), "recipients": 0, "occasions": 0}

        orders = db.scalars(select(Order).order_by(Order.id)).all()
        assert len(orders) == len(DAYS_AGO)
        assert {order.status for order in orders} == {
            "paid", "pending", "approval_pending", "cancelled"
        }
        assert {order.fulfillment_status for order in orders if order.status == "paid"} == {
            "unfulfilled", "processing", "shipped", "delivered"
        }
        assert all(order.shipping_address["full_name"].startswith("DEMO") for order in orders)
        assert all(order.paypal_order_id is None for order in orders)
        assert all(order.paypal_capture_id is None for order in orders)
        assert all(order.user_id is None for order in orders)
        initial = {
            row.id: (row.created_at, row.status, row.price_snapshot_minor)
            for row in orders
        }

        repeated = seed_demo_scenarios(db, now=now + timedelta(days=4))
        assert repeated == {"orders": 0, "recipients": 0, "occasions": 0}
        assert {
            row.id: (row.created_at, row.status, row.price_snapshot_minor)
            for row in db.scalars(select(Order)).all()
        } == initial
        assert db.scalar(select(func.count(Product.id))) == before_products


def test_account_scoped_scenarios_are_visible_only_to_test_user(
    database, client, token_factory,
):
    now = datetime.now(timezone.utc)
    with database() as db:
        added = seed_demo_scenarios(db, now=now, user_id="test-user-a")
        assert added == {"orders": len(DAYS_AGO), "recipients": 5, "occasions": 4}
        assert seed_demo_scenarios(db, now=now, user_id="test-user-a") == {
            "orders": 0, "recipients": 0, "occasions": 0
        }
        assert db.scalar(select(func.count(Recipient.id))) == 5
        assert db.scalar(select(func.count(Occasion.id))) == 4

    h = {"Authorization": "Bearer " + token_factory(sub="test-user-a")}
    orders = client.get("/api/v1/orders", headers=h)
    assert orders.status_code == 200, orders.text
    assert len(orders.json()) == len(DAYS_AGO)
    assert len(client.get("/api/v1/recipients", headers=h).json()) == 5
    assert len(client.get("/api/v1/occasions", headers=h).json()) == 4

    other = {"Authorization": "Bearer " + token_factory(sub="another-test-user")}
    assert client.get("/api/v1/orders", headers=other).json() == []
    assert client.get("/api/v1/recipients", headers=other).json() == []


def test_demo_orders_populate_analytics_without_customer_pii(
    database, client, token_factory, monkeypatch,
):
    monkeypatch.setattr(get_settings(), "admin_user_ids", "test-user-a")
    with database() as db:
        seed_demo_scenarios(db, now=datetime.now(timezone.utc))
    h = {"Authorization": "Bearer " + token_factory(sub="test-user-a")}
    values = []
    for days in (7, 30, 90):
        response = client.get(f"/api/v1/admin/analytics?days={days}", headers=h)
        assert response.status_code == 200, response.text
        payload = response.json()
        values.append(payload["summary"]["orders"])
        assert payload["environment"] == "sandbox"
        assert payload["summary"]["sandbox_captured_minor"] > 0
        assert payload["product_performance"]
        assert payload["daily_orders"]
        assert payload["payment_statuses"]
        assert payload["fulfillment_statuses"]
        assert "DEMO Recipient" not in response.text
        assert "shipping_address" not in response.text
    assert 0 < values[0] < values[1] < values[2] == len(DAYS_AGO)


def test_scenario_seed_fails_closed_in_production_live_or_remote(database, monkeypatch):
    settings = get_settings()
    with database() as db:
        monkeypatch.setattr(settings, "environment", "production")
        with pytest.raises(RuntimeError, match="development/test"):
            seed_demo_scenarios(db)
        monkeypatch.setattr(settings, "environment", "development")
        monkeypatch.setattr(settings, "paypal_mode", "live")
        with pytest.raises(RuntimeError, match="PAYPAL_MODE"):
            seed_demo_scenarios(db)
        monkeypatch.setattr(settings, "paypal_mode", "sandbox")
        bind = db.get_bind()
        monkeypatch.setattr(db, "get_bind", lambda **kwargs: SimpleNamespace(
            url=SimpleNamespace(host="remote.example")
        ))
        with pytest.raises(RuntimeError, match="local database"):
            seed_demo_scenarios(db)
        monkeypatch.setattr(db, "get_bind", lambda **kwargs: bind)
        assert db.scalar(select(func.count(Order.id))) == 0
