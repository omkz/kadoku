from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.auth import required_user
from app.db.session import get_db
from app.models import Recipient, Occasion
from app.schemas.gifts import OccasionIn, OccasionOut, RecipientIn, RecipientOut

router = APIRouter(prefix="/api/v1", tags=["people"])


@router.get("/recipients", response_model=list[RecipientOut])
def list_recipients(user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Recipient).where(Recipient.user_id == user_id)).all())


@router.post("/recipients", response_model=RecipientOut, status_code=201)
def add_recipient(payload: RecipientIn, user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    row = Recipient(user_id=user_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/recipients/{recipient_id}", status_code=204)
def delete_recipient(recipient_id: str, user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    row = db.get(Recipient, recipient_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, "Recipient not found")
    db.delete(row)
    db.commit()


@router.get("/occasions", response_model=list[OccasionOut])
def list_occasions(user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Occasion).join(Recipient).where(Recipient.user_id == user_id)).all())


@router.post("/occasions", response_model=OccasionOut, status_code=201)
def add_occasion(payload: OccasionIn, user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    owner = db.get(Recipient, payload.recipient_id)
    if owner is None or owner.user_id != user_id:
        raise HTTPException(404, "Recipient not found")
    try:
        date(payload.year or 2000, payload.month, payload.day)
    except ValueError as exc:
        raise HTTPException(422, "Invalid calendar date") from exc
    row = Occasion(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
