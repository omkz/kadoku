from datetime import datetime, timezone
import hashlib
import hmac
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import RecommendationUsage


def use_recommendation(db: Session, user_id: str | None, client_ip: str,
                       guest_cookie: str | None = None) -> int:
    settings = get_settings()
    if user_id:
        subject = "member:" + user_id
        limit = settings.member_recommendations_daily
    else:
        secret = settings.guest_quota_secret or "local-development-only-not-production"
        verified_guest = None
        if guest_cookie:
            parts = guest_cookie.split(".")
            if len(parts) == 2:
                identifier, signature = parts
                expected = hmac.new(secret.encode(), identifier.encode(), hashlib.sha256).hexdigest()
                if len(identifier) == 36 and hmac.compare_digest(signature, expected):
                    verified_guest = identifier
        # Signed HttpOnly cookie is the primary per-browser quota identity.
        # Direct API clients without a cookie fall back to IP hashing.
        # Cookie deletion can evade the guest quota: add abuse detection/WAF before launch.
        key = verified_guest if verified_guest else "ip:" + client_ip
        subject = "guest:" + hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
        limit = settings.guest_recommendations_daily
    day = datetime.now(timezone.utc).date()
    usage = db.scalar(select(RecommendationUsage).where(
        RecommendationUsage.subject == subject,
        RecommendationUsage.day == day,
    ).with_for_update())
    if usage is None:
        usage = RecommendationUsage(subject=subject, day=day, count=1)
        db.add(usage)
    elif usage.count >= limit:
        raise HTTPException(429, detail="Daily gift recommendation limit reached. Sign in or try tomorrow.")
    else:
        usage.count += 1
    try:
        db.commit()  # reserve before any LLM call
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(429, detail="Daily recommendation limit reached. Please retry later.") from exc
    return max(0, limit - usage.count)
