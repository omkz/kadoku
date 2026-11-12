"""Small, server-authorized role management surface for Kadoku super admins.

Better Auth owns the 'user' table; this API only updates its role field.
The public Better Auth Admin API is intentionally granted no user-management
permissions, so role changes pass through this guarded endpoint.
"""
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import required_super_admin
from app.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin-team"])


class TeamMember(BaseModel):
    id: str
    name: str
    email: str
    role: str


class TeamList(BaseModel):
    items: list[TeamMember]
    total: int


class RoleChange(BaseModel):
    role: Literal["user", "admin", "super_admin"]


@router.get("/team", response_model=TeamList)
def list_team(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: str = Depends(required_super_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text('SELECT id, name, email, role FROM "user" ORDER BY email, id LIMIT :limit OFFSET :offset'),
        {"limit": limit, "offset": offset},
    ).mappings().all()
    total = db.execute(text('SELECT COUNT(*) FROM "user"')).scalar_one()
    return TeamList(items=[
        TeamMember(id=row["id"], name=row["name"], email=row["email"],
                   role=row["role"] or "user")
        for row in rows
    ], total=total)


@router.patch("/team/{user_id}/role", response_model=TeamMember)
def change_role(
    user_id: str,
    payload: RoleChange,
    actor: str = Depends(required_super_admin),
    db: Session = Depends(get_db),
):
    if actor == user_id:
        raise HTTPException(409, "You cannot change your own role")

    # Serialize role changes on PostgreSQL to prevent concurrent demotions
    # from removing the last super admin. SQLite is only used in unit tests.
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(38110457)"))
    target = db.execute(
        text('SELECT id, name, email, role FROM "user" WHERE id = :id'),
        {"id": user_id},
    ).mappings().first()
    if target is None:
        raise HTTPException(404, "User not found")
    old_role = target["role"] or "user"
    if old_role == "super_admin" and payload.role != "super_admin":
        remaining = db.execute(
            text('SELECT COUNT(*) FROM "user" WHERE role = :role'),
            {"role": "super_admin"},
        ).scalar_one()
        if remaining <= 1:
            raise HTTPException(409, "Cannot remove the last super administrator")
    db.execute(
        text('UPDATE "user" SET role = :role WHERE id = :id'),
        {"id": user_id, "role": payload.role},
    )
    db.commit()
    logger.info("Admin role changed actor=%s target=%s from=%s to=%s",
                actor, user_id, old_role, payload.role)
    return TeamMember(id=target["id"], name=target["name"],
                      email=target["email"], role=payload.role)
