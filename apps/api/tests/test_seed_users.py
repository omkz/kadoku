"""Provisioning must be explicit, repeatable and privilege-safe."""
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.models import Order, Recipient
from app.seed_users import (
    DemoAccount, load_accounts, provision_demo_users, verify_auth_origin,
)


class FakeResponse:
    def __init__(self, status: int, user: dict | None = None):
        self.status_code = status
        self._body = {"user": user} if user else {}

    def json(self):
        return self._body


class FakeBetterAuth:
    """Mimics Better Auth user creation/authentication, not its password hash."""
    def __init__(self, database):
        self.database = database
        self.passwords = {}
        self.calls = []

    def post(self, url, *, json, headers):
        self.calls.append((url, json["email"]))
        email = json["email"]
        if url.endswith("/sign-up/email"):
            with self.database() as db:
                row = db.execute(
                    text('SELECT id FROM "user" WHERE email = :email'),
                    {"email": email},
                ).first()
                if row is not None:
                    return FakeResponse(409)
                user_id = "better-auth-test-" + str(len(self.passwords))
                db.execute(
                    text('INSERT INTO "user" (id, name, email, role, banned) '
                         'VALUES (:id,:name,:email,:role,:banned)'),
                    {"id": user_id, "name": json["name"], "email": email,
                     "role": "user", "banned": False},
                )
                db.commit()
            self.passwords[email] = json["password"]
            return FakeResponse(200, {"id": user_id, "email": email})
        if url.endswith("/sign-in/email"):
            if self.passwords.get(email) != json["password"]:
                return FakeResponse(401)
            with self.database() as db:
                user_id = db.execute(
                    text('SELECT id FROM "user" WHERE email = :email'),
                    {"email": email},
                ).scalar_one()
            return FakeResponse(200, {"id": user_id, "email": email})
        raise AssertionError("Unexpected route: " + url)


@pytest.fixture(autouse=True)
def local_setup(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "environment", "test")
    monkeypatch.setattr(s, "better_auth_url", "http://localhost:3000")
    monkeypatch.setattr(s, "paypal_mode", "sandbox")
    monkeypatch.setattr(s, "staging_demo_seed_enabled", False)


def demo_accounts():
    return [
        DemoAccount("CUSTOMER","Demo Customer","customer@demo.test","user","customer-secret-123456789"),
        DemoAccount("ADMIN","Demo Admin","admin@demo.test","admin","admin-secret-123456789"),
        DemoAccount("OWNER","Demo Owner","owner@demo.test","super_admin","owner-secret-123456789"),
    ]


def test_creates_three_roles_through_better_auth_and_sample_data(database):
    fake = FakeBetterAuth(database)
    with database() as db:
        provisioned = provision_demo_users(
            db, client=fake, accounts=demo_accounts(),
        )
        assert set(provisioned) == {"customer","admin","owner"}
        roles = db.execute(text('SELECT email, role FROM "user" ORDER BY email')).all()
        assert {email: role for email, role in roles} == {
            "customer@demo.test": "user",
            "admin@demo.test": "admin",
            "owner@demo.test": "super_admin",
        }
        assert db.scalar(select(func.count(Order.id))) == 76
        assert db.scalar(select(func.count(Recipient.id))) == 5
        repeated = provision_demo_users(db, client=fake, accounts=demo_accounts())
        assert repeated == provisioned
        assert db.scalar(select(func.count(Order.id))) == 76
        assert len(fake.passwords) == 3
        assert [action.rsplit("/",1)[-1] for action,_ in fake.calls] == (
            ["email"] * 6  # sign-up/email first, sign-in/email on rerun
        )


def test_password_mismatch_never_promotes_existing_account(database):
    fake = FakeBetterAuth(database)
    with database() as db:
        provision_demo_users(db, client=fake, accounts=demo_accounts(),
                             with_business_data=False)
        bad = demo_accounts()
        bad[1] = DemoAccount("ADMIN","Demo Admin","admin@demo.test","admin","wrong-password-but-long")
        with pytest.raises(RuntimeError, match="HTTP 401"):
            provision_demo_users(db, client=fake, accounts=bad,
                                 with_business_data=False)
        assert db.scalar(text('SELECT role FROM "user" WHERE email = :email').bindparams(
            email="admin@demo.test"
        )) == "admin"


def test_no_automatic_adoption_of_preexisting_non_demo_user(database):
    with database() as db:
        db.execute(
            text('INSERT INTO "user" (id, name, email, role, banned) '
                 'VALUES (:id,:name,:email,:role,:banned)'),
            {"id":"stranger","name":"Actual Customer", "email":"owner@demo.test",
             "role":"user","banned":False},
        )
        db.commit()
        with pytest.raises(RuntimeError, match="not a healthy demo identity"):
            provision_demo_users(db, client=FakeBetterAuth(database),
                                 accounts=demo_accounts(),
                                 with_business_data=False)
        assert db.scalar(text('SELECT role FROM "user" WHERE id = :id').bindparams(
            id="stranger"
        )) == "user"


def test_rejects_local_nonlocalhost_and_staging_without_explicit_flags(
    database, monkeypatch,
):
    with database() as db:
        monkeypatch.setattr(get_settings(), "environment", "production")
        with pytest.raises(RuntimeError, match="development/test"):
            provision_demo_users(db, client=FakeBetterAuth(database),
                                 accounts=demo_accounts())
        monkeypatch.setattr(get_settings(), "environment", "staging")
        with pytest.raises(RuntimeError, match="STAGING_DEMO_SEED_ENABLED"):
            provision_demo_users(db, client=FakeBetterAuth(database),
                                 accounts=demo_accounts(), target="staging")
    with pytest.raises(RuntimeError, match="http://localhost"):
        verify_auth_origin(target="local",
                           auth_url="https://kadoku-web.onrender.com",
                           expected_auth_host=None)
    with pytest.raises(RuntimeError, match="HTTPS"):
        verify_auth_origin(target="staging", auth_url="http://staging.example.test",
                           expected_auth_host="staging.example.test")


def test_staging_requires_supplied_unique_accounts_and_strong_passwords():
    env = {f"DEMO_{key}_PASSWORD": f"unique-secret-for-{key}-2026"
           for key in ("CUSTOMER","ADMIN","OWNER")}
    with pytest.raises(ValueError, match="DEMO_CUSTOMER_EMAIL"):
        load_accounts(target="staging", environ=env)
    local = load_accounts(target="local", environ=env)
    assert [a.email for a in local] == [
        "customer@demo.test","admin@demo.test","owner@demo.test"
    ]
    env["DEMO_CUSTOMER_EMAIL"]="alpha@example.test"
    env["DEMO_ADMIN_EMAIL"]="alpha@example.test"
    env["DEMO_OWNER_EMAIL"]="gamma@example.test"
    with pytest.raises(ValueError, match="unique"):
        load_accounts(target="staging", environ=env)
