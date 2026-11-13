"""Provisioning must be explicit, repeatable and privilege-safe."""
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.models import Order, Recipient
from app.seed_users import (
    DemoAccount, load_accounts, local_seed_environment,
    provision_demo_users, verify_auth_origin,
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
        assert db.scalar(select(func.count(Recipient.id))) == 6
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
    with pytest.raises(ValueError, match="DEMO_CUSTOMER_EMAIL"):
        load_accounts(target="local", environ=env)
    env["DEMO_CUSTOMER_EMAIL"]="alpha@example.test"
    env["DEMO_ADMIN_EMAIL"]="alpha@example.test"
    env["DEMO_OWNER_EMAIL"]="gamma@example.test"
    with pytest.raises(ValueError, match="unique"):
        load_accounts(target="staging", environ=env)


def test_local_and_staging_seed_require_at_least_12_characters():
    env = {
        "DEMO_CUSTOMER_EMAIL": "customer@demo.test",
        "DEMO_ADMIN_EMAIL": "admin@demo.test",
        "DEMO_OWNER_EMAIL": "owner@demo.test",
        "DEMO_CUSTOMER_PASSWORD": "customer1234",
        "DEMO_ADMIN_PASSWORD": "admin1234567",
        "DEMO_OWNER_PASSWORD": "owner1234567",
    }
    assert len(load_accounts(target="staging", environ=env)) == 3
    assert len(load_accounts(target="local", environ=env)) == 3
    env["DEMO_CUSTOMER_PASSWORD"] = "customer123"
    with pytest.raises(ValueError, match="12–128"):
        load_accounts(target="staging", environ=env)
    with pytest.raises(ValueError, match="12–128"):
        load_accounts(target="local", environ=env)




def test_two_account_staging_helper_reuses_better_auth_and_refuses_owner_role(database):
    """The API-only staging flow creates one customer and one admin, not an owner."""
    fake = FakeBetterAuth(database)
    accounts = [
        DemoAccount("ADMIN", "Kadoku Admin", "admin@kadoku.test", "admin", "admin-staging-secret-12345"),
        DemoAccount("CUSTOMER", "customer", "customer@kadoku.test", "user", "customer-staging-secret-45678"),
    ]
    with database() as db:
        with pytest.raises(ValueError, match="Expected three demo roles"):
            provision_demo_users(
                db, client=fake, accounts=accounts,
                with_business_data=False,
            )
        provisioned = provision_demo_users(
            db, client=fake, accounts=accounts,
            with_business_data=False, allow_two_accounts=True,
        )
        assert set(provisioned) == {"admin", "customer"}
        assert dict(db.execute(text('SELECT email, role FROM "user"')).all()) == {
            "admin@kadoku.test": "admin", "customer@kadoku.test": "user",
        }
        assert db.scalar(select(func.count(Order.id))) == 0
        assert db.scalar(select(func.count(Recipient.id))) == 0
        again = provision_demo_users(
            db, client=fake, accounts=accounts,
            with_business_data=False, allow_two_accounts=True,
        )
        assert again == provisioned
        assert len(fake.passwords) == 2


def test_local_env_seed_reads_web_credentials_without_prompting(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AUTH_DATABASE_URL=postgresql://kadoku:pw@localhost:5432/kadoku\n"
        "DEV_CUSTOMER_EMAIL=customer@kadoku.test\n"
        "DEV_CUSTOMER_PASSWORD=customer-password-2026\n"
        "DEV_ADMIN_EMAIL=admin@kadoku.test\n"
        "DEV_ADMIN_PASSWORD=admin-password-for-2026\n"
        "DEV_ADMIN_NAME=Demo Admin\n"
        "DEV_SUPER_ADMIN_EMAIL=superadmin@kadoku.test\n"
        "DEV_SUPER_ADMIN_PASSWORD=owner-password-for-2026\n"
        "DEV_SUPER_ADMIN_NAME=Super Admin\n"
    )
    values = local_seed_environment(
        {}, api_database_url="postgresql+psycopg://kadoku:pw@localhost:5432/kadoku",
        web_env_files=(env_file,),
    )
    assert values["DEMO_OWNER_EMAIL"] == "superadmin@kadoku.test"
    assert values["DEMO_OWNER_NAME"] == "Super Admin"
    assert values["DEMO_OWNER_PASSWORD"] == "owner-password-for-2026"
    assert [u.role for u in load_accounts(target="local", environ=values)] == [
        "user", "admin", "super_admin",
    ]


def test_local_env_seed_rejects_remote_or_mismatched_db(tmp_path):
    web_env = tmp_path / ".env"
    api = "postgresql+psycopg://kadoku:pw@localhost:5432/kadoku"

    web_env.write_text("AUTH_DATABASE_URL=postgresql://kadoku:pw@other-host:5432/kadoku\n")
    with pytest.raises(RuntimeError, match="same localhost"):
        local_seed_environment({}, api_database_url=api, web_env_files=(web_env,))

    web_env.write_text("AUTH_DATABASE_URL=postgresql://kadoku:pw@localhost:5432/other_db\n")
    with pytest.raises(RuntimeError, match="same localhost"):
        local_seed_environment({}, api_database_url=api, web_env_files=(web_env,))

    web_env.write_text("AUTH_DATABASE_URL=postgresql://kadoku:pw@localhost:5432/kadoku\n")
    local_override = {"AUTH_DATABASE_URL": "postgresql://kadoku:pw@localhost:5432/not_kadoku"}
    with pytest.raises(RuntimeError, match="missing or conflicting"):
        local_seed_environment(local_override, api_database_url=api,
                               web_env_files=(web_env,))

    with pytest.raises(RuntimeError, match="missing or conflicting"):
        local_seed_environment({}, api_database_url=api,
                               web_env_files=(tmp_path / "nonexistent",))



def test_local_seed_requires_configured_email_and_password(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AUTH_DATABASE_URL=postgresql://kadoku:pw@localhost:5432/kadoku\n"
        "DEV_CUSTOMER_EMAIL=customer@kadoku.test\n"
        "DEV_CUSTOMER_PASSWORD=customer-test-password\n"
        "DEV_ADMIN_EMAIL=admin@kadoku.test\n"
        "DEV_ADMIN_PASSWORD=admin-test-password\n"
        "DEV_SUPER_ADMIN_EMAIL=superadmin@kadoku.test\n"
        "DEV_SUPER_ADMIN_PASSWORD=super-admin-test-password\n"
    )
    values = local_seed_environment(
        {}, api_database_url="postgresql+psycopg://kadoku:pw@localhost:5432/kadoku",
        web_env_files=(env_file,),
    )
    assert len(load_accounts(target="local", environ=values)) == 3
    del values["DEMO_OWNER_EMAIL"]
    with pytest.raises(ValueError, match="DEMO_OWNER_EMAIL"):
        load_accounts(target="local", environ=values)
    values["DEMO_OWNER_EMAIL"] = "superadmin@kadoku.test"
    del values["DEMO_OWNER_PASSWORD"]
    with pytest.raises(ValueError, match="DEMO_OWNER_PASSWORD"):
        load_accounts(target="local", environ=values)
