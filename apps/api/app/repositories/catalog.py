from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Product


def available_products(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).where(Product.active.is_(True), Product.stock > 0)).all())


def get_product(db: Session, product_id: str) -> Product | None:
    return db.get(Product, product_id)
