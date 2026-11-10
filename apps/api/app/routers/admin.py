"""Admin-only catalog and Sandbox order operations.

Access is enforced on *every* endpoint against verified Better Auth JWT IDs.
No PayPal capture, payment status overrides or hard deletes are exposed here.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.core.auth import required_admin
from app.db.session import get_db
from app.models import Order, Product

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(required_admin)],
)


Tag = str


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=64)
    price_minor: int = Field(ge=1, le=10_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    active: bool = True
    emoji: str = Field(default="🎁", min_length=1, max_length=12)
    interests: list[Tag] = Field(default_factory=list, max_length=10)
    occasions: list[Tag] = Field(default_factory=list, max_length=10)
    styles: list[Tag] = Field(default_factory=list, max_length=10)

    @field_validator("name", "description", "category", "emoji")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value may not be blank")
        return value

    @field_validator("interests", "occasions", "styles")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        cleaned = [item.strip().lower() for item in values]
        if any(not item or len(item) > 60 for item in cleaned):
            raise ValueError("Tags must contain 1 to 60 characters")
        return list(dict.fromkeys(cleaned))


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    price_minor: int | None = Field(default=None, ge=1, le=10_000_000)
    stock: int | None = Field(default=None, ge=0, le=1_000_000)
    active: bool | None = None
    emoji: str | None = Field(default=None, min_length=1, max_length=12)
    interests: list[Tag] | None = Field(default=None, max_length=10)
    occasions: list[Tag] | None = Field(default=None, max_length=10)
    styles: list[Tag] | None = Field(default=None, max_length=10)

    @field_validator("name", "description", "category", "emoji")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value may not be blank")
        return value

    @field_validator("interests", "occasions", "styles")
    @classmethod
    def normalize_tags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [item.strip().lower() for item in values]
        if any(not item or len(item) > 60 for item in cleaned):
            raise ValueError("Tags must contain 1 to 60 characters")
        return list(dict.fromkeys(cleaned))


class AdminProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    category: str
    price_minor: int
    currency: str
    stock: int
    active: bool
    emoji: str
    interests: list[str]
    occasions: list[str]
    styles: list[str]
    image_url: str | None
    demo_only: bool


class ProductPage(BaseModel):
    items: list[AdminProductOut]
    total: int
    page: int
    page_size: int


class Overview(BaseModel):
    products_total: int
    products_active: int
    products_out_of_stock: int
    orders_total: int
    orders_paid: int
    sandbox_paid_minor: int


class AdminOrderOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    price_minor: int
    currency: str
    status: str
    buyer_ref: str
    created_at: datetime


class OrderPage(BaseModel):
    items: list[AdminOrderOut]
    total: int
    page: int
    page_size: int


class AdminCustomerOut(BaseModel):
    """Only buyers with orders; deliberately excludes account emails and addresses."""
    buyer_ref: str
    orders_total: int
    paid_orders: int
    sandbox_paid_minor: int
    latest_order_at: datetime


class CustomerPage(BaseModel):
    items: list[AdminCustomerOut]
    total: int
    page: int
    page_size: int


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(Product)) or 0
    active = db.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))) or 0
    out_of_stock = db.scalar(select(func.count()).select_from(Product).where(Product.stock <= 0)) or 0
    orders_total = db.scalar(select(func.count()).select_from(Order)) or 0
    paid = db.scalar(select(func.count()).select_from(Order).where(Order.status == "paid")) or 0
    sandbox_total = db.scalar(
        select(func.coalesce(func.sum(Order.price_snapshot_minor), 0))
        .where(Order.status == "paid", Order.currency == "USD")
    ) or 0
    return Overview(
        products_total=total, products_active=active,
        products_out_of_stock=out_of_stock, orders_total=orders_total,
        orders_paid=paid, sandbox_paid_minor=sandbox_total,
    )


@router.get("/products", response_model=ProductPage)
def products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str = Query(default="", max_length=120),
    active: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    filters = []
    if search.strip():
        needle = f"%{search.strip()}%"
        filters.append(or_(Product.name.ilike(needle), Product.category.ilike(needle)))
    if active is not None:
        filters.append(Product.active.is_(active))
    total = db.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
    items = db.scalars(
        select(Product).where(*filters)
        .order_by(Product.name, Product.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return ProductPage(items=list(items), total=total, page=page, page_size=page_size)


@router.post("/products", response_model=AdminProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    # Every new item remains a fictional demo. Never imply live fulfillment.
    row = Product(**payload.model_dump(), currency="USD", demo_only=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/products/{product_id}", response_model=AdminProductOut)
def update_product(
    product_id: str, payload: ProductUpdate, db: Session = Depends(get_db)
):
    row = db.get(Product, product_id)
    if row is None:
        raise HTTPException(404, "Product not found")
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(400, "No fields to update")
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Fields cannot be null")
    for name, value in changes.items():
        setattr(row, name, value)
    db.commit()
    db.refresh(row)
    return row


@router.get("/orders", response_model=OrderPage)
def orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str = Query(default="", max_length=24),
    db: Session = Depends(get_db),
):
    filters = [Order.status == status] if status else []
    total = db.scalar(select(func.count()).select_from(Order).where(*filters)) or 0
    rows = db.execute(
        select(Order, Product.name).join(Product, Product.id == Order.product_id)
        .where(*filters).order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        AdminOrderOut(
            id=order.id, product_id=order.product_id, product_name=name,
            price_minor=order.price_snapshot_minor, currency=order.currency,
            status=order.status,
            buyer_ref=("Guest" if not order.user_id else "…" + order.user_id[-8:]),
            created_at=order.created_at,
        )
        for order, name in rows
    ]
    return OrderPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/customers", response_model=CustomerPage)
def customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Read-only, order-linked buyer summary (not all registered accounts).

    Guests cannot be identified uniquely, so they are excluded. Do not return
    authentication IDs, shipping addresses, PayPal identifiers or emails.
    """
    total = db.scalar(
        select(func.count(func.distinct(Order.user_id)))
        .where(Order.user_id.is_not(None))
    ) or 0
    last_order = func.max(Order.created_at)
    rows = db.execute(
        select(
            Order.user_id,
            func.count(Order.id),
            func.sum(case((Order.status == "paid", 1), else_=0)),
            func.coalesce(func.sum(case(
                ((Order.status == "paid") & (Order.currency == "USD"),
                 Order.price_snapshot_minor),
                else_=0,
            )), 0),
            last_order,
        )
        .where(Order.user_id.is_not(None))
        .group_by(Order.user_id)
        .order_by(last_order.desc(), Order.user_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return CustomerPage(
        items=[
            AdminCustomerOut(
                buyer_ref="…" + user_id[-8:],
                orders_total=orders_total,
                paid_orders=paid_orders,
                sandbox_paid_minor=paid_minor,
                latest_order_at=latest,
            )
            for user_id, orders_total, paid_orders, paid_minor, latest in rows
        ],
        total=total, page=page, page_size=page_size,
    )
