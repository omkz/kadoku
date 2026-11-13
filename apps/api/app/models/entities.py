from __future__ import annotations
from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship as orm_relationship
from app.db.base import Base


def uid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    interests: Mapped[list] = mapped_column(JSON, default=list)
    occasions: Mapped[list] = mapped_column(JSON, default=list)
    styles: Mapped[list] = mapped_column(JSON, default=list)
    emoji: Mapped[str] = mapped_column(String(12), default="🎁")
    image_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    demo_only: Mapped[bool] = mapped_column(Boolean, default=True)


class Recipient(Base):
    __tablename__ = "recipients"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    relationship: Mapped[str | None] = mapped_column(String(80))
    interests: Mapped[list] = mapped_column(JSON, default=list)
    avoids: Mapped[list] = mapped_column(JSON, default=list)
    usual_budget_minor: Mapped[int | None] = mapped_column(Integer)
    occasions: Mapped[list[Occasion]] = orm_relationship(back_populates="recipient", cascade="all, delete-orphan")


class Occasion(Base):
    __tablename__ = "occasions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("recipients.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), default="birthday")
    month: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recipient: Mapped[Recipient] = orm_relationship(back_populates="occasions")


class RecommendationUsage(Base):
    __tablename__ = "recommendation_usage"
    __table_args__ = (UniqueConstraint("subject", "day", name="uq_usage_subject_day"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(128), index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(String(128), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    price_snapshot_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(24), default="pending")
    shipping_address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fulfillment_status: Mapped[str] = mapped_column(String(24), nullable=False, default="unfulfilled")
    tracking_carrier: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentRefund(Base):
    __tablename__ = "payment_refunds"
    __table_args__ = (UniqueConstraint("order_id", "request_key", name="uq_refund_order_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    request_key: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    paypal_refund_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider_event_id: Mapped[str] = mapped_column(String(128), unique=True)
    event_type: Mapped[str] = mapped_column(String(128))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class FulfillmentEvent(Base):
    """Immutable operational audit log; does not affect PayPal state."""
    __tablename__ = "fulfillment_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    actor_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
