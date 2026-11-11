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

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

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
    _run(sys.executable, "-m", "alembic", "upgrade", "head")
    # Better Auth owns its own tables; Alembic intentionally doesn't manage them.
    _run("pnpm", "dlx", "auth@latest", "migrate", "--yes", cwd=WEB_DIR)
    print("Reset complete. Run: uv run python -m app.db seed", flush=True)


def seed_all() -> None:
    """Idempotent demo catalog, scenarios and a proper Better Auth admin account."""
    name = _local_database_name()
    if not (WEB_DIR / ".env").is_file():
        raise RuntimeError("Create apps/web/.env before seeding (Better Auth needs it).")
    with SessionLocal() as db:
        added = seed(db)
        fixtures = seed_demo_scenarios(db)
    print(f"Products added: {added}; demo fixtures: {fixtures}", flush=True)
    env = {**os.environ, "KADOKU_EXPECTED_DB_NAME": name,
           "KADOKU_EXPECTED_DB_PORT": str(make_url(get_settings().database_url).port or 5432)}
    _run("node", "--env-file=.env", "scripts/seed-admin.mjs", cwd=WEB_DIR, env=env)
    print("Local development seed complete.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Kadoku database commands")
    parser.add_argument("command", choices=("reset", "seed"))
    args = parser.parse_args()
    try:
        (reset if args.command == "reset" else seed_all)()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
