"""Destructive local-only reset; migrate before starting temporary Better Auth."""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psycopg
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.seed_users import LOCAL_HOSTS, verify_auth_origin


API_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = API_DIR.parents[1]
WEB_DIR = ROOT_DIR / "apps" / "web"
KNOWN_TABLES = frozenset({
    "alembic_version",
    "products", "recipients", "occasions", "recommendation_usage",
    "orders", "payment_events", "payment_refunds", "fulfillment_events",
    "user", "session", "account", "verification", "jwks",
})
SYSTEM_DATABASES = {"postgres", "template0", "template1"}


def validate_local_reset(
    api_database_url: str, web_database_url: str, *,
    environment: str, paypal_mode: str, auth_url: str,
) -> str:
    """Fail closed before touching PostgreSQL or launching any subprocess."""
    if environment != "development" or paypal_mode != "sandbox":
        raise RuntimeError("db:reset only supports ENVIRONMENT=development and PAYPAL_MODE=sandbox")

    api = make_url(api_database_url)
    web = make_url(web_database_url)
    for origin, url in (("FastAPI", api), ("Better Auth", web)):
        if not url.drivername.startswith("postgresql"):
            raise RuntimeError(f"{origin} must use PostgreSQL")
        if not url.host or url.host.lower() not in LOCAL_HOSTS:
            raise RuntimeError(f"{origin} must use an explicit localhost PostgreSQL hostname")
        if not url.database or url.database.lower() in SYSTEM_DATABASES:
            raise RuntimeError(f"{origin} must use a dedicated application database")
        if not url.username:
            raise RuntimeError(f"{origin} requires an explicit database user")

    first = (api.host.lower(), api.port or 5432, api.database)
    second = (web.host.lower(), web.port or 5432, web.database)
    if first != second:
        raise RuntimeError(
            "FastAPI DATABASE_URL and Better Auth AUTH_DATABASE_URL must "
            "use the exact same local host, port and database"
        )

    verify_auth_origin(target="local", auth_url=auth_url, expected_auth_host=None)
    parsed = urlsplit(auth_url)
    if parsed.port != 3000:
        raise RuntimeError("db:reset requires local Better Auth on port 3000")

    return api.database


def local_web_environment(*, environ: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Resolve and validate web DB config without accidentally using hosted env."""
    base_env = dict(os.environ if environ is None else environ)
    files = [
        WEB_DIR / ".env",
        WEB_DIR / ".env.development",
        WEB_DIR / ".env.local",
        WEB_DIR / ".env.development.local",
    ]
    merged: dict[str, str] = {}
    all_web_dbs = []
    for filepath in files:
        if not filepath.is_file():
            continue
        parsed = dotenv_values(filepath)
        value = parsed.get("AUTH_DATABASE_URL")
        if value:
            all_web_dbs.append((str(filepath.name), value))
        for key, item in parsed.items():
            if item is not None:
                merged[key] = item
    if base_env.get("AUTH_DATABASE_URL"):
        all_web_dbs.append(("shell", base_env["AUTH_DATABASE_URL"]))
        merged["AUTH_DATABASE_URL"] = base_env["AUTH_DATABASE_URL"]

    # Refuse reset when Next.js and FastAPI point to different databases.
    if not all_web_dbs:
        raise RuntimeError("Set AUTH_DATABASE_URL in apps/web/.env.local before db:reset")
    targets = {value for _, value in all_web_dbs}
    if len(targets) != 1:
        raise RuntimeError(
            "Conflicting AUTH_DATABASE_URL values in web env files or shell; "
            "make them consistent before db:reset"
        )
    web_url = all_web_dbs[0][1]
    merged.update(base_env)
    merged["AUTH_DATABASE_URL"] = web_url
    return web_url, merged


def reject_unknown_objects(conn: psycopg.Connection) -> None:
    """Keep unrelated database objects out of the scope of a destructive reset."""
    schemas = {
        x[0] for x in conn.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
            "AND nspname <> 'information_schema'"
        ).fetchall()
    }
    unknown_schemas = schemas - {"public"}
    if unknown_schemas:
        raise RuntimeError("Database has non-Kadoku schemas; refusing reset: "
                           + ", ".join(sorted(unknown_schemas)))

    relations = {
        x[0] for x in conn.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')"
        ).fetchall()
    }
    unexpected = relations - KNOWN_TABLES
    if unexpected:
        raise RuntimeError("Database contains unfamiliar objects; refusing reset: "
                           + ", ".join(sorted(unexpected)))

    extensions = [
        row[0] for row in conn.execute(
            "SELECT e.extname FROM pg_extension e JOIN pg_namespace n "
            "ON e.extnamespace=n.oid WHERE n.nspname='public'"
        ).fetchall()
    ]
    if extensions:
        raise RuntimeError("Database has public-schema extensions; refusing reset: "
                           + ", ".join(sorted(extensions)))


def check_port_free(port: int) -> None:
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.3):
                raise RuntimeError(f"Local port {port} is occupied. Stop the web/API server before db:reset.")
        except OSError:
            pass


def reset_public_schema(api_database_url: str) -> None:
    db_url = make_url(api_database_url)
    dsn = db_url.set(drivername="postgresql").render_as_string(hide_password=False)
    # Uses one transaction: DDL rolls back if PostgreSQL rejects the reset.
    with psycopg.connect(dsn) as conn:
        real_database = conn.execute("SELECT current_database()").fetchone()[0]
        if real_database != db_url.database:
            raise RuntimeError("Connected PostgreSQL database does not match configured database")
        reject_unknown_objects(conn)
        conn.execute('DROP SCHEMA IF EXISTS public CASCADE')
        conn.execute('CREATE SCHEMA public')
    print("Local public schema cleared.")


def run_checked(argv: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print("Executing:", " ".join(argv))
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def wait_for_better_auth(process: subprocess.Popen, *, origin: str, logfile) -> None:
    # Wait for a live Better Auth handler, not just the TCP port.
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        try:
            result = httpx.get(origin + "/api/auth/ok", timeout=2.0, follow_redirects=False)
            if result.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)

    logfile.flush()
    logfile.seek(0)
    tail = "\n".join(logfile.read().splitlines()[-25:])
    raise RuntimeError(
        "Temporary Next.js Better Auth server failed to start. Recent log lines:\n" + tail
    )


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DANGER: wipe a dedicated LOCAL Kadoku PostgreSQL schema, migrate and seed"
    )
    parser.add_argument(
        "--confirm-db", default=None,
        help="Non-interactive alternative to typing the database name (must match exactly)",
    )
    args = parser.parse_args()

    settings = get_settings()
    try:
        web_database_url, child_env = local_web_environment()
        dbname = validate_local_reset(
            settings.database_url, web_database_url,
            environment=settings.environment,
            paypal_mode=settings.paypal_mode,
            auth_url=settings.better_auth_url,
        )
        for program in ("npx", "npm"):
            if not shutil.which(program):
                raise RuntimeError(f"{program} must be installed before db:reset")
        if not (WEB_DIR / "node_modules" / "next").exists() and not (ROOT_DIR / "node_modules" / "next").exists():
            raise RuntimeError("Install Next.js dependencies before db:reset (pnpm install)")
        check_port_free(3000)
        check_port_free(8000)
        origin = settings.better_auth_url.rstrip("/")
        child_env["BETTER_AUTH_URL"] = origin

        # Reject unrelated objects before destructive schema operations.
        api_db = make_url(settings.database_url)
        dsn = api_db.set(drivername="postgresql").render_as_string(hide_password=False)
        with psycopg.connect(dsn) as conn:
            reject_unknown_objects(conn)

        print(
            f"\nWARNING: Permanently delete ALL Kadoku data in local PostgreSQL "
            f"database '{dbname}' at {api_db.host}:{api_db.port or 5432}."
        )
        if args.confirm_db is not None:
            confirmed = args.confirm_db
        elif sys.stdin.isatty():
            confirmed = input(f"Type the exact database name '{dbname}' to continue: ").strip()
        else:
            raise RuntimeError("Non-interactive reset requires --confirm-db DATABASE_NAME")
        if confirmed != dbname:
            raise RuntimeError("Database name confirmation did not match; nothing deleted")

        reset_public_schema(settings.database_url)
        run_checked(["uv", "run", "alembic", "upgrade", "head"],
                    cwd=API_DIR, env=child_env)
        run_checked(
            ["npx", "--yes", "auth@latest", "migrate", "--yes", "--config", "./lib/auth.ts"],
            cwd=WEB_DIR, env=child_env,
        )
        # Start temporary auth only after both schema migrations.
        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as logfile:
            process = subprocess.Popen(
                ["npm", "--workspace", "apps/web", "run", "dev", "--", "--port", "3000"],
                cwd=ROOT_DIR, env=child_env,
                stdout=logfile, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                wait_for_better_auth(process, origin=origin, logfile=logfile)
                run_checked(
                    ["uv", "run", "python", "-m", "app.seed_users", "--confirm-demo-users"],
                    cwd=API_DIR, env=child_env,
                )
            finally:
                stop_server(process)
        print("\nKadoku localhost database reset, migrated, and seeded. Start your web/API servers.")
    except (RuntimeError, OSError, psycopg.Error, subprocess.CalledProcessError) as exc:
        # Keep failures concise; never print DSNs, environment variables or secrets.
        if isinstance(exc, subprocess.CalledProcessError):
            parser.exit(1, f"db:reset step failed (exit code {exc.returncode}).\n")
        parser.exit(1, f"db:reset aborted: {exc}\n")


if __name__ == "__main__":
    main()
