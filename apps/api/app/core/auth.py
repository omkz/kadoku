"""Verify Better Auth JWT plugin tokens using its public JWKS endpoint."""
from fastapi import Depends, Header, HTTPException
import jwt
from jwt import PyJWKClient
from app.core.config import get_settings


def optional_user(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Expected a Bearer token")
    token = authorization[7:]
    issuer = get_settings().better_auth_url.rstrip("/")
    try:
        jwks_client = PyJWKClient(f"{issuer}/api/auth/jwks", cache_keys=True, lifespan=300)
        key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(token, key.key, algorithms=["EdDSA", "ES256", "RS256", "PS256"], audience=issuer, issuer=issuer)
        user_id = decoded.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Missing subject")
        return user_id
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired session token") from exc


def required_user(user_id: str | None = Depends(optional_user)) -> str:
    if not user_id:
        raise HTTPException(401, "Sign in to save recipients and occasions")
    return user_id
