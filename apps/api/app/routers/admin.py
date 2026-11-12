"""Admin-only catalog and order operations.

Access is enforced on *every* endpoint against verified Better Auth JWT IDs.
No PayPal capture, payment status overrides or hard deletes are exposed here.
"""
from datetime import datetime, timezone
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import bindparam, case, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.auth import required_admin
from app.db.session import get_db
from app.models import FulfillmentEvent, Order, Product

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
    dependencies=[Depends(required_admin)],
)


Tag = str
SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,63}$")
IMAGE_PATTERN = re.compile(r"^/products/[A-Za-z0-9][A-Za-z0-9_-]*\.(?:webp|png|jpg|jpeg)$")
FULFILLMENT_STATES = ("unfulfilled", "processing", "shipped", "delivered")
NEXT_FULFILLMENT_STATE = {
    "unfulfilled": "processing",
    "processing": "shipped",
    "shipped": "delivered",
}


def normalize_sku(value: str | None) -> str | None:
    if value is None:
        return None
    sku = value.strip().upper()
    if not SKU_PATTERN.fullmatch(sku):
        raise ValueError("SKU must be 3–64 characters: A-Z, 0-9, period, hyphen or underscore")
    return sku


def validate_image_url(value: str | None) -> str | None:
    """Only checked-in first-party public assets, no remote URLs or traversal."""
    if value is None or value == "":
        return None
    if not IMAGE_PATTERN.fullmatch(value):
        raise ValueError("Use a local /products/<filename>.webp/png/jpg/jpeg asset")
    return value


def assert_sku_available(db: Session, sku: str | None, *, exclude_id: str | None = None) -> None:
    if not sku:
        return
    existing = db.scalar(select(Product.id).where(Product.sku == sku))
    if existing is not None and existing != exclude_id:
        raise HTTPException(409, "SKU already exists")



class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    category: str = Field(min_length=1, max_length=64)
    price_minor: int = Field(ge=1, le=10_000_000)
    stock: int = Field(ge=0, le=1_000_000)
    active: bool = True
    sku: str | None = Field(default=None, max_length=64)
    image_url: str | None = Field(default=None, max_length=255)
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


    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str | None) -> str | None:
        return normalize_sku(value)

    @field_validator("image_url")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        return validate_image_url(value)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    price_minor: int | None = Field(default=None, ge=1, le=10_000_000)
    stock: int | None = Field(default=None, ge=0, le=1_000_000)
    active: bool | None = None
    sku: str | None = Field(default=None, max_length=64)
    image_url: str | None = Field(default=None, max_length=255)
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


    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str | None) -> str | None:
        return normalize_sku(value)

    @field_validator("image_url")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        return validate_image_url(value)


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
    sku: str | None
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
    buyers_total: int
    orders_paid: int
    awaiting_fulfillment: int
    sandbox_paid_minor: int


class AdminOrderOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    price_minor: int
    currency: str
    status: str
    fulfillment_status: str
    buyer_ref: str
    created_at: datetime


class OrderPage(BaseModel):
    items: list[AdminOrderOut]
    total: int
    page: int
    page_size: int


class FulfillmentChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_status: str
    to_status: str
    tracking_carrier: str | None = Field(default=None, max_length=80)
    tracking_number: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("tracking_carrier", "tracking_number", "note")
    @classmethod
    def trim_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class FulfillmentAuditOut(BaseModel):
    from_status: str
    to_status: str
    actor_ref: str
    note: str | None
    created_at: datetime


class AdminOrderDetail(AdminOrderOut):
    shipping_address: dict | None
    tracking_carrier: str | None
    tracking_number: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None
    history: list[FulfillmentAuditOut]


class AdminCustomerOut(BaseModel):
    """Order-linked buyers, with minimal identity data for authorized admins."""
    buyer_ref: str
    name: str | None
    email: str | None
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
    buyers_total = db.scalar(
        select(func.count(func.distinct(Order.user_id)))
        .where(Order.user_id.is_not(None))
    ) or 0
    paid = db.scalar(select(func.count()).select_from(Order).where(Order.status == "paid")) or 0
    awaiting_fulfillment = db.scalar(
        select(func.count()).select_from(Order)
        .where(Order.status == "paid", Order.fulfillment_status == "unfulfilled")
    ) or 0
    sandbox_total = db.scalar(
        select(func.coalesce(func.sum(Order.price_snapshot_minor), 0))
        .where(Order.status == "paid", Order.currency == "USD")
    ) or 0
    return Overview(
        products_total=total, products_active=active,
        products_out_of_stock=out_of_stock, orders_total=orders_total,
        buyers_total=buyers_total, orders_paid=paid,
        awaiting_fulfillment=awaiting_fulfillment, sandbox_paid_minor=sandbox_total,
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
    # New listings remain demo-only until supplier verification and live-commerce
    # onboarding are implemented. Operators can still prepare real catalog metadata.
    assert_sku_available(db, payload.sku)
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
    if any(value is None for name, value in changes.items() if name not in ("sku", "image_url")):
        raise HTTPException(422, "Fields cannot be null")
    if "sku" in changes:
        assert_sku_available(db, changes["sku"], exclude_id=product_id)
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
    fulfillment: str = Query(default="", max_length=24),
    db: Session = Depends(get_db),
):
    if fulfillment and fulfillment not in FULFILLMENT_STATES:
        raise HTTPException(422, "Invalid fulfillment status")
    filters = [Order.status == status] if status else []
    if fulfillment:
        filters.append(Order.fulfillment_status == fulfillment)
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
            status=order.status, fulfillment_status=order.fulfillment_status,
            buyer_ref=("Guest" if not order.user_id else "…" + order.user_id[-8:]),
            created_at=order.created_at,
        )
        for order, name in rows
    ]
    return OrderPage(items=items, total=total, page=page, page_size=page_size)


def admin_order_detail(db: Session, order: Order, product_name: str) -> AdminOrderDetail:
    history = db.scalars(
        select(FulfillmentEvent)
        .where(FulfillmentEvent.order_id == order.id)
        .order_by(FulfillmentEvent.created_at.asc(), FulfillmentEvent.id.asc())
    ).all()
    return AdminOrderDetail(
        id=order.id, product_id=order.product_id, product_name=product_name,
        price_minor=order.price_snapshot_minor, currency=order.currency,
        status=order.status, fulfillment_status=order.fulfillment_status,
        buyer_ref="Guest" if not order.user_id else "…" + order.user_id[-8:],
        created_at=order.created_at,
        shipping_address=order.shipping_address,
        tracking_carrier=order.tracking_carrier, tracking_number=order.tracking_number,
        shipped_at=order.shipped_at, delivered_at=order.delivered_at,
        history=[
            FulfillmentAuditOut(
                from_status=event.from_status, to_status=event.to_status,
                actor_ref="…" + event.actor_user_id[-8:],
                note=event.note, created_at=event.created_at,
            )
            for event in history
        ],
    )


@router.get("/orders/{order_id}", response_model=AdminOrderDetail)
def get_admin_order(order_id: str, db: Session = Depends(get_db)):
    row = db.execute(
        select(Order, Product.name)
        .join(Product, Product.id == Order.product_id)
        .where(Order.id == order_id)
    ).first()
    if not row:
        raise HTTPException(404, "Order not found")
    order, name = row
    return admin_order_detail(db, order, name)


@router.post("/orders/{order_id}/fulfillment", response_model=AdminOrderDetail)
def update_fulfillment(
    order_id: str,
    payload: FulfillmentChange,
    actor: str = Depends(required_admin),
    db: Session = Depends(get_db),
):
    """Explicit step-by-step physical operations, independent of payment state.

    Lock order row in Postgres so two admins cannot advance the same state at
    once. The expected status is also checked to reject stale UI submissions.
    """
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status != "paid":
        raise HTTPException(409, "Payment must be captured before order processing")
    current = order.fulfillment_status
    if payload.expected_status != current:
        raise HTTPException(409, "Order status changed; refresh before editing")
    if NEXT_FULFILLMENT_STATE.get(current) != payload.to_status:
        raise HTTPException(409, "Invalid fulfillment transition")
    if payload.to_status == "shipped":
        if not isinstance(order.shipping_address, dict) or not order.shipping_address.get("address_line_1") or not order.shipping_address.get("country"):
            raise HTTPException(409, "Shipping address required before marking shipped")
        if not payload.tracking_carrier or not payload.tracking_number:
            raise HTTPException(422, "Carrier and tracking number are required to ship")
    elif payload.tracking_carrier is not None or payload.tracking_number is not None:
        raise HTTPException(422, "Tracking details are only accepted when shipping")
    if payload.to_status == "shipped":
        order.tracking_carrier = payload.tracking_carrier
        order.tracking_number = payload.tracking_number
        order.shipped_at = datetime.now(timezone.utc)
    if payload.to_status == "delivered":
        order.delivered_at = datetime.now(timezone.utc)
    order.fulfillment_status = payload.to_status
    db.add(FulfillmentEvent(
        order_id=order.id, actor_user_id=actor,
        from_status=current, to_status=payload.to_status, note=payload.note,
    ))
    db.commit()
    db.refresh(order)
    product_name = db.scalar(select(Product.name).where(Product.id == order.product_id))
    return admin_order_detail(db, order, product_name)


@router.get("/customers", response_model=CustomerPage)
def customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Admin-only buyer list. Names/emails come from Better Auth, not orders.

    Only registered buyers with orders are included. Guest orders are excluded.
    Never return shipping addresses, provider IDs or raw auth user IDs.
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

    # Better Auth owns the "user" table; keep its schema separate from
    # Kadoku's Alembic ORM models. Parameterized batch lookup avoids N+1
    # queries and never exposes authentication secrets.
    identities = {}
    if rows:
        ids = [user_id for user_id, *_ in rows]
        query = text(
            'SELECT id, name, email FROM "user" WHERE id IN :ids'
        ).bindparams(bindparam("ids", expanding=True))
        identities = {
            row.id: row
            for row in db.execute(query, {"ids": ids}).all()
        }

    return CustomerPage(
        items=[
            AdminCustomerOut(
                buyer_ref="…" + user_id[-8:],
                name=identities[user_id].name if user_id in identities else None,
                email=identities[user_id].email if user_id in identities else None,
                orders_total=orders_total,
                paid_orders=paid_orders,
                sandbox_paid_minor=paid_minor,
                latest_order_at=latest,
            )
            for user_id, orders_total, paid_orders, paid_minor, latest in rows
        ],
        total=total, page=page, page_size=page_size,
    )
