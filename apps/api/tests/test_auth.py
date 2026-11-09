"""FastAPI auth integration: signed JWT, issuer/audience, expiration, and ownership."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import auth as auth_module


@pytest.fixture
def token_factory(monkeypatch):
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
        return jwt.encode(claims, private, algorithm="EdDSA", headers={"kid":"local-test-key"})
    return build


def test_me_requires_authorization(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization":"Basic anything"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization":"Bearer wrong"}).status_code == 401


def test_valid_signed_token_loads_user(client, token_factory):
    token = token_factory()
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"user_id": "test-user-a"}
    person = client.post("/api/v1/recipients", json={"name":"Mom", "interests":["gardening"]}, headers=headers)
    assert person.status_code == 201, person.text
    other_headers = {"Authorization": f"Bearer {token_factory(sub='test-user-b')}"}
    assert client.get("/api/v1/recipients", headers=other_headers).json() == []
    assert client.delete(f"/api/v1/recipients/{person.json()['id']}", headers=other_headers).status_code == 404


@pytest.mark.parametrize("claims", [
    {"aud":"https://not-kadoku.example"},
    {"iss":"https://not-kadoku.example"},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=10)},
    {"exp": None},
    {"sub": ""},
])
def test_rejects_invalid_claims(client, token_factory, claims):
    token = token_factory(**claims)
    assert client.get("/api/v1/auth/me", headers={"Authorization":f"Bearer {token}"}).status_code == 401


def test_rejects_wrong_signature(client, token_factory):
    good_token = token_factory()
    attacker_key = Ed25519PrivateKey.generate()
    claims = jwt.decode(good_token, options={"verify_signature":False})
    malicious = jwt.encode(claims, attacker_key, algorithm="EdDSA", headers={"kid":"local-test-key"})
    assert client.get("/api/v1/auth/me", headers={"Authorization":f"Bearer {malicious}"}).status_code == 401
