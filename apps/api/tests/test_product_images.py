"""Five curated AI-generated demo images are wired to existing catalog items."""
from app.seed import IMAGE_URLS, seed
from app.models import Product


def test_demo_catalog_has_five_image_paths(client):
    products = client.get("/api/v1/products")
    assert products.status_code == 200
    rows = products.json()
    assert len(rows) == 100
    matches = {row["name"]: row["image_url"] for row in rows if row["image_url"]}
    assert matches == IMAGE_URLS
    assert all(value.startswith("/products/") and value.endswith(".webp")
               for value in matches.values())


def test_recommendations_expose_catalog_image_not_generated_image(client):
    response = client.post(
        "/api/v1/gifts/recommendations",
        json={"prompt": "My mom loves gardening. Birthday gift under $100."},
    )
    assert response.status_code == 200
    for gift in response.json()["recommendations"]:
        assert "image_url" in gift
        assert gift["image_url"] in IMAGE_URLS.values() or gift["image_url"] is None


def test_reseeding_existing_catalog_backfills_missing_image_but_not_custom_images(database):
    with database() as db:
        custom = db.query(Product).filter_by(name="Handmade Tea Box").one()
        custom.image_url = "/products/custom-tea-photo.webp"
        missing = db.query(Product).filter_by(name="Book Lover Bundle").one()
        missing.image_url = None
        db.commit()

    with database() as db:
        assert seed(db) == 0
        assert db.query(Product).filter_by(name="Handmade Tea Box").one().image_url == "/products/custom-tea-photo.webp"
        assert db.query(Product).filter_by(name="Book Lover Bundle").one().image_url == IMAGE_URLS["Book Lover Bundle"]
