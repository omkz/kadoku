"""Illustrative gifts only. Do not publish as purchasable real inventory."""
from sqlalchemy import select
from uuid import NAMESPACE_URL, uuid5
from app.catalog.demo_products import EXTRA_SAMPLES
from app.models import Product

SAMPLES = [
    ("Garden Lover's Box", "Gardening tools, seed packets, and gloves.", "gardening", 6800, ["gardening"], ["birthday", "thank_you"], ["practical"], "🌱"),
    ("Botanical Planter", "Handmade planter for an indoor green corner.", "home", 4200, ["gardening", "art"], ["birthday"], ["thoughtful"], "🪴"),
    ("Engraved Garden Set", "Personalized hand tools for a garden enthusiast.", "personalized", 8900, ["gardening"], ["birthday", "anniversary"], ["personal"], "🌷"),
    ("Artisan Coffee Ritual", "Brewing tools and specialty coffee gift set.", "coffee", 5900, ["coffee"], ["birthday", "thank_you"], ["practical"], "☕"),
    ("Handmade Tea Box", "A curated collection of loose-leaf teas.", "tea", 3500, ["tea", "wellness"], ["birthday", "thank_you"], ["relaxing"], "🍵"),
    ("Book Lover Bundle", "Reading journal, bookmark, and book light.", "books", 4500, ["reading"], ["birthday"], ["cozy"], "📚"),
    ("Pixel Desk Display", "Colorful desktop pixel-art display.", "tech", 7900, ["technology", "art"], ["birthday"], ["unique"], "🕹️"),
    ("Kitchen Discovery Kit", "Spices and illustrated recipe cards.", "food", 4900, ["cooking"], ["birthday", "thank_you"], ["practical"], "🧑‍🍳"),
    ("Mini Watercolor Studio", "Travel watercolor palette and sketchbook.", "creative", 5400, ["art", "travel"], ["birthday"], ["creative"], "🎨"),
    ("Cozy Evening Box", "Soft blanket, candle, and relaxation treats.", "wellness", 6400, ["wellness", "reading"], ["birthday", "anniversary"], ["cozy"], "🕯️"),
    ("Travel Memory Journal", "Personal travel notes and keepsake album.", "travel", 3300, ["travel", "reading"], ["birthday", "anniversary"], ["personal"], "🧳"),
    ("Vinyl-Inspired Speaker", "Compact retro-style Bluetooth speaker.", "music", 7200, ["music", "technology"], ["birthday"], ["unique"], "🎵"),
]


# Generated illustrations, not supplier photos or inventory.
IMAGE_URLS = {
    "Garden Lover's Box": "/products/garden-lovers-box.webp",
    "Artisan Coffee Ritual": "/products/artisan-coffee-ritual.webp",
    "Handmade Tea Box": "/products/handmade-tea-box.webp",
    "Book Lover Bundle": "/products/book-lover-bundle.webp",
    "Cozy Evening Box": "/products/cozy-evening-box.webp",
}


def seed(db):
    """Add missing demo products without changing existing rows.

    Stable IDs prevent duplicate inserts; existing order links stay intact.
    """
    existing = list(db.scalars(select(Product)).all())
    names = {p.name for p in existing}
    ids = {p.id for p in existing}
    added = 0

    for product in existing:
        image_url = IMAGE_URLS.get(product.name)
        if image_url and not product.image_url:
            product.image_url = image_url

    for name, desc, category, price, interests, occasions, styles, emoji in SAMPLES:
        if name in names:
            continue
        row = Product(
            name=name, description=desc, category=category,
            price_minor=price, currency="USD", stock=10,
            interests=interests, occasions=occasions, styles=styles,
            emoji=emoji, image_url=IMAGE_URLS.get(name), demo_only=True,
        )
        db.add(row)
        names.add(name)
        added += 1

    for name, desc, category, price, interests, occasions, styles, emoji in EXTRA_SAMPLES:
        stable_id = str(uuid5(NAMESPACE_URL, f"kadoku/demo-products/v1/{name}"))
        if stable_id in ids or name in names:
            continue
        db.add(Product(
            id=stable_id, name=name, description=desc, category=category,
            price_minor=price, currency="USD", stock=10,
            interests=interests, occasions=occasions, styles=styles,
            emoji=emoji, image_url=None, demo_only=True,
        ))
        names.add(name)
        ids.add(stable_id)
        added += 1

    db.commit()
    return added

