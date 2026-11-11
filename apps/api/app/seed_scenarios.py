"""Explicit demo scenarios for Orders, Analytics, and optional My People.

Creates *synthetic* orders, not PayPal Sandbox captures. Local development is
the default; a dedicated staging opt-in requires independent guardrails.
Never use with a production/payment-live database.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Occasion, Order, Product, Recipient


# Exercise 7/30/90-day analytics and a realistic mix of payment states.
DAYS_AGO = (
    0, 1, 1, 2, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13,
    14, 15, 17, 18, 20, 21, 23, 25, 27, 29, 32, 35,
    39, 42, 45, 48, 55, 59, 66, 70, 76, 83,
)
STATUS_CYCLE = (
    "paid", "paid", "paid", "approval_pending",
    "paid", "cancelled", "paid", "pending",
)
FULFILLMENT_CYCLE = ("unfulfilled", "processing", "shipped", "delivered")
DEMO_SHIPPING = {
    "full_name": "DEMO Recipient (fictional)",
    "address_line_1": "123 Example Street",
    "address_line_2": None,
    "city": "Sample City",
    "region": None,
    "postal_code": "00000",
    "country": "United States",
    "phone_country_code": None,
    "phone_number": None,
}
# Dates are derived from the seed date once, then left alone on reruns.
DEMO_PEOPLE = (
    ("Demo Alex", "friend", ["coffee", "books"], 7),
    ("Demo Morgan", "sibling", ["gardening", "art"], 28),
    ("Demo Taylor", "coworker", ["technology", "music"], -12),
    ("Demo Casey", "partner", ["travel", "tea"], 45),
    ("Demo Jordan", "friend", ["wellness"], None),
)


def _id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, "kadoku/dev-fixtures/v1/" + name))


def _ensure_demo_target(
    db: Session,
    *,
    target: Literal["local", "staging"] = "local",
    expected_db_host: str | None = None,
    expected_db_name: str | None = None,
) -> None:
    """Do not trust a command-line switch alone to authorize remote writes.

    Every caller, including programmatic callers, goes through these checks.
    Staging requires both opt-in environment variables and an exact database
    host/name match. These are trusted-operator CLI helpers, never HTTP routes.
    """
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        raise RuntimeError("Demo scenario seed requires PAYPAL_MODE=sandbox")
    url = db.get_bind().url
    host = (url.host or "").lower()
    local_hosts = ("", "localhost", "127.0.0.1", "::1")

    if target == "local":
        if settings.environment not in ("development", "test"):
            raise RuntimeError("Demo scenario seed is restricted to development/test locally")
        if host not in local_hosts:
            raise RuntimeError("Demo scenario seed requires a local database")
        return

    if target != "staging":
        raise RuntimeError("Unknown demo seed target")
    if settings.environment != "staging":
        raise RuntimeError("Staging seed requires ENVIRONMENT=staging")
    if not settings.staging_demo_seed_enabled:
        raise RuntimeError("Staging seed requires STAGING_DEMO_SEED_ENABLED=true")
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("Staging seed requires PostgreSQL")
    if host in local_hosts:
        raise RuntimeError("Staging seed requires an explicitly identified remote database")
    if not expected_db_host or host != expected_db_host.strip().lower():
        raise RuntimeError("Staging database host does not match --expected-db-host")
    if not expected_db_name or url.database != expected_db_name.strip():
        raise RuntimeError("Staging database name does not match --expected-db-name")


def _ensure_local_dev_database(db: Session) -> None:
    """Preserve the original development-only safety contract."""
    _ensure_demo_target(db, target="local")


def seed_demo_scenarios(
    db: Session, *, user_id: str | None = None, now: datetime | None = None,
    target: Literal["local", "staging"] = "local",
    expected_db_host: str | None = None, expected_db_name: str | None = None,
    commit: bool = True,
) -> dict[str, int]:
    """Insert only missing deterministic fixtures; never update existing rows.

    Default orders are anonymous (visible in admin, not My Orders). Passing a
    Better Auth test-account subject scopes a separate order set to that user
    and adds example people/moments for the account. Different scopes are
    separate datasets, so do not mix them on the same development database.
    """
    _ensure_demo_target(
        db, target=target, expected_db_host=expected_db_host,
        expected_db_name=expected_db_name,
    )
    if user_id is not None and (not user_id.strip() or len(user_id) > 128):
        raise ValueError("user_id must be a non-empty Better Auth subject (max 128 chars)")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    products = list(db.scalars(
        select(Product)
        .where(Product.demo_only.is_(True), Product.currency == "USD")
        .order_by(Product.category, Product.name, Product.id)
    ).all())
    if not products:
        raise RuntimeError("No demo products found. Run 'uv run python -m app.seed' first.")

    scope = ("account/" + user_id) if user_id else "analytics"
    created = {"orders": 0, "recipients": 0, "occasions": 0}

    for index, days_ago in enumerate(DAYS_AGO):
        order_id = _id(f"{scope}/order/{index:03d}")
        if db.get(Order, order_id) is not None:
            continue
        product = products[index % len(products)]
        status = STATUS_CYCLE[index % len(STATUS_CYCLE)]
        paid = status == "paid"
        # Count paid entries, rather than all statuses, so every fulfillment
        # phase (including delivered) is represented in the sample orders.
        paid_ordinal = sum(
            STATUS_CYCLE[slot % len(STATUS_CYCLE)] == "paid"
            for slot in range(index + 1)
        ) - 1
        fulfillment = (
            FULFILLMENT_CYCLE[paid_ordinal % len(FULFILLMENT_CYCLE)]
            if paid else "unfulfilled"
        )
        placed_at = now - timedelta(days=days_ago, hours=index % 18)
        shipped = fulfillment in ("shipped", "delivered")
        delivered = fulfillment == "delivered"
        db.add(Order(
            id=order_id,
            user_id=user_id,
            product_id=product.id,
            price_snapshot_minor=product.price_minor,
            currency="USD",
            status=status,
            fulfillment_status=fulfillment,
            shipping_address=dict(DEMO_SHIPPING),
            tracking_carrier="DEMO carrier" if shipped else None,
            tracking_number=f"DEMO-ONLY-{index:03d}" if shipped else None,
            shipped_at=min(placed_at + timedelta(days=1), now) if shipped else None,
            delivered_at=min(placed_at + timedelta(days=3), now) if delivered else None,
            paypal_order_id=None,
            paypal_capture_id=None,
            created_at=placed_at,
        ))
        created["orders"] += 1

    if user_id:
        for name, relation, interests, offset in DEMO_PEOPLE:
            recipient_id = _id(f"account/{user_id}/recipient/{name}")
            recipient = db.get(Recipient, recipient_id)
            display_name = name.removeprefix("Demo ")
            if recipient is None:
                db.add(Recipient(
                    id=recipient_id, user_id=user_id, name=display_name,
                    relationship=relation, interests=interests, avoids=[],
                    usual_budget_minor=7000,
                ))
                created["recipients"] += 1
            elif recipient.name == name:
                # Upgrade only the original seeded label; preserve user edits.
                recipient.name = display_name
            if offset is None:
                continue
            date = (now + timedelta(days=offset)).date()
            occasion_id = _id(f"account/{user_id}/occasion/{name}/birthday")
            if db.get(Occasion, occasion_id) is None:
                db.add(Occasion(
                    id=occasion_id, recipient_id=recipient_id, kind="birthday",
                    month=date.month, day=date.day, year=None,
                    reminder_enabled=False,
                ))
                created["occasions"] += 1

    if commit:
        db.commit()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert synthetic local demo orders and scenarios")
    parser.add_argument(
        "--confirm-demo-data", action="store_true",
        help="required: acknowledge that paid statuses are fictional, not PayPal captures",
    )
    parser.add_argument(
        "--user-id", default=None, metavar="BETTER_AUTH_SUB",
        help="optional test account id to show demo orders in My Orders and demo people in My People",
    )
    args = parser.parse_args()
    if not args.confirm_demo_data:
        parser.error("Pass --confirm-demo-data to insert fictional demo orders")
    with SessionLocal() as db:
        created = seed_demo_scenarios(db, user_id=args.user_id)
    print(
        "Demo scenarios inserted: "
        + ", ".join(f"{name}={count}" for name, count in created.items())
    )
    print("Synthetic only: no real PayPal order or capture was created.")


if __name__ == "__main__":
    main()
