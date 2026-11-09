"""Grounded gift recommender. The LLM extracts intent only; SQL is the price/stock source of truth."""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
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


async def understand_request(prompt: str, ai_model: str) -> tuple[Intent, str]:
    base = extract_intent_rules(prompt)
    if not ai_model:
        return base, "rules"
    try:
        from litellm import acompletion  # optional, installed with [ai]
        response = await acompletion(
            model=ai_model,
            messages=[
                {"role":"system", "content": (
                    "Extract gift-shopping intent only. Return one JSON object with keys interests "
                    "(array of tags among gardening, coffee, tea, reading, technology, cooking, art, music, wellness, travel), "
                    "occasion (birthday, anniversary, thank_you or null), budget_usd (integer or null), "
                    "avoid (array of words), relationship (string or null). Never guess currencies or convert money. "
                    "Use budget_usd only if user explicitly specifies USD/$; otherwise null.")},
                {"role":"user","content":prompt},
            ],
            max_tokens=180,
            temperature=0,
            timeout=12,
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip()))
        if not isinstance(parsed, dict):
            return base, "rules"
        interests = parsed.get("interests") or base.interests
        interests = [t for t in interests if isinstance(t, str) and t in TAGS][:8]
        budget_usd = parsed.get("budget_usd")
        budget = budget_usd * 100 if type(budget_usd) is int and 0 < budget_usd < 100000 else base.budget_minor
        return Intent(interests, parsed.get("occasion") if parsed.get("occasion") in OCCASIONS else base.occasion,
                      budget, [str(s).lower() for s in parsed.get("avoid",[]) if isinstance(s,str)][:8],
                      str(parsed.get("relationship") or base.relationship or "")[:80]), "llm"
    except Exception:
        # Production can be configured fail-closed instead; no LLM dependency required for local demo.
        return base, "rules-fallback"


def recommend(products: list[Product], intent: Intent, count: int = 3) -> list[tuple[Product,str,str]]:
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
        score = interest_score + occasion_score + price_score + specificity
        matched = ", ".join(sorted(interest_matches))
        reason = f"Matches their interest in {matched}." if matched else "A versatile gift worth considering for the occasion."
        if intent.budget_minor is not None:
            reason += " Fits your stated budget."
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
