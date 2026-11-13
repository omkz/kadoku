"""Provision test users through Better Auth, never by writing auth tables.

Operator-only; not part of app startup or deployment.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.seed import seed as seed_catalog
from app.seed_sample import seed_sample_for_account
from app.seed_scenarios import _ensure_demo_target


@dataclass(frozen=True)
class DemoAccount:
    label: str
    name: str
    email: str
    role: str
    password: str


ACCOUNT_SPECS = (
    ("CUSTOMER", "Demo Customer", "user"),
    ("ADMIN", "Demo Admin", "admin"),
    ("OWNER", "Super Admin", "super_admin"),
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
WEB_ENV_FILES = (
    WEB_DIR / ".env", WEB_DIR / ".env.development",
    WEB_DIR / ".env.local", WEB_DIR / ".env.development.local",
)


def local_seed_environment(
    environ: dict[str, str], *,
    api_database_url: str,
    web_env_files: tuple[Path, ...] = WEB_ENV_FILES,
) -> dict[str, str]:
    """Read local test accounts from untracked web env; refuse DB mismatches."""
    values: dict[str, str] = {}
    web_databases: set[str] = set()
    for path in web_env_files:
        if not path.is_file():
            continue
        parsed = dotenv_values(path)
        if parsed.get("AUTH_DATABASE_URL"):
            web_databases.add(str(parsed["AUTH_DATABASE_URL"]))
        values.update({key: str(value) for key, value in parsed.items()
                       if value is not None})
    if environ.get("AUTH_DATABASE_URL"):
        web_databases.add(environ["AUTH_DATABASE_URL"])
    values.update(environ)

    if len(web_databases) != 1:
        raise RuntimeError(
            "Configure the same AUTH_DATABASE_URL in the local web environment; "
            "missing or conflicting database targets"
        )
    api_url, web_url = make_url(api_database_url), make_url(next(iter(web_databases)))
    if (not api_url.drivername.startswith("postgresql")
            or not web_url.drivername.startswith("postgresql")
            or not web_url.host or web_url.host.lower() not in LOCAL_HOSTS
            or not api_url.host
            or (api_url.host.lower(), api_url.port or 5432, api_url.database)
            != (web_url.host.lower(), web_url.port or 5432, web_url.database)):
        raise RuntimeError(
            "Local FastAPI DATABASE_URL and Better Auth AUTH_DATABASE_URL "
            "must point to the same localhost PostgreSQL database"
        )

    aliases = {"CUSTOMER": "CUSTOMER", "ADMIN": "ADMIN",
               "OWNER": "SUPER_ADMIN"}
    for suffix, alias in aliases.items():
        for field in ("EMAIL", "PASSWORD", "NAME"):
            key = f"DEMO_{suffix}_{field}"
            if not values.get(key) and values.get(f"DEV_{alias}_{field}"):
                values[key] = values[f"DEV_{alias}_{field}"]
    return values



def load_accounts(*, target: str, environ: dict[str, str]) -> list[DemoAccount]:
    accounts = []
    for suffix, name, role in ACCOUNT_SPECS:
        raw_email = environ.get(f"DEMO_{suffix}_EMAIL", "")
        email = raw_email.strip().lower()
        if not email:
            raise ValueError(f"DEMO_{suffix}_EMAIL is required")
        if "@" not in email or any(char.isspace() for char in email):
            raise ValueError(f"Invalid DEMO_{suffix}_EMAIL")
        name = environ.get(f"DEMO_{suffix}_NAME", "").strip() or name
        if len(name) > 120:
            raise ValueError(f"DEMO_{suffix}_NAME must be at most 120 characters")
        password = environ.get(f"DEMO_{suffix}_PASSWORD", "")
        if len(password) < 8 or len(password) > 128:
            raise ValueError(f"DEMO_{suffix}_PASSWORD must contain 8–128 characters")
        accounts.append(DemoAccount(suffix, name, email, role, password))
    if len({entry.email for entry in accounts}) != len(accounts):
        raise ValueError("Demo user emails must be unique")
    if len({entry.password for entry in accounts}) != len(accounts):
        raise ValueError("Each demo account must have a different password")
    return accounts



def verify_auth_origin(*, target: str, auth_url: str, expected_auth_host: str | None) -> str:
    parsed = urlsplit(auth_url)
    if (not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise RuntimeError("BETTER_AUTH_URL must be an origin without credentials, path or query")
    host = parsed.hostname.lower()
    if target == "local":
        if parsed.scheme != "http" or host not in LOCAL_HOSTS:
            raise RuntimeError("Local provisioning requires http://localhost Better Auth")
    elif target == "staging":
        if (parsed.scheme != "https" or host in LOCAL_HOSTS or
                not expected_auth_host or host != expected_auth_host.strip().lower()):
            raise RuntimeError("Staging Better Auth hostname must match --expected-auth-host and use HTTPS")
    else:
        raise RuntimeError("Unknown demo seed target")
    return auth_url.rstrip("/")


def _auth_post(client: httpx.Client, origin: str, action: str, payload: dict) -> dict:
    try:
        response = client.post(
            origin + "/api/auth/" + action,
            json=payload,
            headers={"Origin": origin},
        )
    except httpx.HTTPError as exc:
        # Do not log request headers or the password payload.
        raise RuntimeError(f"Better Auth {action} request failed ({type(exc).__name__})") from None
    if response.status_code != 200:
        raise RuntimeError(
            f"Better Auth {action} returned HTTP {response.status_code}; "
            "check credentials and Better Auth logs, not raw response content"
        )
    try:
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("user"), dict):
            raise ValueError
        return data["user"]
    except (ValueError, TypeError):
        raise RuntimeError(f"Better Auth {action} returned an unexpected response") from None


def provision_demo_users(
    db: Session,
    *,
    client: httpx.Client,
    accounts: list[DemoAccount],
    target: str = "local",
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    expected_auth_host: str | None = None,
    with_business_data: bool = True,
    allow_two_accounts: bool = False,
) -> dict[str, str]:
    """Provision test roles; reuse existing users only after identity verification."""
    _ensure_demo_target(
        db, target=target, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name,
    )
    origin = verify_auth_origin(
        target=target, auth_url=get_settings().better_auth_url,
        expected_auth_host=expected_auth_host,
    )
    roles = {a.role for a in accounts}
    if not (
        (len(accounts) == 3 and roles == {"user", "admin", "super_admin"})
        or (allow_two_accounts and len(accounts) == 2 and roles == {"user", "admin"})
    ):
        raise ValueError("Expected three demo roles, or an explicitly authorized two-account staging seed")
    if len({a.email for a in accounts}) != len(accounts):
        raise ValueError("Demo account emails must be unique")

    provisioned: dict[str, str] = {}
    for account in accounts:
        existing = db.execute(
            text('SELECT id, name, role, banned FROM "user" WHERE lower(email) = :email'),
            {"email": account.email},
        ).mappings().first()
        if existing is None:
            user = _auth_post(client, origin, "sign-up/email", {
                "email": account.email, "name": account.name,
                "password": account.password,
            })
        else:
            if existing["name"] != account.name or bool(existing["banned"]):
                raise RuntimeError(
                    f"Account {account.label} already exists but is not a healthy demo identity; "
                    "refusing to change it"
                )
            try:
                user = _auth_post(client, origin, "sign-in/email", {
                    "email": account.email, "password": account.password,
                    "rememberMe": False,
                })
            except RuntimeError as exc:
                if "sign-in/email returned HTTP 401" in str(exc):
                    raise RuntimeError(
                        f"Existing {account.label} account ({account.email}) rejected the "
                        "configured password. Use its original password or choose a "
                        "new demo email in apps/web/.env. No account was overwritten."
                    ) from None
                raise
        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id:
            raise RuntimeError(f"Better Auth did not return a valid user ID for {account.label}")
        if existing is not None and user_id != existing["id"]:
            raise RuntimeError(f"Identity verification failed for {account.label}")
        # Reads DB truth; do not trust role claims or user IDs supplied by caller.
        stored = db.execute(
            text('SELECT id, name, email, role, banned FROM "user" WHERE id = :id'),
            {"id": user_id},
        ).mappings().first()
        if (stored is None or stored["name"] != account.name or
                stored["email"].lower() != account.email or stored["banned"]):
            raise RuntimeError(f"Verified demo account and database do not match: {account.label}")
        current_role = stored["role"] or "user"
        if current_role not in ("user", account.role):
            raise RuntimeError(
                f"Account {account.label} has a different role; refusing to overwrite it"
            )
        if current_role != account.role:
            result = db.execute(
                text('UPDATE "user" SET role = :role WHERE id = :id '
                     'AND name = :name AND (role IS NULL OR role = :old_role) '
                     'AND (banned IS NULL OR banned = false)'),
                {"id": user_id, "name": account.name,
                 "old_role": "user", "role": account.role},
            )
            if result.rowcount != 1:
                db.rollback()
                raise RuntimeError(f"Concurrent account change for {account.label}")
            db.commit()
        provisioned[account.label.lower()] = account.email

    if with_business_data:
        seed_catalog(db)
        seed_sample_for_account(
            db, email=provisioned["customer"], target=target,
            expected_db_host=expected_db_host, expected_db_name=expected_db_name,
        )
    return provisioned


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provision demo accounts via Better Auth (never production)"
    )
    parser.add_argument("--target", choices=["local", "staging"], default="local")
    parser.add_argument("--expected-db-host")
    parser.add_argument("--expected-db-name")
    parser.add_argument("--expected-auth-host")
    parser.add_argument("--skip-business-data", action="store_true")
    args = parser.parse_args()
    if args.target == "staging" and (
        not args.expected_db_host or not args.expected_db_name
        or not args.expected_auth_host
    ):
        parser.error(
            "Staging requires --expected-db-host, --expected-db-name, "
            "and --expected-auth-host"
        )
    try:
        with SessionLocal() as db:
            # Live Better Auth provisioning requires PostgreSQL, not test SQLite.
            if db.get_bind().dialect.name != "postgresql":
                parser.error("Demo user provisioning requires the shared PostgreSQL database")
            _ensure_demo_target(
                db, target=args.target, expected_db_host=args.expected_db_host,
                expected_db_name=args.expected_db_name,
            )
            verify_auth_origin(
                target=args.target, auth_url=get_settings().better_auth_url,
                expected_auth_host=args.expected_auth_host,
            )
            # Staging accounts come from the operator's shell, never web env files.
            if args.target == "local":
                account_env = local_seed_environment(
                    os.environ, api_database_url=str(db.get_bind().url),
                )
            else:
                account_env = os.environ
            accounts = load_accounts(target=args.target, environ=account_env)
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                provisioned = provision_demo_users(
                    db, client=client, accounts=accounts, target=args.target,
                    expected_db_host=args.expected_db_host,
                    expected_db_name=args.expected_db_name,
                    expected_auth_host=args.expected_auth_host,
                    with_business_data=not args.skip_business_data,
                )
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print("Demo identities verified and provisioned:")
    for label, email in provisioned.items():
        print(f"  {label}: {email}")
    print("Passwords were not logged. No real payments or orders were created.")


if __name__ == "__main__":
    main()
