from fastapi import APIRouter, Depends, HTTPException, Request
from decimal import Decimal, InvalidOperation
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.core.auth import required_user
from app.db.session import get_db
from app.integrations.paypal import PayPalClient
from app.models import Order, PaymentEvent, Product
from app.repositories.catalog import get_product
from app.schemas.gifts import CheckoutStart, CheckoutCreated, CheckoutCapture, OrderSummary, OrderDetail

router = APIRouter(prefix="/api/v1", tags=["checkout"])


def verified_capture(data: dict, expected_minor: int, currency: str) -> str | None:
    """Require one completed capture with exact currency and cent amount."""
    if not isinstance(data, dict) or data.get("status") != "COMPLETED":
        return None
    units = data.get("purchase_units")
    if not isinstance(units, list) or len(units) != 1:
        return None
    payments = units[0].get("payments", {}) if isinstance(units[0], dict) else {}
    captures = payments.get("captures") if isinstance(payments, dict) else None
    if not isinstance(captures, list) or len(captures) != 1:
        return None
    capture = captures[0]
    if not isinstance(capture, dict) or capture.get("status") != "COMPLETED":
        return None
    amount = capture.get("amount")
    if not isinstance(amount, dict) or amount.get("currency_code") != currency:
        return None
    capture_id = capture.get("id")
    if not isinstance(capture_id, str) or not capture_id:
        return None
    try:
        cents = Decimal(str(amount["value"])) * 100
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if not cents.is_finite() or cents != expected_minor:
        return None
    return capture_id


def approval_link(response: dict) -> str | None:
    """Follow PayPal's URL, never an untrusted or non-Sandbox redirect."""
    from urllib.parse import urlsplit

    if not isinstance(response, dict):
        return None
    links = response.get("links")
    if not isinstance(links, list):
        return None
    for rel in ("payer-action", "approve"):
        for link in links:
            if not isinstance(link, dict) or link.get("rel") != rel:
                continue
            href = link.get("href")
            if not isinstance(href, str):
                continue
            try:
                parsed = urlsplit(href)
                valid_host = parsed.hostname == "sandbox.paypal.com" or (
                    parsed.hostname is not None and parsed.hostname.endswith(".sandbox.paypal.com")
                )
                if parsed.scheme == "https" and valid_host and parsed.username is None and parsed.password is None:
                    return href
            except ValueError:
                continue
    return None



def order_summary(order: Order, product: Product) -> dict:
    """Return the user's order with its recorded price, not today's catalog price."""
    return {
        "id": order.id,
        "product_id": order.product_id,
        "product_name": product.name,
        "product_emoji": product.emoji,
        "price_minor": order.price_snapshot_minor,
        "currency": order.currency,
        "status": order.status,
        "created_at": order.created_at,
    }


@router.get("/orders", response_model=list[OrderSummary])
def my_orders(user_id: str = Depends(required_user), db: Session = Depends(get_db)):
    """Newest 100 orders owned by the authenticated user (guest orders are excluded)."""
    rows = db.execute(
        select(Order, Product)
        .join(Product, Product.id == Order.product_id)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(100)
    ).all()
    return [order_summary(order, product) for order, product in rows]


@router.get("/orders/{order_id}", response_model=OrderDetail)
def my_order(order_id: str, user_id: str = Depends(required_user),
             db: Session = Depends(get_db)):
    row = db.execute(
        select(Order, Product)
        .join(Product, Product.id == Order.product_id)
        .where(Order.id == order_id, Order.user_id == user_id)
    ).first()
    if not row:
        raise HTTPException(404, "Order not found")
    order, product = row
    return {
        **order_summary(order, product),
        "paypal_order_id": order.paypal_order_id,
        "paypal_capture_id": order.paypal_capture_id,
        "shipping_address": order.shipping_address,
    }

@router.post("/orders/{order_id}/cancel")
def cancel_my_order(order_id: str, user_id: str = Depends(required_user),
                    db: Session = Depends(get_db)):
    """Cancel only pending orders atomically; never refund a captured payment."""
    result = db.execute(
        update(Order)
        .where(Order.id == order_id, Order.user_id == user_id,
               Order.status == "approval_pending")
        .values(status="cancelled")
    )
    if result.rowcount:
        db.commit()
        return {"order_id": order_id, "status": "cancelled"}
    db.rollback()
    order = db.get(Order, order_id)
    if order is None or order.user_id != user_id:
        raise HTTPException(404, "Order not found")
    if order.status == "cancelled":
        return {"order_id": order_id, "status": "cancelled"}
    raise HTTPException(409, "This order cannot be cancelled from checkout")


@router.post("/checkout/paypal/orders", response_model=CheckoutCreated)
async def create_paypal_order(payload: CheckoutStart, db: Session = Depends(get_db),
                              user_id: str = Depends(required_user)):
    paypal = PayPalClient()
    product = get_product(db, payload.product_id)
    if not product or not product.active or product.stock <= 0 or product.price_minor <= 0:
        raise HTTPException(409, "Product unavailable")
    if not product.demo_only or product.currency != "USD":
        raise HTTPException(409, "Sandbox checkout supports USD demo products only")
    order = Order(user_id=user_id, product_id=product.id,
                  price_snapshot_minor=product.price_minor, currency="USD",
                  shipping_address=payload.shipping_address.model_dump(mode="json"))
    db.add(order)
    db.commit()
    db.refresh(order)
    response = await paypal.create_order(order.id, order.price_snapshot_minor)
    approval_url = approval_link(response)
    if not approval_url or not isinstance(response.get("id"), str) or not response["id"] or len(response["id"]) > 64:
        raise HTTPException(502, "PayPal did not return a buyer approval link")
    order.paypal_order_id = response["id"]
    order.status = "approval_pending"
    db.commit()
    return CheckoutCreated(order_id=order.id, approval_url=approval_url, status=order.status)


@router.post("/checkout/paypal/capture")
async def capture_paypal_order(payload: CheckoutCapture, db: Session = Depends(get_db),
                               user_id: str = Depends(required_user)):
    # Ownership and approval must match; a PayPal token is insufficient.
    order = db.get(Order, payload.order_id)
    if not order or order.user_id != user_id or order.paypal_order_id != payload.paypal_order_id:
        raise HTTPException(404, "Order not found")
    if order.status == "paid":
        return {"status": "paid", "order_id": order.id}
    if order.status != "approval_pending":
        raise HTTPException(409, "Order not awaiting approval")
    data = await PayPalClient().capture_order(order.paypal_order_id, order.id)
    capture_id = verified_capture(data, order.price_snapshot_minor, order.currency)
    if not capture_id:
        raise HTTPException(409, "Payment was not captured for the expected amount")
    order.status = "paid"
    order.paypal_capture_id = capture_id
    db.commit()
    return {"status": "paid", "order_id": order.id}


@router.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    import json
    raw = await request.body()
    if len(raw) > 256 * 1024:
        raise HTTPException(413, "Webhook payload too large")
    try:
        event = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    paypal = PayPalClient()
    if not await paypal.verify_webhook(dict(request.headers), event):
        raise HTTPException(401, "Webhook signature not verified")
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise HTTPException(400, "Missing event ID")
    if db.query(PaymentEvent).filter_by(provider_event_id=event_id).first():
        return {"status": "already_processed"}
    event_type = event.get("event_type", "unknown")
    # Log/deduplicate webhooks; only verified captures mark orders paid.
    db.add(PaymentEvent(provider_event_id=event_id, event_type=event_type))
    db.commit()
    return {"status": "received"}
