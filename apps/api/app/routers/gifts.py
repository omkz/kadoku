from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.auth import optional_user
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.catalog import available_products, featured_products, get_product
from app.models import Recipient
from app.schemas.gifts import GiftCard, GiftRequest, GiftResponse, ProductOut
from app.services.gifting import recommend, understand_request
from app.services.conversation import refine_request, next_context
from app.services.concierge import clarification_for, concierge_reply
from app.services.quota import use_recommendation

router = APIRouter(prefix="/api/v1", tags=["gifting"])


@router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    return available_products(db)


@router.get("/products/featured", response_model=list[ProductOut])
def products_featured(db: Session = Depends(get_db)):
    """Six editorial homepage picks; full catalog remains available for AI."""
    return featured_products(db)


@router.post("/gifts/recommendations", response_model=GiftResponse)
async def gift_recommendations(payload: GiftRequest, request: Request,
                               db: Session = Depends(get_db), user_id: str | None = Depends(optional_user)):
    if not payload.context and len(payload.prompt.strip()) < 10:
        raise HTTPException(422, "Describe the gift recipient in at least 10 characters")
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
    intent, prefer_personal = refine_request(intent, payload.context, payload.prompt)
    if recipient:
        intent.interests = sorted(set(intent.interests) | set(recipient.interests))
        intent.avoid = sorted(set(intent.avoid) | set(recipient.avoids))
        if intent.budget_minor is None:
            intent.budget_minor = recipient.usual_budget_minor
    clarification = clarification_for(intent)
    choices = [] if clarification else recommend(available_products(db), intent, prefer_personal=prefer_personal)
    if clarification:
        summary, reply_provider = clarification, "rules"
    elif choices:
        top, _, reason = choices[0]
        summary, reply_provider = await concierge_reply(
            top, reason, intent, payload.prompt, settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            max_output_tokens=settings.ai_max_output_tokens,
        )
    else:
        summary, reply_provider = (
            "I couldn't find a match in our demo catalog with those preferences. "
            "Could you try another interest or a different budget?", "rules"
        )
    return GiftResponse(
        summary=summary,
        clarification=clarification,
        reply_provider=reply_provider,
        recommendations=[GiftCard(
            id=p.id, name=p.name, description=p.description, category=p.category,
            price_minor=p.price_minor, currency=p.currency, emoji=p.emoji,
            demo_only=p.demo_only, image_url=p.image_url, label=label, reason=reason,
        ) for p, label, reason in choices],
        remaining_today=remaining, provider=provider,
        context=next_context(
            intent, prefer_personal=prefer_personal,
            top_pick_price_minor=choices[0][0].price_minor if choices else None,
        ),
    )
