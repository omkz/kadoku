"""Guardrails for the shared local/staging app.db CLI."""
from types import SimpleNamespace

import pytest

from app.db import __main__ as cli


STAGING = dict(
    target="staging", confirmed=True,
    expected_db_host="dpg-demo.render.com",
    expected_db_name="kadoku",
    expected_auth_host="kadoku-web.onrender.com",
)


@pytest.fixture
def staging_settings(monkeypatch):
    settings = SimpleNamespace(
        environment="staging", paypal_mode="sandbox",
        database_url="postgresql+psycopg://demo:secret@dpg-demo.render.com/kadoku?sslmode=require",
        better_auth_url="https://kadoku-web.onrender.com",
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    return settings


def test_staging_uses_exact_db_and_auth_allowlist(staging_settings):
    assert cli._database_name(**STAGING) == "kadoku"


@pytest.mark.parametrize("change", [
    {"confirmed": False},
    {"expected_db_host": "another.render.com"},
    {"expected_db_name": "production"},
    {"expected_auth_host": "wrong.onrender.com"},
    {"target": "local"},
])
def test_staging_refuses_unconfirmed_or_mismatched_targets(staging_settings, change):
    with pytest.raises(RuntimeError):
        cli._database_name(**{**STAGING, **change})


def test_staging_rejects_production_and_live_payment(staging_settings):
    staging_settings.environment = "production"
    with pytest.raises(RuntimeError):
        cli._database_name(**STAGING)
    staging_settings.environment = "staging"
    staging_settings.paypal_mode = "live"
    with pytest.raises(RuntimeError):
        cli._database_name(**STAGING)


def test_staging_requires_https_auth_and_remote_postgres(staging_settings):
    staging_settings.better_auth_url = "http://kadoku-web.onrender.com"
    with pytest.raises(RuntimeError):
        cli._database_name(**STAGING)
    staging_settings.better_auth_url = "https://kadoku-web.onrender.com"
    staging_settings.database_url = "postgresql+psycopg://demo:secret@localhost/kadoku"
    with pytest.raises(RuntimeError):
        cli._database_name(**STAGING)


def test_staging_seed_requires_optin_before_db_change(staging_settings, monkeypatch):
    monkeypatch.setattr(cli, "_prepare", lambda *args, **kwargs: ("kadoku", {}))
    monkeypatch.delenv("STAGING_DEMO_SEED_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="STAGING_DEMO_SEED_ENABLED"):
        cli.seed_all(**STAGING)


def test_staging_reset_needs_two_independent_confirmations(staging_settings, monkeypatch):
    monkeypatch.setattr(cli, "_prepare", lambda *args, **kwargs: ("kadoku", {}))
    monkeypatch.delenv("STAGING_DB_RESET_ENABLED", raising=False)
    with pytest.raises(RuntimeError, match="STAGING_DB_RESET_ENABLED"):
        cli.reset(**STAGING, confirm_db="kadoku")
    monkeypatch.setenv("STAGING_DB_RESET_ENABLED", "true")
    with pytest.raises(RuntimeError, match="confirm-db"):
        cli.reset(**STAGING, confirm_db="wrong_database")


def test_staging_auth_env_must_match_api_database(staging_settings, monkeypatch):
    monkeypatch.setenv("AUTH_DATABASE_URL", "postgresql://demo:secret@other.render.com/kadoku")
    monkeypatch.setenv("BETTER_AUTH_URL", staging_settings.better_auth_url)
    monkeypatch.setenv("BETTER_AUTH_SECRET", "test-secret-not-for-real-users")
    with pytest.raises(RuntimeError, match="same PostgreSQL host"):
        cli._web_seed_env("staging", "kadoku", expected_db_host="dpg-demo.render.com",
                          expected_auth_host="kadoku-web.onrender.com", confirmed=True)



def test_staging_preparation_does_not_require_node_or_web_sources(staging_settings, monkeypatch):
    # Render's API service has only the Python project; no Next.js checkout.
    monkeypatch.setattr(cli, "_web_seed_env", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Node env used")))
    monkeypatch.setattr(cli, "_check_web_database", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Node check used")))
    name, web_env = cli._prepare(
        "staging", confirmed=True, expected_db_host="dpg-demo.render.com",
        expected_db_name="kadoku", expected_auth_host="kadoku-web.onrender.com",
    )
    assert name == "kadoku"
    assert web_env == {}


def test_staging_seed_accounts_require_distinct_strong_test_credentials(monkeypatch):
    values = {
        "DEV_ADMIN_EMAIL": "admin@kadoku.test",
        "DEV_ADMIN_PASSWORD": "a-dedicated-staging-admin-secret",
        "DEV_CUSTOMER_NAME": "customer",
        "DEV_CUSTOMER_EMAIL": "customer@kadoku.test",
        "DEV_CUSTOMER_PASSWORD": "different-customer-staging-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    accounts = cli._staging_accounts()
    assert [a.role for a in accounts] == ["admin", "user"]
    assert len(accounts) == 2
    assert accounts[0].name == "Kadoku Admin"
    assert accounts[1].name == "customer"
    monkeypatch.setenv("DEV_CUSTOMER_PASSWORD", values["DEV_ADMIN_PASSWORD"])
    with pytest.raises(RuntimeError, match="separate"):
        cli._staging_accounts()


def test_staging_migration_does_not_try_better_auth_node_cli(staging_settings, monkeypatch):
    monkeypatch.setattr(cli, "_prepare", lambda *args, **kwargs: ("kadoku", {}))
    commands = []
    monkeypatch.setattr(cli, "_run", lambda *args, **kwargs: commands.append(args))
    verified = []
    monkeypatch.setattr(cli, "_verify_auth_schema", lambda: verified.append(True))
    cli.migrate(**STAGING)
    assert len(commands) == 1
    assert commands[0][-3:] == ("alembic", "upgrade", "head")
    assert verified == [True]
