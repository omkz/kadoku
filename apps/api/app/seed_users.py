"""Provision explicitly named demo accounts using Better Auth's public signup API.

The operator must control the API database and provide each demo password in
environment variables. No direct writes to Better Auth password/account/session
tables: Better Auth creates those using its configured hashing and session flow.
This script is never called by the web service or by a deployment hook.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

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
    ("CUSTOMER", "Demo Customer", "user", "customer@demo.test"),
    ("ADMIN", "Demo Admin", "admin", "admin@demo.test"),
    ("OWNER", "Demo Owner", "super_admin", "owner@demo.test"),
)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def load_accounts(*, target: str, environ: dict[str, str]) -> list[DemoAccount]:
    accounts = []
    for suffix, name, role, local_email in ACCOUNT_SPECS:
        raw_email = environ.get(f"DEMO_{suffix}_EMAIL", "")
        email = raw_email.strip().lower()
        if not email:
            if target == "staging":
                raise ValueError(f"DEMO_{suffix}_EMAIL is required for staging")
            email = local_email
        if not email or "@" not in email or any(char.isspace() for char in email):
            raise ValueError(f"Invalid DEMO_{suffix}_EMAIL")
        password = environ.get(f"DEMO_{suffix}_PASSWORD", "")
        minimum = 12 if target == "staging" else 16
        if len(password) < minimum or len(password) > 128:
            raise ValueError(f"DEMO_{suffix}_PASSWORD must contain {minimum}–128 characters")
        accounts.append(DemoAccount(suffix, name, email, role, password))
    if len({entry.email for entry in accounts}) != len(accounts):
        raise ValueError("Demo user emails must be unique")
    if len({entry.password for entry in accounts}) != len(accounts):
        raise ValueError("Each demo account must have a different password")
    return accounts


def local_password_environment(
    environ: dict[str, str], *, interactive: bool, prompt=getpass.getpass,
) -> dict[str, str]:
    """Prompt for missing local secrets, never generating/hardcoding credentials.

    Shell-provided DEMO_*_PASSWORD values work in CI; interactive developer
    use needs only one 'pnpm db:seed' command.
    """
    values = dict(environ)
    missing = [suffix for suffix, _, _, _ in ACCOUNT_SPECS
               if not values.get(f"DEMO_{suffix}_PASSWORD")]
    if missing and not interactive:
        raise ValueError(
            "Missing demo passwords in non-interactive mode: set "
            + ", ".join(f"DEMO_{suffix}_PASSWORD" for suffix in missing)
        )
    for suffix in missing:
        password = prompt(f"Password for {suffix.lower()} demo (16+ characters): ")
        if len(password) < 16 or len(password) > 128:
            raise ValueError(f"DEMO_{suffix}_PASSWORD must contain 16–128 characters")
        confirm = prompt(f"Repeat {suffix.lower()} demo password: ")
        if password != confirm:
            raise ValueError(f"Passwords did not match for {suffix.lower()} demo")
        values[f"DEMO_{suffix}_PASSWORD"] = password
    return values


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
    """Create missing users, verify ownership of existing identities, assign roles.

    A colliding email is not automatically adopted. A previous demo identity
    can be reused only with the same email, exact demo display name, and a
    successful Better Auth password sign-in matching its stored user ID.
    """
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
            user = _auth_post(client, origin, "sign-in/email", {
                "email": account.email, "password": account.password,
                "rememberMe": False,
            })
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
        # This also creates missing demo products and analytics fixtures.
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
    parser.add_argument("--confirm-demo-users", action="store_true")
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--expected-db-host")
    parser.add_argument("--expected-db-name")
    parser.add_argument("--expected-auth-host")
    parser.add_argument("--skip-business-data", action="store_true")
    args = parser.parse_args()
    if not args.confirm_demo_users:
        parser.error("--confirm-demo-users is required")
    if args.target == "staging" and (
        not args.confirm_staging or not args.expected_db_host or
        not args.expected_db_name or not args.expected_auth_host
    ):
        parser.error(
            "Staging requires --confirm-staging, --expected-db-host, "
            "--expected-db-name, and --expected-auth-host"
        )
    try:
        with SessionLocal() as db:
            # Local interactive provisioning must share Better Auth's PostgreSQL.
            # SQLite is supported only by the isolated unit-test fixture.
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
            # Local-only interactive setup; staging always requires explicitly
            # supplied secrets and never prompts for privileged accounts.
            account_env = (
                local_password_environment(os.environ, interactive=sys.stdin.isatty())
                if args.target == "local" else os.environ
            )
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
