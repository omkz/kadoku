"""Grounded gift recommender. The LLM extracts intent only; SQL is the price/stock source of truth."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.integrations.llm import extract_intent_json
from app.models import Product

TAGS = {
    "gardening": ["garden", "gardening", "plant", "plants", "tanaman", "berkebun", "kebun"],
    "coffee": ["coffee", "kopi", "barista"],
    "tea": ["tea", "teh"],
    "reading": ["read", "reading", "books", "book", "buku", "membaca"],
    "technology": ["tech", "gadget", "technology", "teknologi", "komputer"],
    "cooking": ["cook", "cooking", "masak", "dapur"],
    "art": ["art", "drawing", "painting", "seni", "melukis"],
    "music": ["music", "musik"],
    "wellness": ["relax", "self care", "spa", "relaksasi", "wellness"],
    "travel": ["travel", "traveling", "travelling", "jalan jalan", "wisata"],
}
OCCASIONS = {
    "birthday": ["birthday", "ulang tahun", "ultah"],
    "anniversary": ["anniversary", "hari jadi"],
    "thank_you": ["thank you", "terima kasih"],
}


@dataclass
class Intent:
    interests: list[str] = field(default_factory=list)
    occasion: str | None = None
    budget_minor: int | None = None
    avoid: list[str] = field(default_factory=list)
    relationship: str | None = None


def extract_intent_rules(prompt: str) -> Intent:
    lowered = prompt.lower()
    interests = [tag for tag, terms in TAGS.items() if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", lowered) for term in terms)]
    occasion = next((tag for tag, terms in OCCASIONS.items() if any(t in lowered for t in terms)), None)
    # Currency is USD in the sample catalog; do not silently convert IDR to USD.
    money = re.search(r"(?:\$|usd\s*)(\d{1,5})(?!\d)", lowered)
    budget = int(money.group(1)) * 100 if money else None
    avoid = []
    for match in re.finditer(r"(?:no|not|avoid|without|jangan|tanpa)\s+([\w-]+)", lowered):
        avoid.append(match.group(1))
    relationship = next((s for s in ["mom", "mother", "ibu", "dad", "father", "ayah", "friend", "teman", "wife", "istri", "husband", "suami", "partner"] if s in lowered), None)
    return Intent(interests, occasion, budget, avoid, relationship)


class ExtractedIntent(BaseModel):
    """Provider output is untrusted, even if it looks like structured JSON."""
    model_config = ConfigDict(extra="forbid", strict=True)

    interests: list[Literal["gardening", "coffee", "tea", "reading", "technology",
                            "cooking", "art", "music", "wellness", "travel"]] = Field(default_factory=list, max_length=8)
    occasion: Literal["birthday", "anniversary", "thank_you"] | None = None
    budget_usd: int | None = Field(default=None, gt=0, le=100_000)
    avoid: list[str] = Field(default_factory=list, max_length=8)
    relationship: str | None = Field(default=None, max_length=80)


def merge_intent(base: Intent, extracted: ExtractedIntent, prompt: str) -> Intent:
    """Keep explicit budget/exclusions as hard constraints, regardless of LLM opinion."""
    interests = list(dict.fromkeys(base.interests + extracted.interests))[:8]
    avoids = list(dict.fromkeys(base.avoid + [
        value.strip().lower() for value in extracted.avoid
        if isinstance(value, str) and 0 < len(value.strip()) <= 60
    ]))[:12]
    explicit_usd = bool(re.search(r"\$\s*\d|\bUSD\b", prompt, flags=re.I))
    budget = base.budget_minor
    if budget is None and explicit_usd and extracted.budget_usd is not None:
        budget = extracted.budget_usd * 100
    return Intent(
        interests=interests,
        occasion=base.occasion or extracted.occasion,
        budget_minor=budget,
        avoid=avoids,
        relationship=base.relationship or extracted.relationship,
    )


async def understand_request(prompt: str, ai_model: str,
                             timeout_seconds: float = 12, max_output_tokens: int = 240) -> tuple[Intent, str]:
    """Extract explicit shopping constraints, falling back to rules on provider failure."""
    base = extract_intent_rules(prompt)
    if not ai_model:
        return base, "rules"
    try:
        fields = await extract_intent_json(
            prompt, ai_model,
            timeout_seconds=timeout_seconds,
            max_output_tokens=max_output_tokens,
        )
        parsed = ExtractedIntent.model_validate(fields)
        return merge_intent(base, parsed, prompt), "llm"
    except Exception:
        # Availability matters more than LLM success for the demo/catalog flow.
        # No request text or credentials are written to logs on failures.
        return base, "rules-fallback"


def recommend(products: list[Product], intent: Intent, count: int = 3,
              prefer_personal: bool = False) -> list[tuple[Product,str,str]]:
    """Hard constraints first, then grounded scoring plus category diversity."""
    eligible = []
    for p in products:
        if p.stock <= 0 or not p.active:
            continue
        if intent.budget_minor is not None and p.price_minor > intent.budget_minor:
            continue
        searchable = (p.name + " " + p.description + " " + " ".join(p.interests + p.styles)).lower()
        if any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", searchable) for t in intent.avoid):
            continue
        interest_matches = set(intent.interests) & set(p.interests)
        interest_score = len(interest_matches) * 8 + (4 if p.category in interest_matches else 0)
        occasion_score = 3 if intent.occasion and intent.occasion in p.occasions else 0
        price_score = 2 if intent.budget_minor and p.price_minor <= int(intent.budget_minor * .85) else 0
        specificity = 1 if "personal" in p.styles else 0
        personal_score = 16 if prefer_personal and 'personal' in p.styles else 0
        score = interest_score + occasion_score + price_score + specificity + personal_score
        matched = ", ".join(sorted(interest_matches))
        reason = f"Matches their interest in {matched}." if matched else "A versatile gift worth considering for the occasion."
        if intent.budget_minor is not None:
            reason += " Fits your stated budget."
        if personal_score:
            reason += " Adds a personal touch."
        eligible.append((p, score, reason))
    eligible.sort(key=lambda row: (-row[1], row[0].price_minor, row[0].id))
    results: list[tuple[Product,str,str]] = []
    categories: set[str] = set()
    for p, _, reason in eligible:
        if p.category in categories:
            continue
        label = ["Top pick", "Something different", "Another option"][len(results)]
        results.append((p, label, reason))
        categories.add(p.category)
        if len(results) == count:
            return results
    for p, _, reason in eligible:
        if any(x[0].id == p.id for x in results):
            continue
        label = ["Top pick", "Something different", "Another option"][len(results)]
        results.append((p, label, reason))
        if len(results) == count:
            break
    return results
