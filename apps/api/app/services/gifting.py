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


# Map catalog categories to interests without guessing product properties.
CATEGORY_INTERESTS = {
    "books": "reading",
    "tech": "technology",
    "food": "cooking",
    "creative": "art",
}
EXCLUSION_ALIASES = {
    "plant": {"plant", "plants", "planter", "planters", "seed", "seeds", "botanical"},
    "plants": {"plant", "plants", "planter", "planters", "seed", "seeds", "botanical"},
}


def eligible_products(products: list[Product], intent: Intent) -> list[Product]:
    """Enforce catalog/price/stock/exclusion constraints before any AI ranking."""
    output: list[Product] = []
    forbidden: set[str] = set()
    for term in intent.avoid:
        term = term.lower().strip()
        if term:
            forbidden.update(EXCLUSION_ALIASES.get(term, {term}))
    for product in products:
        # Kadoku's current storefront is USD-only. Never compare currencies
        # as though their minor units were interchangeable.
        if not product.active or product.stock <= 0 or product.currency != "USD" or product.price_minor < 0:
            continue
        if intent.budget_minor is not None and product.price_minor > intent.budget_minor:
            continue
        searchable = " ".join([
            product.name, product.description, product.category,
            *(product.interests or []), *(product.styles or []),
        ]).lower()
        if any(re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", searchable)
               for term in forbidden):
            continue
        output.append(product)
    return output


def grounded_reason(product: Product, intent: Intent, prefer_personal: bool) -> str:
    """Compose explanations exclusively from catalog and stated intent."""
    interest_matches = sorted(set(intent.interests) & set(product.interests or []))
    relation = (intent.relationship or "").strip().lower()
    if relation not in {"mom", "mother", "ibu", "dad", "father", "ayah",
                        "friend", "teman", "wife", "istri", "husband", "suami",
                        "partner"}:
        relation = ""
    audience = f"your {relation}" if relation else "the recipient"
    parts: list[str] = []
    if interest_matches:
        parts.append(f"Matches {audience}'s interest in {', '.join(interest_matches)}.")
    else:
        parts.append(f"A catalog gift option for {audience}.")
    if intent.occasion and intent.occasion in (product.occasions or []):
        parts.append(f"Tagged for {intent.occasion.replace('_', ' ')} gifts.")
    if prefer_personal and "personal" in (product.styles or []):
        parts.append("Marked as a personalized option in the catalog.")
    details = product.description.strip().rstrip(".")
    if details:
        parts.append(f"Includes: {details[:180]}.")
    if intent.budget_minor is not None:
        parts.append(f"Within your stated budget of {intent.budget_minor / 100:,.2f} USD.")
    return " ".join(parts)


def recommend(products: list[Product], intent: Intent, count: int = 3,
              prefer_personal: bool = False) -> list[tuple[Product, str, str]]:
    """Rank eligible products deterministically, diversifying categories."""
    count = max(0, min(count, 12))
    if not count:
        return []
    eligible: list[tuple[Product, int, str]] = []
    for p in eligible_products(products, intent):
        interest_matches = set(intent.interests) & set(p.interests or [])
        normalized_category = CATEGORY_INTERESTS.get(p.category, p.category)
        interest_score = len(interest_matches) * 8 + (4 if normalized_category in interest_matches else 0)
        occasion_score = 3 if intent.occasion and intent.occasion in (p.occasions or []) else 0
        price_score = 2 if intent.budget_minor and p.price_minor <= int(intent.budget_minor * .85) else 0
        specificity = 1 if "personal" in (p.styles or []) else 0
        personal_score = 16 if prefer_personal and specificity else 0
        score = interest_score + occasion_score + price_score + specificity + personal_score
        eligible.append((p, score, grounded_reason(p, intent, prefer_personal)))
    eligible.sort(key=lambda row: (-row[1], row[0].price_minor, row[0].id))
    rows: list[tuple[Product, str]] = []
    categories: set[str] = set()
    for p, _, reason in eligible:
        if p.category in categories:
            continue
        rows.append((p, reason))
        categories.add(p.category)
        if len(rows) >= count:
            break
    if len(rows) < count:
        for p, _, reason in eligible:
            if any(chosen.id == p.id for chosen, _ in rows):
                continue
            rows.append((p, reason))
            if len(rows) >= count:
                break
    labels = ("Top pick", "Something different", "Another option")
    return [(p, labels[min(index, 2)], reason) for index, (p, reason) in enumerate(rows)]


async def choose_gifts(products: list[Product], intent: Intent, *,
                       prefer_personal: bool, model: str, ai_rerank_enabled: bool,
                       timeout_seconds: float = 12) -> tuple[list[tuple[Product, str, str]], str]:
    """Optional AI ordering of eligible catalog candidates, with safe fallback.

    Costs one additional model request when enabled. The model only returns
    opaque IDs, never prices, product text, or user-visible rationale.
    """
    fallback = recommend(products, intent, prefer_personal=prefer_personal)
    if not ai_rerank_enabled or not model or len(fallback) < 2:
        return fallback, "rules"

    candidates = recommend(products, intent, count=12, prefer_personal=prefer_personal)
    by_id = {p.id: (p, reason) for p, _, reason in candidates}
    wanted = min(3, len(candidates))
    try:
        from app.integrations.llm import rank_catalog_json
        answer = await rank_catalog_json(
            model=model,
            intent={
                "interests": intent.interests[:10],
                "occasion": intent.occasion,
                "relationship": intent.relationship,
                "budget_minor": intent.budget_minor,
                "prefer_personal": prefer_personal,
            },
            candidates=[{
                "id": p.id,
                "name": p.name[:160],
                "description": p.description[:200],
                "category": p.category,
                "price_minor": p.price_minor,
                "interests": (p.interests or [])[:10],
                "styles": (p.styles or [])[:10],
                "occasions": (p.occasions or [])[:10],
            } for p, _, _ in candidates],
            timeout_seconds=timeout_seconds,
        )
        ids = answer.get("ranked_ids")
        if (not isinstance(ids, list) or len(ids) != wanted
                or not all(type(item) is str and item in by_id for item in ids)
                or len(ids) != len(set(ids))):
            raise ValueError("AI ranking contains unknown, repeated, or missing product IDs")
        labels = ("Top pick", "Something different", "Another option")
        return [(by_id[product_id][0], labels[index], by_id[product_id][1])
                for index, product_id in enumerate(ids)], "llm"
    except Exception:
        # Never leak model output or customer preferences through exceptions.
        return fallback, "rules-fallback"
