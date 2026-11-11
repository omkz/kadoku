"""Local-only Rails-style database reset and seed commands.

Run from apps/api:
    uv run python -m app.db reset
    uv run python -m app.db seed
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.seed import seed
from app.seed_scenarios import seed_demo_scenarios

API_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = API_DIR.parent / "web"


def _local_database_name() -> str:
    settings = get_settings()
    if settings.environment not in ("development", "test"):
        raise RuntimeError("Database helpers are restricted to development/test.")
    if settings.paypal_mode != "sandbox":
        raise RuntimeError("Database helpers require PAYPAL_MODE=sandbox.")
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Database helpers require local PostgreSQL.")
    if (url.host or "").lower() not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Refusing to modify a remote database.")
    if url.database not in ("kadoku", "kadoku_test"):
        raise RuntimeError("Refusing to modify a database other than kadoku/kadoku_test.")
    return url.database


def _run(*args: str, cwd: Path = API_DIR, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def _check_web_database() -> None:
    settings = get_settings()
    url = make_url(settings.database_url)
    env = {
        **os.environ,
        "KADOKU_EXPECTED_DB_NAME": url.database or "",
        "KADOKU_EXPECTED_DB_PORT": str(url.port or 5432),
    }
    _run("node", "--env-file=.env", "scripts/seed-admin.mjs", "--check", cwd=WEB_DIR, env=env)



def _web_environment() -> dict[str, str]:
    """Provide frontend .env to Better Auth CLI (outside of Next.js runtime)."""
    values = dotenv_values(WEB_DIR / ".env")
    return {**os.environ, **{key: value for key, value in values.items() if value is not None}}


def _verify_auth_schema() -> None:
    """The migration must create all core/plugin tables in Kadoku's database."""
    schema = inspect(engine)
    tables = set(schema.get_table_names(schema="public"))
    missing = sorted({"user", "session", "account", "verification", "jwks"} - tables)
    if missing:
        raise RuntimeError("Better Auth migration incomplete: " + ", ".join(missing))
    columns = {col["name"] for col in schema.get_columns("user", schema="public")}
    if not {"role", "banned"}.issubset(columns):
        raise RuntimeError("Better Auth admin role/banned columns are missing")


def _apply_migrations() -> None:
    _run(sys.executable, "-m", "alembic", "upgrade", "head")
    _run(
        "pnpm", "dlx", "auth@latest", "migrate",
        "--config", "./lib/auth.ts", "--yes",
        cwd=WEB_DIR, env=_web_environment(),
    )
    _verify_auth_schema()


def migrate() -> None:
    """Apply both migrations to existing local DB without deleting its data."""
    _local_database_name()
    if not (WEB_DIR / ".env").is_file():
        raise RuntimeError("Create apps/web/.env before migrating.")
    _check_web_database()
    _apply_migrations()
    print("Kadoku and Better Auth migrations complete.", flush=True)


def reset() -> None:
    """Drop local Kadoku public schema and restore both app and auth tables."""
    name = _local_database_name()
    if not (WEB_DIR / ".env").is_file():
        raise RuntimeError("Create apps/web/.env before resetting (Better Auth needs it).")
    _check_web_database()
    print(f"Resetting LOCAL development database {name!r} (all data will be lost).", flush=True)
    # No postgres superuser/CREATEDB permission necessary; Kadoku owns its DB.
    engine.dispose()
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    _apply_migrations()
    print("Reset complete. Run: uv run python -m app.db seed", flush=True)


def seed_all() -> None:
    """Idempotent catalog, one admin, one buyer with recipients and orders."""
    name = _local_database_name()
    if not (WEB_DIR / ".env").is_file():
        raise RuntimeError("Create apps/web/.env before seeding (Better Auth needs it).")
    # Ensure authentication schema is present without resetting the DB.
    migrate()
    # Create both auth accounts before seeding customer-owned orders/people.
    env = {
        **os.environ,
        "KADOKU_EXPECTED_DB_NAME": name,
        "KADOKU_EXPECTED_DB_PORT": str(make_url(get_settings().database_url).port or 5432),
    }
    result = subprocess.run(
        ("node", "--env-file=.env", "scripts/seed-admin.mjs"),
        cwd=WEB_DIR, env=env, check=True, capture_output=True, text=True,
    )
    admin_ids = [
        line.removeprefix("SEED_ADMIN_USER_ID=")
        for line in result.stdout.splitlines()
        if line.startswith("SEED_ADMIN_USER_ID=")
    ]
    customer_ids = [
        line.removeprefix("SEED_CUSTOMER_USER_ID=")
        for line in result.stdout.splitlines()
        if line.startswith("SEED_CUSTOMER_USER_ID=")
    ]
    if len(admin_ids) != 1 or not admin_ids[0]:
        raise RuntimeError("Better Auth seed did not return an admin user ID")
    if len(customer_ids) != 1 or not customer_ids[0] or customer_ids[0] == admin_ids[0]:
        raise RuntimeError("Better Auth seed did not return one separate customer ID")
    public_lines = [
        line for line in result.stdout.splitlines()
        if not line.startswith(("SEED_ADMIN_USER_ID=", "SEED_CUSTOMER_USER_ID="))
    ]
    print("\n".join(public_lines), flush=True)
    with SessionLocal() as db:
        added = seed(db)
        fixtures = seed_demo_scenarios(db, user_id=customer_ids[0])
    print(f"Products added: {added}; demo fixtures: {fixtures}", flush=True)
    print("Local development seed complete.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Kadoku database commands")
    parser.add_argument("command", choices=("reset", "migrate", "seed"))
    args = parser.parse_args()
    try:
        {"reset": reset, "migrate": migrate, "seed": seed_all}[args.command]()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
