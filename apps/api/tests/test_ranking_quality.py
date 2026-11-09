"""Catalog-grounded ranking evaluation. No network calls or model keys needed."""
import asyncio

import pytest

from app.models import Product
from app.seed import SAMPLES
from app.services.gifting import Intent, choose_gifts, extract_intent_rules, recommend


def catalog():
    return [
        Product(
            id=f"demo-{index}", name=name, description=description,
            category=category, price_minor=price, currency="USD",
            stock=10, active=True, interests=interests,
            occasions=occasions, styles=styles, emoji=emoji, demo_only=True,
        )
        for index, (name, description, category, price,
                    interests, occasions, styles, emoji) in enumerate(SAMPLES)
    ]


@pytest.mark.parametrize(("prompt", "top_pick"), [
    ("Birthday gift for mom who loves gardening. Budget $100.", "Garden Lover's Box"),
    ("My friend loves coffee. Budget $70.", "Artisan Coffee Ritual"),
    ("A gift for someone who loves tea, under $50.", "Handmade Tea Box"),
    ("My partner loves books. Budget $60.", "Book Lover Bundle"),
    ("My sister enjoys painting and art. Budget $60.", "Mini Watercolor Studio"),
    ("Something for a friend who loves cooking, under $60.", "Kitchen Discovery Kit"),
    ("A gift for someone who loves technology. Budget $100.", "Pixel Desk Display"),
    ("Birthday present for a music fan. Budget $100.", "Vinyl-Inspired Speaker"),
    ("My mom loves gardening but no plants. Budget $100.", "Engraved Garden Set"),
])
def test_curated_recommendation_evaluation_set(prompt, top_pick):
    options = recommend(catalog(), extract_intent_rules(prompt))
    assert options, prompt
    assert options[0][0].name == top_pick, prompt
    assert len(options) <= 3


def test_all_exclusions_price_stock_and_currency_are_hard_filters():
    products = catalog()
    products[0].stock = 0
    products[3].active = False
    products[4].currency = "IDR"
    options = recommend(products, Intent(
        interests=["gardening", "tea"], budget_minor=6000, avoid=["plants"],
    ))
    ids = {p.id for p, _, _ in options}
    assert products[0].id not in ids
    assert products[3].id not in ids
    assert products[4].id not in ids
    assert all(p.currency == "USD" and p.active and p.stock > 0 and p.price_minor <= 6000
               for p, _, _ in options)
    assert all("seed" not in p.description.lower() and "planter" not in p.name.lower()
               for p, _, _ in options)


def test_reasons_only_use_catalog_data_and_explicit_preferences():
    products = catalog()
    intent = Intent(interests=["gardening"], occasion="birthday",
                    budget_minor=10_000, relationship="mom")
    top, label, reason = recommend(products, intent)[0]
    assert label == "Top pick"
    assert top.description.rstrip(".") in reason
    assert "your mom" in reason
    assert "birthday" in reason
    assert "100.00 USD" in reason
    assert "guaranteed" not in reason.lower()


def test_ai_reranks_only_eligible_catalog_ids(monkeypatch):
    from app.integrations import llm
    products = catalog()
    captured = {}

    async def stub(**kwargs):
        captured.update(kwargs)
        candidates = kwargs["candidates"]
        return {"ranked_ids": [candidate["id"] for candidate in candidates[:3]][::-1]}

    monkeypatch.setattr(llm, "rank_catalog_json", stub)
    intent = Intent(interests=["gardening"], budget_minor=10000)
    result, source = asyncio.run(choose_gifts(
        products, intent, prefer_personal=False, model="fake/model",
        ai_rerank_enabled=True, timeout_seconds=5,
    ))
    assert source == "llm"
    assert [p.id for p, _, _ in result] == [p["id"] for p in captured["candidates"][:3]][::-1]
    assert all(p.price_minor <= 10000 for p, _, _ in result)
    assert all(p.description.rstrip(".") in reason for p, _, reason in result)
    assert "prompt" not in captured["intent"]
    assert captured["timeout_seconds"] == 5
    assert len(captured["candidates"]) <= 12


@pytest.mark.parametrize("bad", [
    {"ranked_ids": ["fake-product", "another", "not-in-catalog"]},
    {"ranked_ids": ["fake-product"]},
    {"ranked_ids": "product-id"},
    {"ranked_ids": [None, 1, "123"]},
])
def test_invalid_ai_ranking_falls_back(monkeypatch, bad):
    from app.integrations import llm

    async def stub(**kwargs):
        return bad

    monkeypatch.setattr(llm, "rank_catalog_json", stub)
    products = catalog()
    intent = Intent(interests=["tea"], budget_minor=5000)
    baseline = recommend(products, intent)
    selected, source = asyncio.run(choose_gifts(
        products, intent, prefer_personal=False,
        model="fake/model", ai_rerank_enabled=True,
    ))
    assert source == "rules-fallback"
    assert [p.id for p, _, _ in selected] == [p.id for p, _, _ in baseline]


def test_duplicate_ai_ids_rejected(monkeypatch):
    from app.integrations import llm

    async def stub(**kwargs):
        product_id = kwargs["candidates"][0]["id"]
        return {"ranked_ids": [product_id, product_id, product_id]}

    monkeypatch.setattr(llm, "rank_catalog_json", stub)
    items, source = asyncio.run(choose_gifts(
        catalog(), Intent(interests=["gardening"]), prefer_personal=False,
        model="fake/model", ai_rerank_enabled=True,
    ))
    assert source == "rules-fallback"
    assert len(items) == 3


def test_no_second_ai_call_unless_opted_in(monkeypatch):
    from app.integrations import llm

    async def fail_if_called(**kwargs):
        raise AssertionError("AI reranking should be disabled by default")

    monkeypatch.setattr(llm, "rank_catalog_json", fail_if_called)
    result, source = asyncio.run(choose_gifts(
        catalog(), Intent(interests=["coffee"]),
        prefer_personal=False, model="fake/model", ai_rerank_enabled=False,
    ))
    assert source == "rules"
    assert result[0][0].name == "Artisan Coffee Ritual"


def test_no_match_does_not_ask_ai(monkeypatch):
    from app.integrations import llm

    async def fail_if_called(**kwargs):
        raise AssertionError("No candidates available")

    monkeypatch.setattr(llm, "rank_catalog_json", fail_if_called)
    result, source = asyncio.run(choose_gifts(
        catalog(), Intent(interests=["coffee"], budget_minor=1),
        prefer_personal=False, model="fake/model", ai_rerank_enabled=True,
    ))
    assert not result
    assert source == "rules"
