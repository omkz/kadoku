"""db:reset must never touch remote/shared databases or unrelated schemas."""
from types import SimpleNamespace

import pytest

from app.db_reset import validate_local_reset, reject_unknown_objects


LOCAL_API = "postgresql+psycopg://dev:password@localhost:5432/kadoku_dev"
LOCAL_WEB = "postgresql://dev:password@localhost:5432/kadoku_dev"


def validate(api=LOCAL_API, web=LOCAL_WEB, **options):
    return validate_local_reset(
        api, web, environment=options.get("environment", "development"),
        paypal_mode=options.get("paypal_mode", "sandbox"),
        auth_url=options.get("auth_url", "http://localhost:3000"),
    )


def test_same_local_postgres_database_accepted():
    assert validate() == "kadoku_dev"


@pytest.mark.parametrize("api, web, expected", [
    ("postgresql+psycopg://user:pass@render.com:5432/kadoku", LOCAL_WEB, "localhost"),
    (LOCAL_API, "postgresql://user:pass@db.internal:5432/kadoku_dev", "localhost"),
    (LOCAL_API, "postgresql://dev:password@localhost:5432/other", "same local"),
    (LOCAL_API, "postgresql://dev:password@localhost:5433/kadoku_dev", "same local"),
    ("sqlite:///./kadoku-dev.db", LOCAL_WEB, "PostgreSQL"),
    ("postgresql+psycopg://dev:password@localhost:5432/postgres",
     "postgresql://dev:password@localhost:5432/postgres", "dedicated"),
])
def test_db_reset_rejects_unsafe_targets(api, web, expected):
    with pytest.raises(RuntimeError, match=expected):
        validate(api, web)


def test_db_reset_rejects_non_development_environment_and_live_paypal():
    with pytest.raises(RuntimeError, match="ENVIRONMENT=development"):
        validate(environment="staging")
    with pytest.raises(RuntimeError, match="ENVIRONMENT=development"):
        validate(environment="production")
    with pytest.raises(RuntimeError, match="PAYPAL_MODE=sandbox"):
        validate(paypal_mode="live")


def test_db_reset_rejects_nonlocal_auth_and_unexpected_port():
    with pytest.raises(RuntimeError, match="localhost"):
        validate(auth_url="https://kadoku-web.onrender.com")
    with pytest.raises(RuntimeError, match="port 3000"):
        validate(auth_url="http://localhost:3001")


class FakeConnection:
    def __init__(self, *, schemas=("public",), objects=(), extensions=()):
        self.schemas, self.objects, self.extensions = schemas, objects, extensions

    def execute(self, statement):
        if "pg_namespace WHERE nspname" in statement:
            return SimpleNamespace(fetchall=lambda: [(s,) for s in self.schemas])
        if "pg_class" in statement:
            return SimpleNamespace(fetchall=lambda: [(s,) for s in self.objects])
        if "pg_extension" in statement:
            return SimpleNamespace(fetchall=lambda: [(s,) for s in self.extensions])
        raise AssertionError(f"Unexpected SQL: {statement}")


def test_schema_guard_accepts_known_tables_or_empty_schema():
    reject_unknown_objects(FakeConnection())
    reject_unknown_objects(FakeConnection(objects=("user", "account", "products", "alembic_version")))


def test_schema_guard_refuses_unknown_tables_schemas_views_and_extensions():
    with pytest.raises(RuntimeError, match="unfamiliar objects"):
        reject_unknown_objects(FakeConnection(objects=("products", "customer_ledger")))
    with pytest.raises(RuntimeError, match="non-Kadoku schemas"):
        reject_unknown_objects(FakeConnection(schemas=("public", "another_app")))
    with pytest.raises(RuntimeError, match="public-schema extensions"):
        reject_unknown_objects(FakeConnection(extensions=("uuid-ossp",)))
