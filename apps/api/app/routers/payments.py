"""Sandbox payment recovery and admin refund operations."""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import required_admin, required_super_admin, required_user
from app.db.session import get_db
from app.integrations.paypal import PayPalClient
from app.models import Order, PaymentRefund
from app.routers.checkout import verified_capture

router = APIRouter(prefix="/api/v1", tags=["payments"])


class RefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    amount_minor: int = Field(gt=0, le=10_000_000)


class RefundOut(BaseModel):
    request_key: str
    amount_minor: int
    currency: str
    status: str
    paypal_refund_id: str | None = None


def refund_out(refund: PaymentRefund) -> RefundOut:
    return RefundOut(
        request_key=refund.request_key, amount_minor=refund.amount_minor,
        currency=refund.currency, status=refund.status,
        paypal_refund_id=refund.paypal_refund_id,
    )


def checked_refund(data: dict, amount_minor: int, currency: str) -> tuple[str, str]:
    """Accept only a matching refund ID, amount, currency and known status."""
    if not isinstance(data, dict):
        raise HTTPException(502, "Unexpected PayPal refund response")
    refund_id, status, amount = data.get("id"), data.get("status"), data.get("amount")
    if not isinstance(refund_id, str) or not (1 <= len(refund_id) <= 64):
        raise HTTPException(502, "Missing PayPal refund reference")
    if status not in ("PENDING", "COMPLETED", "FAILED"):
        raise HTTPException(502, "Unexpected PayPal refund status")
    if not isinstance(amount, dict) or amount.get("currency_code") != currency:
        raise HTTPException(502, "PayPal refund currency mismatch")
    try:
        cents = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise HTTPException(502, "Invalid PayPal refund amount") from exc
    if not cents.is_finite() or cents != amount_minor:
        raise HTTPException(502, "PayPal refund amount mismatch")
    return refund_id, status.lower()


def completed_refunds(db: Session, order_id: str) -> int:
    return db.scalar(select(func.coalesce(func.sum(PaymentRefund.amount_minor), 0)).where(
        PaymentRefund.order_id == order_id, PaymentRefund.status == "completed"
    )) or 0


def apply_refund_result(db: Session, order: Order, refund: PaymentRefund, response: dict) -> None:
    refund_id, status = checked_refund(response, refund.amount_minor, refund.currency)
    if refund.paypal_refund_id and refund.paypal_refund_id != refund_id:
        raise HTTPException(409, "PayPal refund reference changed")
    refund.paypal_refund_id = refund_id
    refund.status = status
    if status == "completed":
        refunded = completed_refunds(db, order.id)
        # Recalculate after flushing the current refund's new status.
        db.flush()
        refunded = completed_refunds(db, order.id)
        if refunded > order.price_snapshot_minor:
            raise HTTPException(409, "Refunded amount exceeds captured total")
        order.status = "refunded" if refunded == order.price_snapshot_minor else "partially_refunded"
    db.commit()


@router.post("/orders/{order_id}/reconcile")
async def reconcile_checkout(order_id: str, user_id: str = Depends(required_user),
                             db: Session = Depends(get_db)):
    """Recover a completed capture when the checkout response was lost."""
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user_id).with_for_update())
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in ("approval_pending", "paid") or not order.paypal_order_id:
        raise HTTPException(409, "Order is not awaiting payment reconciliation")
    data = await PayPalClient().get_order(order.paypal_order_id)
    if not isinstance(data, dict) or data.get("id") != order.paypal_order_id:
        raise HTTPException(502, "PayPal order reference mismatch")
    units = data.get("purchase_units")
    if not isinstance(units, list) or len(units) != 1 or not isinstance(units[0], dict):
        raise HTTPException(502, "Unexpected PayPal order details")
    unit = units[0]
    if unit.get("custom_id") != order.id or unit.get("reference_id", order.id) != order.id:
        raise HTTPException(409, "PayPal order ownership mismatch")
    if data.get("status") in ("CREATED", "APPROVED"):
        if order.status == "paid":
            raise HTTPException(409, "Local and PayPal payment states disagree")
        return {"status": order.status, "order_id": order.id, "reconciled": False}
    if data.get("status") != "COMPLETED":
        raise HTTPException(409, "PayPal has not confirmed a completed capture")
    capture_id = verified_capture(data, order.price_snapshot_minor, order.currency)
    if not capture_id or (order.paypal_capture_id and order.paypal_capture_id != capture_id):
        raise HTTPException(409, "PayPal capture details do not match this order")
    order.paypal_capture_id = capture_id
    order.status = "paid"
    db.commit()
    return {"status": "paid", "order_id": order.id, "reconciled": True}


@router.get("/admin/orders/{order_id}/refunds", response_model=list[RefundOut])
def list_refunds(order_id: str, _: str = Depends(required_admin),
                 db: Session = Depends(get_db)):
    if db.get(Order, order_id) is None:
        raise HTTPException(404, "Order not found")
    rows = db.scalars(
        select(PaymentRefund).where(PaymentRefund.order_id == order_id)
        .order_by(PaymentRefund.created_at, PaymentRefund.id)
    ).all()
    return [refund_out(row) for row in rows]


@router.post("/admin/orders/{order_id}/refund", response_model=RefundOut)
async def refund_order(order_id: str, payload: RefundRequest,
                       _: str = Depends(required_super_admin),
                       db: Session = Depends(get_db)):
    """Refund a Sandbox capture, keyed for safe retries after timeouts."""
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(404, "Order not found")
    if not order.paypal_capture_id or order.currency != "USD":
        raise HTTPException(409, "Only captured USD orders can be refunded")
    request_key = str(payload.request_key)
    existing = db.scalar(select(PaymentRefund).where(
        PaymentRefund.order_id == order.id, PaymentRefund.request_key == request_key
    ))
    if existing and existing.amount_minor != payload.amount_minor:
        raise HTTPException(409, "Request key was already used for a different amount")
    if existing and existing.status != "pending":
        return refund_out(existing)
    if order.status not in ("paid", "partially_refunded"):
        raise HTTPException(409, "Order is not eligible for a refund")
    if order.fulfillment_status != "unfulfilled":
        raise HTTPException(409, "Refund requires manual review after fulfillment begins")
    if not existing:
        if db.scalar(select(PaymentRefund.id).where(
            PaymentRefund.order_id == order.id, PaymentRefund.status == "pending"
        )):
            raise HTTPException(409, "Resolve the outstanding refund before starting another")
        remaining = order.price_snapshot_minor - completed_refunds(db, order.id)
        if payload.amount_minor > remaining:
            raise HTTPException(409, "Refund exceeds remaining captured amount")
    paypal = PayPalClient()
    refund = existing or PaymentRefund(
        order_id=order.id, request_key=request_key, amount_minor=payload.amount_minor,
        currency=order.currency, status="pending",
    )
    if not existing:
        db.add(refund)
        db.commit()  # Record the retry key before contacting PayPal.
    if refund.paypal_refund_id:
        data = await paypal.get_refund(refund.paypal_refund_id)
    else:
        data = await paypal.refund_capture(
            order.paypal_capture_id, refund.amount_minor, refund.currency, request_key
        )
    apply_refund_result(db, order, refund, data)
    return refund_out(refund)
