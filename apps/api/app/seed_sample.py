"""Seed repeatable synthetic data into an existing Better Auth test account.

No accounts, credentials, permissions, or sessions are created or changed here.
Never triggered automatically by API startup, Render deploy, or a web endpoint.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.seed_scenarios import _ensure_demo_target, seed_demo_scenarios

Target = Literal["local", "staging"]


def seed_sample_for_account(
    db: Session,
    *,
    email: str,
    target: Target = "local",
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
    now: datetime | None = None,
) -> dict[str, dict[str, int]]:
    """Add 38 anonymous dashboard orders + 38 account orders and five people.

    Both sets use stable fixture UUIDs so reruns insert no duplicates. Only
    accounts that already signed up with Better Auth may receive account
    fixtures; sample data never grants admin roles or touches actual orders.
    """
    _ensure_demo_target(
        db, target=target, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name,
    )
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise ValueError("Pass a registered test-account email with --email")

    account = db.execute(
        text('SELECT id FROM "user" WHERE lower(email) = :email'),
        {"email": normalized},
    ).first()
    if account is None:
        raise ValueError(
            "Account not found in the selected database. Sign up through Better Auth "
            "on the matching localhost/staging site before running this command."
        )
    moment = now or datetime.now(timezone.utc)
    try:
        dashboard = seed_demo_scenarios(
            db, now=moment, target=target,
            expected_db_host=expected_db_host,
            expected_db_name=expected_db_name, commit=False,
        )
        personal = seed_demo_scenarios(
            db, user_id=account.id, now=moment, target=target,
            expected_db_host=expected_db_host,
            expected_db_name=expected_db_name, commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"analytics": dashboard, "account": personal}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed synthetic dashboard + account data (never real purchases)"
    )
    parser.add_argument("--email", required=True, help="Existing Better Auth test account email")
    parser.add_argument("--target", choices=("local", "staging"), default="local")
    parser.add_argument("--confirm-demo-data", action="store_true")
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--expected-db-host", default=None)
    parser.add_argument("--expected-db-name", default=None)
    args = parser.parse_args()
    if not args.confirm_demo_data:
        parser.error("Pass --confirm-demo-data to acknowledge fictional orders")
    if args.target == "staging" and not args.confirm_staging:
        parser.error("Pass --confirm-staging for intentional staging writes")
    if args.target == "staging" and (
        not args.expected_db_host or not args.expected_db_name
    ):
        parser.error("Staging requires --expected-db-host and --expected-db-name")

    with SessionLocal() as db:
        counts = seed_sample_for_account(
            db, email=args.email, target=args.target,
            expected_db_host=args.expected_db_host,
            expected_db_name=args.expected_db_name,
        )
    print("Sample data complete (synthetic only; no PayPal calls):")
    for scope, values in counts.items():
        print(f"  {scope}: " + ", ".join(f"{key}={val}" for key, val in values.items()))
    print("Existing data, user roles, passwords, and sessions were not modified.")


if __name__ == "__main__":
    main()
