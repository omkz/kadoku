"""Safe concierge replies: natural language is optional, products stay authoritative."""
from __future__ import annotations

from app.integrations.llm import generate_grounded_reply
from app.models import Product
from app.services.gifting import Intent


def clarification_for(intent: Intent) -> str | None:
    """Ask about interests instead of recommending arbitrary products."""
    if intent.interests:
        return None
    if intent.budget_minor is None:
        return "What do they enjoy, and do you have a budget in mind? Our demo catalog uses USD."
    return "What are they interested in? Even one or two interests will help me choose a better gift."


def fallback_reply(product: Product, reason: str, intent: Intent) -> str:
    """Useful even when AI is disabled or unavailable."""
    message = f"I'd start with {product.name}. {reason}"
    if intent.budget_minor is None:
        message += " Do you have a budget in mind?"
    return message


async def concierge_reply(
    product: Product, reason: str, intent: Intent, latest_message: str,
    model: str, *, timeout_seconds: float, max_output_tokens: int,
) -> tuple[str, str]:
    fallback = fallback_reply(product, reason, intent)
    if not model:
        return fallback, "rules"
    try:
        answer = await generate_grounded_reply(
            model, latest_message=latest_message,
            product={
                "name": product.name,
                "description": product.description[:350],
                "reason": reason,
                "category": product.category,
            },
            preferences={
                "interests": intent.interests[:8],
                "occasion": intent.occasion,
                "relationship": intent.relationship,
                "budget_provided": intent.budget_minor is not None,
            },
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        # Price appears in a verified product card, never in free-form AI text.
        # Reject ungrounded links, other item names, excessively long responses,
        # or a missing exact catalog product name.
        if (not 15 <= len(answer) <= 330 or product.name not in answer
                or "$" in answer or "http://" in answer.lower()
                or "https://" in answer.lower() or "\n" in answer):
            return fallback, "rules-fallback"
        return answer, "llm"
    except Exception:
        return fallback, "rules-fallback"
