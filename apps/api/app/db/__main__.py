"""Kadoku database lifecycle commands for local development and explicit staging.

Run from apps/api:
    uv run python -m app.db reset
    uv run python -m app.db seed

Staging requires --target staging, confirmation flags, matching PostgreSQL
hosts, HTTPS Better Auth origin and operator-only environment variables.
No reset or demo user seed is part of application startup/deployment.
"""
from __future__ import annotations

import argparse
import os
import httpx
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

import psycopg
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.db_reset import reject_unknown_objects
from app.seed import seed
from app.seed_scenarios import seed_demo_scenarios
from app.seed_users import DemoAccount, provision_demo_users

API_DIR = Path(__file__).resolve().parents[2]
WEB_DIR = API_DIR.parent / "web"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
SYSTEM_DATABASES = {"postgres", "template0", "template1"}


def _database_name(
    target: str = "local", *, confirmed: bool = False,
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    expected_auth_host: str | None = None,
) -> str:
    """Fail closed before using a database URL or spawning any child process."""
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        raise RuntimeError("Database helpers require PAYPAL_MODE=sandbox.")
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Database helpers require PostgreSQL.")
    host = (url.host or "").lower()
    if not url.database or url.database.lower() in SYSTEM_DATABASES or not url.username:
        raise RuntimeError("Use a dedicated application database with an explicit database user.")

    if target == "local":
        if settings.environment not in ("development", "test"):
            raise RuntimeError("Local database helpers are restricted to development/test.")
        if host not in LOCAL_HOSTS:
            raise RuntimeError("Refusing to modify a remote database in local mode.")
        if url.database not in ("kadoku", "kadoku_test"):
            raise RuntimeError("Local database must be kadoku or kadoku_test.")
        return url.database

    if target != "staging":
        raise RuntimeError("Unknown database target.")
    if settings.environment != "staging" or not confirmed:
        raise RuntimeError("Staging requires ENVIRONMENT=staging and --confirm-staging.")
    if host in LOCAL_HOSTS or not host or host != (expected_db_host or "").strip().lower():
        raise RuntimeError("Staging PostgreSQL host must match --expected-db-host exactly.")
    if url.database != (expected_db_name or "").strip():
        raise RuntimeError("Staging PostgreSQL database must match --expected-db-name exactly.")
    auth = urlsplit(settings.better_auth_url)
    if (auth.scheme != "https" or not auth.hostname or
            auth.hostname.lower() != (expected_auth_host or "").strip().lower() or
            auth.username or auth.password or auth.path not in ("", "/") or
            auth.query or auth.fragment):
        raise RuntimeError("Staging HTTPS Better Auth origin must match --expected-auth-host exactly.")
    return url.database


def _run(*args: str, cwd: Path = API_DIR, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True)


def _web_environment(target: str = "local") -> dict[str, str]:
    """Local reads .env; staging must use operator-exported shell variables."""
    if target == "local":
        values = dotenv_values(WEB_DIR / ".env")
        return {**{key: val for key, val in values.items() if val is not None}, **os.environ}
    required = ("AUTH_DATABASE_URL", "BETTER_AUTH_URL", "BETTER_AUTH_SECRET")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise RuntimeError("Staging requires shell variables: " + ", ".join(missing))
    return dict(os.environ)


def _web_seed_env(
    target: str, name: str, *, expected_db_host: str | None,
    expected_auth_host: str | None, confirmed: bool,
) -> dict[str, str]:
    settings = get_settings()
    env = _web_environment(target)
    api = make_url(settings.database_url)
    web = make_url(env["AUTH_DATABASE_URL"])
    first = ((api.host or "").lower(), api.port or 5432, api.database)
    second = ((web.host or "").lower(), web.port or 5432, web.database)
    if first != second:
        raise RuntimeError("FastAPI and Better Auth must target the same PostgreSQL host, port and database.")
    if not web.drivername.startswith("postgresql"):
        raise RuntimeError("Better Auth must use PostgreSQL.")
    if target == "staging" and env["BETTER_AUTH_URL"].rstrip("/") != settings.better_auth_url.rstrip("/"):
        raise RuntimeError("FastAPI and Better Auth staging origins disagree.")
    return {
        **env,
        "KADOKU_SEED_TARGET": target,
        "KADOKU_EXPECTED_DB_NAME": name,
        "KADOKU_EXPECTED_DB_PORT": str(api.port or 5432),
        "KADOKU_EXPECTED_DB_HOST": expected_db_host or "",
        "KADOKU_EXPECTED_AUTH_HOST": expected_auth_host or "",
        "KADOKU_CONFIRM_STAGING": "true" if confirmed else "false",
    }


def _check_web_database(env: dict[str, str], target: str) -> None:
    argv = ["node"]
    if target == "local":
        if not (WEB_DIR / ".env").is_file():
            raise RuntimeError("Create apps/web/.env before running local database commands.")
        argv.append("--env-file=.env")
    argv.extend(["scripts/seed-admin.mjs", "--check"])
    _run(*argv, cwd=WEB_DIR, env=env)


def _verify_auth_schema() -> None:
    schema = inspect(engine)
    tables = set(schema.get_table_names(schema="public"))
    missing = sorted({"user", "session", "account", "verification", "jwks"} - tables)
    if missing:
        raise RuntimeError("Better Auth migration incomplete: " + ", ".join(missing))
    columns = {col["name"] for col in schema.get_columns("user", schema="public")}
    if not {"role", "banned"}.issubset(columns):
        raise RuntimeError("Better Auth admin role/banned columns are missing")


def _apply_migrations(web_env: dict[str, str]) -> None:
    _run(sys.executable, "-m", "alembic", "upgrade", "head")
    _run("pnpm", "dlx", "auth@latest", "migrate",
         "--config", "./lib/auth.ts", "--yes", cwd=WEB_DIR, env=web_env)
    _verify_auth_schema()


def _prepare(
    target: str, *, confirmed: bool, expected_db_host: str | None,
    expected_db_name: str | None, expected_auth_host: str | None,
) -> tuple[str, dict[str, str]]:
    name = _database_name(
        target, confirmed=confirmed, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name, expected_auth_host=expected_auth_host,
    )
    if target == "staging":
        # The Render API service contains only apps/api (Python), not apps/web.
        # Better Auth provisioning goes via the deployed HTTPS web API.
        return name, {}
    env = _web_seed_env(
        target, name, expected_db_host=expected_db_host,
        expected_auth_host=expected_auth_host, confirmed=confirmed,
    )
    _check_web_database(env, target)
    return name, env


def migrate(
    target: str = "local", *, confirmed: bool = False,
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    expected_auth_host: str | None = None,
) -> None:
    """Non-destructively apply Kadoku and Better Auth migrations."""
    _, env = _prepare(
        target, confirmed=confirmed, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name, expected_auth_host=expected_auth_host,
    )
    if target == "staging":
        _run(sys.executable, "-m", "alembic", "upgrade", "head")
        # Better Auth migrations are performed by kadoku-web on its startup.
        _verify_auth_schema()
    else:
        _apply_migrations(env)
    print(f"{target} Kadoku and Better Auth migrations verified.", flush=True)


def reset(
    target: str = "local", *, confirmed: bool = False,
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    expected_auth_host: str | None = None,
    confirm_db: str | None = None,
) -> None:
    """Manually erase only the verified Kadoku schema, then reapply migrations."""
    name, env = _prepare(
        target, confirmed=confirmed, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name, expected_auth_host=expected_auth_host,
    )
    if target == "staging" and os.environ.get("STAGING_DB_RESET_ENABLED") != "true":
        raise RuntimeError("Staging reset additionally requires STAGING_DB_RESET_ENABLED=true.")
    if target == "staging":
        if confirm_db != name:
            raise RuntimeError("Staging reset requires --confirm-db with the exact database name.")
    elif confirm_db is not None and confirm_db != name:
        raise RuntimeError("Database name confirmation does not match.")

    url = make_url(get_settings().database_url)
    dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)
    engine.dispose()
    # Validate the live connection and reject any unexpected objects before
    # dropping the public schema. Both DDL statements are transactional.
    with psycopg.connect(dsn) as conn:
        actual = conn.execute("SELECT current_database()").fetchone()[0]
        if actual != name:
            raise RuntimeError("Connected database name differs from the confirmed target.")
        reject_unknown_objects(conn)
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    if target == "staging":
        _run(sys.executable, "-m", "alembic", "upgrade", "head")
        print(
            "Staging public schema reset. Restart/redeploy kadoku-web now to "
            "run Better Auth migrations; only then run app.db seed.",
            flush=True,
        )
    else:
        _apply_migrations(env)
        print("Local reset complete. Run: uv run python -m app.db seed", flush=True)



def _staging_accounts() -> list[DemoAccount]:
    """Resolve only test credentials supplied by an operator in the Shell."""
    def identity(key: str) -> str:
        value = os.environ.get(key, "").strip()
        if not value or len(value) > 320:
            raise RuntimeError(f"Set {key} explicitly for the staging demo")
        return value

    admin_email = identity("DEV_ADMIN_EMAIL").lower()
    customer_email = identity("DEV_CUSTOMER_EMAIL").lower()
    customer_name = identity("DEV_CUSTOMER_NAME")
    admin_password = os.environ.get("DEV_ADMIN_PASSWORD", "")
    customer_password = os.environ.get("DEV_CUSTOMER_PASSWORD", "")
    if any(
        "@" not in email or any(character.isspace() for character in email)
        for email in (admin_email, customer_email)
    ):
        raise RuntimeError("Staging demo users require valid email addresses")
    if admin_email == customer_email:
        raise RuntimeError("Staging admin and customer emails must differ")
    if (
        len(admin_password) < 16 or len(customer_password) < 16
        or len(admin_password) > 128 or len(customer_password) > 128
        or admin_password == customer_password
    ):
        raise RuntimeError("Use separate demo passwords of 16–128 characters")
    return [
        DemoAccount("ADMIN", "Kadoku Admin", admin_email, "admin", admin_password),
        DemoAccount("CUSTOMER", customer_name, customer_email, "user", customer_password),
    ]


def seed_all(
    target: str = "local", *, confirmed: bool = False,
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    expected_auth_host: str | None = None,
) -> None:
    """Same idempotent catalog, admin, customer, orders and people for both targets."""
    name, env = _prepare(
        target, confirmed=confirmed, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name, expected_auth_host=expected_auth_host,
    )
    if target == "staging" and os.environ.get("STAGING_DEMO_SEED_ENABLED") != "true":
        raise RuntimeError("Staging seed requires STAGING_DEMO_SEED_ENABLED=true.")
    if target == "staging":
        # All Render operations stay inside the API service and private DB.
        _run(sys.executable, "-m", "alembic", "upgrade", "head")
        _verify_auth_schema()
        accounts = _staging_accounts()
        with SessionLocal() as db:
            with httpx.Client(timeout=60.0, follow_redirects=False) as client:
                provision_demo_users(
                    db, client=client, accounts=accounts, target="staging",
                    expected_db_host=expected_db_host,
                    expected_db_name=expected_db_name,
                    expected_auth_host=expected_auth_host,
                    with_business_data=False, allow_two_accounts=True,
                )
            customer_id = db.execute(
                text('SELECT id FROM "user" WHERE lower(email) = :email'),
                {"email": accounts[1].email},
            ).scalar_one()
            added = seed(db)
            fixtures = seed_demo_scenarios(
                db, user_id=customer_id, target="staging",
                expected_db_host=expected_db_host,
                expected_db_name=expected_db_name,
            )
        print("Staging admin and customer ready (Better Auth).", flush=True)
    else:
        _apply_migrations(env)
        argv = ["node", "--env-file=.env", "scripts/seed-admin.mjs"]
        result = subprocess.run(
            argv, cwd=WEB_DIR, env=env, check=True, capture_output=True, text=True,
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
            raise RuntimeError("Better Auth seed did not return one admin user ID.")
        if len(customer_ids) != 1 or not customer_ids[0] or customer_ids[0] == admin_ids[0]:
            raise RuntimeError("Better Auth seed did not return a separate customer ID.")
        public_lines = [
            line for line in result.stdout.splitlines()
            if not line.startswith(("SEED_ADMIN_USER_ID=", "SEED_CUSTOMER_USER_ID="))
        ]
        print("\n".join(public_lines), flush=True)
        with SessionLocal() as db:
            added = seed(db)
            fixtures = seed_demo_scenarios(db, user_id=customer_ids[0])
    print(f"Products added: {added}; demo fixtures: {fixtures}", flush=True)
    print(f"{target} seed complete.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kadoku database commands (local/staging)")
    parser.add_argument("command", choices=("reset", "migrate", "seed"))
    parser.add_argument("--target", choices=("local", "staging"), default="local")
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--confirm-db", help="Exact database name confirmation for staging reset")
    parser.add_argument("--expected-db-host")
    parser.add_argument("--expected-db-name")
    parser.add_argument("--expected-auth-host")
    args = parser.parse_args()
    kwargs = dict(
        target=args.target, confirmed=args.confirm_staging,
        expected_db_host=args.expected_db_host,
        expected_db_name=args.expected_db_name,
        expected_auth_host=args.expected_auth_host,
    )
    try:
        if args.command == "reset":
            reset(**kwargs, confirm_db=args.confirm_db)
        elif args.command == "migrate":
            migrate(**kwargs)
        else:
            seed_all(**kwargs)
    except (RuntimeError, ValueError, psycopg.Error, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            parser.exit(1, f"Database helper child process failed (exit code {exc.returncode}).\n")
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
