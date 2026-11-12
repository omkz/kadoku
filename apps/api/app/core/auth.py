"""Verify Better Auth session JWTs with pinned EdDSA JWKS keys."""
from functools import lru_cache

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import jwt
from jwt import PyJWKClient

from app.core.config import get_settings
from app.db.session import get_db


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> PyJWKClient:
    # Reuse the client so JWKS cache/rotation handling is effective per process.
    return PyJWKClient(f"{issuer}/api/auth/jwks", lifespan=300)


def optional_user(authorization: str | None = Header(default=None)) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(401, "Expected a Bearer token")
    issuer = get_settings().better_auth_url.rstrip("/")
    try:
        signing_key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            audience=issuer,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        user_id = claims["sub"]
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("Invalid subject")
        return user_id
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise HTTPException(401, "Invalid or expired session token") from exc
    except Exception as exc:
        # JWKS temporarily unreachable or malformed. Fail closed.
        raise HTTPException(401, "Unable to verify session token") from exc


def required_user(user_id: str | None = Depends(optional_user)) -> str:
    if not user_id:
        raise HTTPException(401, "Sign in to access your account")
    return user_id


def _current_role(db: Session, user_id: str) -> str | None:
    """Read Better Auth role server-side, never from the browser or JWT claims.

    Admin plugin stores one of our three mutually exclusive application roles.
    Unknown, missing and multi-role values fail closed. A banned account is
    denied immediately, even if an older JWT remains cryptographically valid.
    """
    try:
        row = db.execute(
            text('SELECT role, banned FROM "user" WHERE id = :id'),
            {"id": user_id},
        ).first()
    except SQLAlchemyError as exc:
        raise HTTPException(503, "Authorization database unavailable or not migrated") from exc
    if row is None or row.banned:
        return None
    role = row.role or "user"
    return role if role in ("user", "admin", "super_admin") else None


def required_admin(
    user_id: str = Depends(required_user), db: Session = Depends(get_db),
) -> str:
    if _current_role(db, user_id) not in ("admin", "super_admin"):
        raise HTTPException(403, "Administrator access required")
    return user_id


def required_super_admin(
    user_id: str = Depends(required_user), db: Session = Depends(get_db),
) -> str:
    if _current_role(db, user_id) != "super_admin":
        raise HTTPException(403, "Super administrator access required")
    return user_id
