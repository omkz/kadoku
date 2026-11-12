"""One-time operator action to promote an existing Better Auth account.

Run from a trusted API shell with DATABASE_URL configured. Never triggered
during deployment, registration, or seeding.
"""
import argparse
from sqlalchemy import text
from app.db.session import SessionLocal


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap an existing Kadoku user as super_admin")
    parser.add_argument("--email", required=True, help="Registered Better Auth account email")
    parser.add_argument("--confirm", action="store_true", help="Explicitly approve privileged role change")
    args = parser.parse_args()
    if not args.confirm:
        parser.error("Pass --confirm to authorize this role change")
    with SessionLocal() as db:
        row = db.execute(
            text('SELECT id, email FROM "user" WHERE lower(email) = lower(:email)'),
            {"email": args.email.strip()},
        ).mappings().first()
        if row is None:
            parser.error("User not found; register through Kadoku first")
        db.execute(
            text('UPDATE "user" SET role = :role WHERE id = :id'),
            {"id": row["id"], "role": "super_admin"},
        )
        db.commit()
        print(f"Super administrator granted to existing account: {row['email']}")

if __name__ == "__main__":
    main()
