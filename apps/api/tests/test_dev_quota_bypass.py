"""Local-only quota bypass must never disable production rate limits."""
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import Settings
from app.models import RecommendationUsage
from app.services import quota


def test_development_bypass_skips_read_write_usage(database, monkeypatch):
    settings = Settings(
        environment="development",
        dev_bypass_recommendation_quota=True,
        guest_recommendations_daily=1,
        member_recommendations_daily=5,
    )
    monkeypatch.setattr(quota, "get_settings", lambda: settings)
    with database() as db:
        for _ in range(12):
            assert quota.use_recommendation(db, None, "127.0.0.1") == 1
            assert quota.use_recommendation(db, "user-1", "127.0.0.1") == 5
        assert db.scalars(select(RecommendationUsage)).all() == []


def test_production_ignores_development_bypass(database, monkeypatch):
    settings = Settings(
        environment="production",
        dev_bypass_recommendation_quota=True,
        guest_quota_secret="a-long-sufficiently-random-production-secret",
        guest_recommendations_daily=1,
        member_recommendations_daily=1,
    )
    monkeypatch.setattr(quota, "get_settings", lambda: settings)
    with database() as db:
        assert quota.use_recommendation(db, None, "127.0.0.1") == 0
        with pytest.raises(HTTPException) as guest_err:
            quota.use_recommendation(db, None, "127.0.0.1")
        assert guest_err.value.status_code == 429
        assert "Guest" in guest_err.value.detail

        assert quota.use_recommendation(db, "user-1", "127.0.0.1") == 0
        with pytest.raises(HTTPException) as member_err:
            quota.use_recommendation(db, "user-1", "127.0.0.1")
        assert member_err.value.status_code == 429
        assert "Member" in member_err.value.detail


def test_development_default_keeps_quota(database, monkeypatch):
    settings = Settings(
        environment="development",
        dev_bypass_recommendation_quota=False,
        guest_recommendations_daily=1,
    )
    monkeypatch.setattr(quota, "get_settings", lambda: settings)
    with database() as db:
        quota.use_recommendation(db, None, "127.0.0.1")
        with pytest.raises(HTTPException) as exc:
            quota.use_recommendation(db, None, "127.0.0.1")
        assert exc.value.status_code == 429
