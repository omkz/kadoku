"""A minimal endpoint for validating web-to-API session integration."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.auth import required_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class CurrentUser(BaseModel):
    user_id: str


@router.get("/me", response_model=CurrentUser)
def me(user_id: str = Depends(required_user)) -> CurrentUser:
    return CurrentUser(user_id=user_id)
