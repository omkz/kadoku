from sqlalchemy import case, select
from sqlalchemy.orm import Session
from app.models import Product


def available_products(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True), Product.stock > 0)).all())


# Editorial selection for the homepage. Not based on sales or engagement data.
FEATURED_NAMES = (
    "Artisan Coffee Ritual",
    "Garden Lover's Box",
    "Cozy Evening Box",
    "Book Lover Bundle",
    "Handmade Tea Box",
    "Mini Watercolor Studio",
)


def featured_products(db: Session) -> list[Product]:
    """Only fetch six active, in-stock gifts, in editorial order.

    If a featured item is unavailable, fill from the remaining catalog in a
    deterministic order. SQL LIMIT applies before transferring rows to Python.
    """
    editorial_order = case(
        *((Product.name == name, index) for index, name in enumerate(FEATURED_NAMES)),
        else_=len(FEATURED_NAMES),
    )
    stmt = (
        select(Product)
        .where(Product.active.is_(True), Product.stock > 0)
        .order_by(editorial_order, Product.name, Product.id)
        .limit(6)
    )
    return list(db.scalars(stmt).all())


def get_product(db: Session, product_id: str) -> Product | None:
    return db.get(Product, product_id)
