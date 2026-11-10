"""Read-only, privacy-minimised commerce analytics for embedded AG Studio.

Values represent PayPal Sandbox events, *not* live revenue. All aggregation
happens on the server; never send customer, address, payment or token data to a
browser analytics engine or an LLM.
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.auth import required_admin
from app.db.session import get_db
from app.models import Order, Product

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin-analytics"],
    dependencies=[Depends(required_admin)],
)

PaymentState = Literal["pending", "approval_pending", "paid", "cancelled"]


class AnalyticsSummary(BaseModel):
    catalog_products: int
    active_products: int
    orders: int
    paid_orders: int
    awaiting_fulfillment: int
    sandbox_captured_minor: int


class CatalogRow(BaseModel):
    product_id: str
    product_name: str
    category: str
    sku: str | None
    stock: int
    active: bool
    price_usd: float
    demo_only: bool


class ProductPerformanceRow(BaseModel):
    product_id: str
    product_name: str
    category: str
    orders: int
    paid_orders: int
    approval_pending: int
    cancelled: int
    sandbox_captured_usd: float


class DailyOrdersRow(BaseModel):
    day: str
    orders: int
    paid_orders: int
    sandbox_captured_usd: float


class PaymentStatusRow(BaseModel):
    payment_status: str
    orders: int
    sandbox_captured_usd: float


class FulfillmentStatusRow(BaseModel):
    fulfillment_status: str
    paid_orders: int


class AnalyticsResponse(BaseModel):
    days: int
    currency: Literal["USD"] = "USD"
    environment: Literal["sandbox"] = "sandbox"
    generated_at: datetime
    summary: AnalyticsSummary
    catalog: list[CatalogRow]
    product_performance: list[ProductPerformanceRow]
    daily_orders: list[DailyOrdersRow]
    payment_statuses: list[PaymentStatusRow]
    fulfillment_statuses: list[FulfillmentStatusRow]


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(
    days: Literal[7, 30, 90] = 30,
    db: Session = Depends(get_db),
):
    """Summaries suitable for client-side exploration, never raw orders or PII."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    within = (Order.created_at >= cutoff,)

    product_rows = db.scalars(
        select(Product).order_by(Product.name, Product.id)
    ).all()
    catalog = [
        CatalogRow(
            product_id=p.id, product_name=p.name, category=p.category,
            sku=p.sku, stock=p.stock, active=p.active,
            price_usd=p.price_minor / 100,
            demo_only=p.demo_only,
        )
        for p in product_rows
    ]

    paid_count = case((Order.status == "paid", 1), else_=0)
    pending_count = case((Order.status == "approval_pending", 1), else_=0)
    cancelled_count = case((Order.status == "cancelled", 1), else_=0)
    paid_minor = case(
        ((Order.status == "paid") & (Order.currency == "USD"),
         Order.price_snapshot_minor),
        else_=0,
    )

    performance = db.execute(
        select(
            Product.id, Product.name, Product.category,
            func.count(Order.id),
            func.sum(paid_count), func.sum(pending_count),
            func.sum(cancelled_count), func.sum(paid_minor),
        )
        .select_from(Order)
        .join(Product, Order.product_id == Product.id)
        .where(*within)
        .group_by(Product.id, Product.name, Product.category)
        .order_by(func.sum(paid_count).desc(), Product.name, Product.id)
    ).all()
    product_performance = [
        ProductPerformanceRow(
            product_id=product_id, product_name=name, category=category,
            orders=count, paid_orders=paid or 0,
            approval_pending=pending or 0, cancelled=cancelled or 0,
            sandbox_captured_usd=(captured or 0) / 100,
        )
        for product_id, name, category, count, paid, pending, cancelled, captured
        in performance
    ]

    daily = db.execute(
        select(
            func.date(Order.created_at),
            func.count(Order.id),
            func.sum(paid_count),
            func.sum(paid_minor),
        )
        .where(*within)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    ).all()
    daily_orders = [
        DailyOrdersRow(
            day=str(day), orders=count, paid_orders=paid or 0,
            sandbox_captured_usd=(captured or 0) / 100,
        )
        for day, count, paid, captured in daily
    ]

    payments = db.execute(
        select(Order.status, func.count(Order.id), func.sum(paid_minor))
        .where(*within)
        .group_by(Order.status)
        .order_by(Order.status)
    ).all()
    payment_statuses = [
        PaymentStatusRow(
            payment_status=status, orders=count,
            sandbox_captured_usd=(captured or 0) / 100,
        )
        for status, count, captured in payments
    ]

    fulfillment = db.execute(
        select(Order.fulfillment_status, func.count(Order.id))
        .where(*within, Order.status == "paid")
        .group_by(Order.fulfillment_status)
        .order_by(Order.fulfillment_status)
    ).all()
    fulfillment_statuses = [
        FulfillmentStatusRow(fulfillment_status=status, paid_orders=count)
        for status, count in fulfillment
    ]

    order_count = sum(item.orders for item in payment_statuses)
    paid_orders = sum(item.paid_orders for item in fulfillment_statuses)
    awaiting = next(
        (item.paid_orders for item in fulfillment_statuses
         if item.fulfillment_status == "unfulfilled"), 0
    )
    sandbox_minor = int(round(
        sum(item.sandbox_captured_usd for item in payment_statuses) * 100
    ))
    return AnalyticsResponse(
        days=days,
        generated_at=now,
        summary=AnalyticsSummary(
            catalog_products=len(catalog),
            active_products=sum(1 for p in catalog if p.active),
            orders=order_count, paid_orders=paid_orders,
            awaiting_fulfillment=awaiting,
            sandbox_captured_minor=sandbox_minor,
        ),
        catalog=catalog,
        product_performance=product_performance,
        daily_orders=daily_orders,
        payment_statuses=payment_statuses,
        fulfillment_statuses=fulfillment_statuses,
    )
