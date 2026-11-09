"""Refine gift recommendations while retaining bounded, explicit shopping context.

The web client sends back only this structured context; no server session or
raw chat transcript needs to be stored for this MVP.
"""
from __future__ import annotations

import re

from app.schemas.gifts import GiftContext
from app.services.gifting import Intent


_CHEAPER = re.compile(
    r"\b(cheaper|less expensive|lower budget|more affordable|lebih murah|murahan|hemat|terjangkau)\b",
    flags=re.I,
)
_PERSONAL = re.compile(
    r"\b(personal|personalized|personalised|engraved|custom(?:ized|ised)?|personalisasi)\b",
    flags=re.I,
)


def refine_request(current: Intent, previous: GiftContext | None, prompt: str) -> tuple[Intent, bool]:
    """Only a new explicit USD amount replaces the previous budget.

    "Cheaper" means strictly below the last top pick, not a guessed currency
    conversion or an invented price; otherwise keep the previous limit.
    """
    if previous is None:
        return current, bool(_PERSONAL.search(prompt))

    new_budget = current.budget_minor if current.budget_minor is not None else previous.budget_minor
    if _CHEAPER.search(prompt) and current.budget_minor is None and previous.top_pick_price_minor:
        cheaper_than = previous.top_pick_price_minor - 1
        new_budget = min(new_budget, cheaper_than) if new_budget is not None else cheaper_than
        # No cheaper positive-priced gift is possible below $0.01.
        new_budget = max(0, new_budget)

    interests = list(dict.fromkeys([*previous.interests, *current.interests]))[:10]
    avoid = list(dict.fromkeys([*previous.avoid, *current.avoid]))[:12]
    intent = Intent(
        interests=interests,
        occasion=current.occasion or previous.occasion,
        budget_minor=new_budget,
        avoid=avoid,
        relationship=current.relationship or previous.relationship,
    )
    return intent, previous.prefer_personal or bool(_PERSONAL.search(prompt))


def next_context(intent: Intent, *, prefer_personal: bool,
                 top_pick_price_minor: int | None) -> GiftContext:
    return GiftContext(
        interests=intent.interests[:10],
        occasion=intent.occasion,
        budget_minor=intent.budget_minor,
        avoid=intent.avoid[:12],
        relationship=intent.relationship,
        prefer_personal=prefer_personal,
        top_pick_price_minor=top_pick_price_minor,
    )
