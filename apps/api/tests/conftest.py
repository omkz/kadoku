import os
os.environ["DATABASE_URL"] = "sqlite:///./kadoku-test-unused.db"
os.environ["GUEST_QUOTA_SECRET"] = "test-hmac-secret"
os.environ["AI_MODEL"] = ""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.seed import seed


@pytest.fixture
def database():
    engine = create_engine("sqlite://", connect_args={"check_same_thread":False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            'CREATE TABLE "user" (id TEXT PRIMARY KEY, name TEXT NOT NULL, '
            'email TEXT NOT NULL UNIQUE, role TEXT, banned BOOLEAN NOT NULL DEFAULT 0)'
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed(session)
    yield factory
    engine.dispose()


@pytest.fixture
def client(database):
    def override_db():
        with database() as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.core import auth as auth_module


@pytest.fixture
def token_factory(monkeypatch):
    """Real EdDSA JWTs; mock only the JWKS network fetch, not auth decisions."""
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    monkeypatch.setattr(auth_module, "_jwks_client", lambda issuer: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public),
    ))

    def build(**overrides):
        now = datetime.now(timezone.utc)
        claims = {
            "sub": "test-user-a", "iss": "http://localhost:3000",
            "aud": "http://localhost:3000", "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        claims.update(overrides)
        return jwt.encode(claims, private, algorithm="EdDSA", headers={"kid": "local-test-key"})

    return build

@pytest.fixture
def set_auth_role(database):
    def set_role(user_id: str, role: str, *, banned: bool = False) -> None:
        with database() as db:
            db.execute(text(
                'INSERT INTO "user" (id, name, email, role, banned) '
                'VALUES (:id, :name, :email, :role, :banned) '
                'ON CONFLICT(id) DO UPDATE SET role = :role, banned = :banned'
            ), {"id":user_id, "name":user_id, "email":f"{user_id}@example.test",
                "role":role, "banned":banned})
            db.commit()
    return set_role
