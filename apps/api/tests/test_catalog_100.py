"""Catalog expansion regression checks (100 illustrative, non-fulfillable gifts)."""

from collections import Counter
import re
from uuid import NAMESPACE_URL, uuid5

import pytest
from sqlalchemy import delete, select

from app.catalog.demo_products import EXTRA_SAMPLES
from app.models import Order, Product
from app.seed import IMAGE_URLS, SAMPLES, seed
from app.services.gifting import Intent, TAGS, recommend


def test_100_curated_product_definitions_cover_current_interest_vocabulary(database):
    assert len(SAMPLES) == 12
    assert len(EXTRA_SAMPLES) == 88
    assert len({row[0] for row in SAMPLES + EXTRA_SAMPLES}) == 100

    prices = []
    categories = Counter()
    for name, description, category, minor, interests, occasions, styles, emoji in SAMPLES + EXTRA_SAMPLES:
        assert name and len(name) <= 160
        assert len(description) >= 20
        assert category and interests and occasions and styles and emoji
        assert set(interests).issubset(TAGS)
        assert set(occasions).issubset({"birthday", "anniversary", "thank_you"})
        assert 1500 <= minor <= 15000
        prices.append(minor)
        categories[category] += 1
    assert len(categories) >= 10
    assert min(prices) <= 2000
    assert max(prices) >= 13000
    assert all(categories[tag] >= 3 for tag in ("tech", "food", "creative", "wellness", "travel"))

    with database() as db:
        products = db.scalars(select(Product)).all()
        assert len(products) == 100
        assert len({p.id for p in products}) == 100
        assert len({p.name for p in products}) == 100
        assert all(p.demo_only and p.active and p.currency == "USD" and p.stock > 0 for p in products)
        assert {p.name: p.image_url for p in products if p.image_url} == IMAGE_URLS
        assert sum(p.image_url is None for p in products) == 95


def test_seed_blank_database_then_repeat_is_idempotent(database):
    with database() as db:
        db.execute(delete(Product))
        db.commit()
    with database() as db:
        assert seed(db) == 100
        assert len(db.scalars(select(Product)).all()) == 100
        assert seed(db) == 0
        assert len(db.scalars(select(Product)).all()) == 100


def test_existing_12_grow_by_88_without_replacing_product_or_order_ids(database):
    extra_ids = {
        str(uuid5(NAMESPACE_URL, f"kadoku/demo-products/v1/{name}"))
        for name, *_ in EXTRA_SAMPLES
    }
    with database() as db:
        original = db.scalar(select(Product).where(Product.name == "Garden Lover's Box"))
        original_id = original.id
        original.price_minor = 7777
        original.stock = 4
        original.image_url = "/products/my-custom-photo.webp"
        db.add(Order(user_id="buyer-123", product_id=original_id,
                     price_snapshot_minor=6800, currency="USD", status="paid",
                     paypal_order_id="PAYPAL-ORIGINAL-ORDER"))
        db.execute(delete(Product).where(Product.id.in_(extra_ids)))
        db.commit()

    with database() as db:
        assert len(db.scalars(select(Product)).all()) == 12
        assert seed(db) == 88
        assert len(db.scalars(select(Product)).all()) == 100
        old = db.get(Product, original_id)
        assert old.name == "Garden Lover's Box"
        assert old.price_minor == 7777
        assert old.stock == 4
        assert old.image_url == "/products/my-custom-photo.webp"
        assert db.scalar(select(Order).where(Order.paypal_order_id == "PAYPAL-ORIGINAL-ORDER")).product_id == original_id
        assert seed(db) == 0
        assert len(db.scalars(select(Product)).all()) == 100


def test_stable_ids_prevent_readding_a_renamed_extra(database):
    name = "Pocket Book Light"
    product_id = str(uuid5(NAMESPACE_URL, f"kadoku/demo-products/v1/{name}"))
    with database() as db:
        product = db.get(Product, product_id)
        assert product and product.name == name
        product.name = "Renamed by a store admin"
        product.price_minor = 4123
        product.stock = 2
        db.commit()
        assert seed(db) == 0
        assert len(db.scalars(select(Product)).all()) == 100
        assert db.get(Product, product_id).name == "Renamed by a store admin"
        assert db.get(Product, product_id).price_minor == 4123
        assert db.get(Product, product_id).stock == 2


@pytest.mark.parametrize("tag", sorted(TAGS))
@pytest.mark.parametrize("budget", [4000, 8000, 15000])
def test_recommendation_30_interest_budget_scenarios(database, tag, budget):
    with database() as db:
        products = db.scalars(select(Product)).all()
        picks = recommend(products, Intent(interests=[tag], occasion="birthday", budget_minor=budget))
        assert 1 <= len(picks) <= 3
        assert len({p.id for p, _, _ in picks}) == len(picks)
        assert all(p.price_minor <= budget and p.stock > 0 for p, _, _ in picks)
        assert tag in picks[0][0].interests


@pytest.mark.parametrize("avoided", ["candle", "leather", "glass", "coffee", "tea"])
def test_excluded_words_are_not_in_recommended_items(database, avoided):
    with database() as db:
        products = db.scalars(select(Product)).all()
        picks = recommend(products, Intent(interests=["wellness", "travel", "coffee", "tea"],
                                           budget_minor=10000, avoid=[avoided]))
        for p, _, _ in picks:
            searchable = (p.name + " " + p.description + " " + " ".join(p.interests + p.styles)).lower()
            assert not re.search(r"(?<!\w)" + re.escape(avoided) + r"(?!\w)", searchable)


def test_recommender_never_returns_inactive_or_out_of_stock(database):
    with database() as db:
        products = db.scalars(select(Product)).all()
        for p in products:
            if "coffee" in p.interests:
                p.stock = 0
        picks = recommend(products, Intent(interests=["coffee"], budget_minor=15000))
        assert all(p.stock > 0 and p.active for p, _, _ in picks)
