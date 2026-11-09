"""Illustrative gifts only. Do not publish as purchasable real inventory."""
from sqlalchemy import select
from app.db.session import SessionLocal
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


# Curated demo illustrations. Files live in apps/web/public/products/.
# They are generated concept images, not supplier photos or actual inventory.
IMAGE_URLS = {
    "Garden Lover's Box": "/products/garden-lovers-box.webp",
    "Artisan Coffee Ritual": "/products/artisan-coffee-ritual.webp",
    "Handmade Tea Box": "/products/handmade-tea-box.webp",
    "Book Lover Bundle": "/products/book-lover-bundle.webp",
    "Cozy Evening Box": "/products/cozy-evening-box.webp",
}


def seed(db):
    """Populate a blank demo DB, or fill missing image paths on existing rows.

    Existing product attributes (including user-edited prices and stock) remain
    untouched. Custom image URLs are never overwritten.
    """
    if db.scalar(select(Product.id).limit(1)):
        changed = False
        for product in db.scalars(select(Product)).all():
            image_url = IMAGE_URLS.get(product.name)
            if image_url and not product.image_url:
                product.image_url = image_url
                changed = True
        if changed:
            db.commit()
        return 0
    for name, desc, category, price, interests, occasions, styles, emoji in SAMPLES:
        db.add(Product(name=name, description=desc, category=category,
                       price_minor=price, currency="USD", stock=10,
                       interests=interests, occasions=occasions, styles=styles,
                       emoji=emoji, image_url=IMAGE_URLS.get(name), demo_only=True))
    db.commit()
    return len(SAMPLES)


if __name__ == "__main__":
    with SessionLocal() as db:
        print(f"Seeded {seed(db)} demo-only products")
