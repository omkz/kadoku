from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.auth import optional_user
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.catalog import available_products, get_product
from app.models import Recipient
from app.schemas.gifts import GiftCard, GiftRequest, GiftResponse, ProductOut
from app.services.gifting import recommend, understand_request
from app.services.quota import use_recommendation

router = APIRouter(prefix="/api/v1", tags=["gifting"])


@router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    return available_products(db)


@router.post("/gifts/recommendations", response_model=GiftResponse)
async def gift_recommendations(payload: GiftRequest, request: Request,
                               db: Session = Depends(get_db), user_id: str | None = Depends(optional_user)):
    recipient = None
    if payload.recipient_id:
        if user_id is None:
            raise HTTPException(401, "Sign in to use a saved recipient")
        recipient = db.get(Recipient, payload.recipient_id)
        if recipient is None or recipient.user_id != user_id:
            raise HTTPException(404, "Recipient not found")
    # Only trust ASGI client address; do not accept client-supplied X-Forwarded-For headers.
    client_ip = request.client.host if request.client else "unknown"
    remaining = use_recommendation(db, user_id, client_ip, request.cookies.get("kadoku_guest"))
    settings = get_settings()
    intent, provider = await understand_request(
        payload.prompt, settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
        max_output_tokens=settings.ai_max_output_tokens,
    )
    if recipient:
        intent.interests = sorted(set(intent.interests) | set(recipient.interests))
        intent.avoid = sorted(set(intent.avoid) | set(recipient.avoids))
        if intent.budget_minor is None:
            intent.budget_minor = recipient.usual_budget_minor
    choices = recommend(available_products(db), intent)
    return GiftResponse(
        summary=("Here are up to three thoughtfully selected gift ideas." if choices
                 else "No gifts matched your request in the sample catalog. Try a higher USD budget."),
        recommendations=[GiftCard(
            id=p.id, name=p.name, description=p.description, category=p.category,
            price_minor=p.price_minor, currency=p.currency, emoji=p.emoji,
            demo_only=p.demo_only, label=label, reason=reason,
        ) for p, label, reason in choices],
        remaining_today=remaining, provider=provider,
    )
