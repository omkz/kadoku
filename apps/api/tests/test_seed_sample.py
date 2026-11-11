"""Local and staging sample data: safety, provenance, idempotence."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.models import Occasion, Order, Product, Recipient
from app.seed_sample import seed_sample_for_account
from app.seed_scenarios import DAYS_AGO, _ensure_demo_target


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(settings, "staging_demo_seed_enabled", False)


def test_sample_uses_registered_account_and_is_idempotent(
    database, set_auth_role,
):
    set_auth_role("fixture-customer", "user")
    at = datetime(2026, 11, 12, tzinfo=timezone.utc)
    with database() as db:
        before_products = db.scalar(select(func.count(Product.id)))
        first = seed_sample_for_account(
            db, email=" FIXTURE-CUSTOMER@example.test ", now=at,
        )
        assert first == {
            "analytics": {"orders": len(DAYS_AGO), "recipients": 0, "occasions": 0},
            "account": {"orders": len(DAYS_AGO), "recipients": 5, "occasions": 4},
        }
        assert db.scalar(select(func.count(Order.id))) == len(DAYS_AGO) * 2
        assert db.scalar(select(func.count(Recipient.id))) == 5
        assert db.scalar(select(func.count(Occasion.id))) == 4
        assert db.scalar(select(func.count(Product.id))) == before_products
        assert db.scalar(select(text('role FROM "user" WHERE id = :id')).params(id="fixture-customer")) == "user"
        initial = {order.id: order.created_at for order in db.scalars(select(Order)).all()}
        assert all(row.paypal_order_id is None and row.paypal_capture_id is None
                   for row in db.scalars(select(Order)).all())

        repeated = seed_sample_for_account(
            db, email="fixture-customer@example.test",
            now=datetime(2026, 12, 12, tzinfo=timezone.utc),
        )
        assert repeated == {
            "analytics": {"orders": 0, "recipients": 0, "occasions": 0},
            "account": {"orders": 0, "recipients": 0, "occasions": 0},
        }
        assert {o.id: o.created_at for o in db.scalars(select(Order)).all()} == initial


def test_missing_account_has_no_side_effects(database):
    with database() as db:
        with pytest.raises(ValueError, match="Sign up through Better Auth"):
            seed_sample_for_account(db, email="missing@example.test")
        assert db.scalar(select(func.count(Order.id))) == 0
        assert db.scalar(select(func.count(Recipient.id))) == 0


def test_seed_does_not_bypass_live_or_remote_guards(database, monkeypatch):
    settings = get_settings()
    with database() as db:
        monkeypatch.setattr(settings, "environment", "production")
        with pytest.raises(RuntimeError, match="development/test"):
            seed_sample_for_account(db, email="demo@example.test")
        monkeypatch.setattr(settings, "environment", "staging")
        with pytest.raises(RuntimeError, match="STAGING_DEMO_SEED_ENABLED"):
            seed_sample_for_account(db, email="demo@example.test", target="staging")
        monkeypatch.setattr(settings, "staging_demo_seed_enabled", True)
        with pytest.raises(RuntimeError, match="PostgreSQL"):
            seed_sample_for_account(db, email="demo@example.test", target="staging")
        monkeypatch.setattr(settings, "paypal_mode", "live")
        with pytest.raises(RuntimeError, match="PAYPAL_MODE"):
            seed_sample_for_account(db, email="demo@example.test", target="staging")


def test_staging_database_host_and_name_must_match(database, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "staging")
    monkeypatch.setattr(settings, "staging_demo_seed_enabled", True)
    with database() as db:
        # Only inspect guard configuration: never execute fixture inserts
        # against this fake remote binding.
        monkeypatch.setattr(db, "get_bind", lambda **kwargs: SimpleNamespace(
            url=make_url("postgresql+psycopg://fixture:fixture@staging-db.example:5432/kadoku")
        ))
        with pytest.raises(RuntimeError, match="expected-db-host"):
            _ensure_demo_target(db, target="staging",
                                expected_db_host="production-db.example",
                                expected_db_name="kadoku")
        with pytest.raises(RuntimeError, match="expected-db-name"):
            _ensure_demo_target(db, target="staging",
                                expected_db_host="staging-db.example",
                                expected_db_name="wrong_name")
        _ensure_demo_target(db, target="staging",
                            expected_db_host="staging-db.example",
                            expected_db_name="kadoku")
