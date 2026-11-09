from fastapi import APIRouter, Depends, HTTPException, Request
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session
from app.core.auth import optional_user
from app.db.session import get_db
from app.integrations.paypal import PayPalClient
from app.models import Order, PaymentEvent
from app.repositories.catalog import get_product
from app.schemas.gifts import CheckoutStart, CheckoutCreated, CheckoutCapture

router = APIRouter(prefix="/api/v1", tags=["checkout"])


def verified_capture(data: dict, expected_minor: int, currency: str) -> str | None:
    if data.get("status") != "COMPLETED":
        return None
    for unit in data.get("purchase_units", []):
        for capture in unit.get("payments", {}).get("captures", []):
            amount = capture.get("amount", {})
            try:
                minor = int(Decimal(str(amount.get("value", "0"))) * 100)
            except (TypeError, ValueError, InvalidOperation):
                continue
            if capture.get("status") == "COMPLETED" and minor == expected_minor and amount.get("currency_code") == currency:
                return capture.get("id")
    return None


@router.post("/checkout/paypal/orders", response_model=CheckoutCreated)
async def create_paypal_order(payload: CheckoutStart, db: Session = Depends(get_db),
                              user_id: str | None = Depends(optional_user)):
    paypal = PayPalClient()
    product = get_product(db, payload.product_id)
    if not product or not product.active or product.stock <= 0:
        raise HTTPException(409, "Product unavailable")
    if not product.demo_only or product.currency != "USD":
        raise HTTPException(409, "Sandbox checkout supports USD demo products only")
    order = Order(user_id=user_id, product_id=product.id,
                  price_snapshot_minor=product.price_minor, currency="USD")
    db.add(order)
    db.commit()
    db.refresh(order)
    response = await paypal.create_order(order.id, order.price_snapshot_minor)
    approval_url = next((link["href"] for link in response.get("links", []) if link.get("rel") == "payer-action"), None)
    if not approval_url or not response.get("id"):
        raise HTTPException(502, "PayPal did not return a buyer approval link")
    order.paypal_order_id = response["id"]
    order.status = "approval_pending"
    db.commit()
    return CheckoutCreated(order_id=order.id, approval_url=approval_url, status=order.status)


@router.post("/checkout/paypal/capture")
async def capture_paypal_order(payload: CheckoutCapture, db: Session = Depends(get_db)):
    # A local order ID is a bearer of limited status info; capture still requires actual
    # PayPal buyer approval. No sensitive order details returned to the caller.
    order = db.get(Order, payload.order_id)
    if not order or order.paypal_order_id != payload.paypal_order_id:
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
    # Capture is the authoritative reconciliation step for this starter. Events
    # are durably logged and deduplicated, but not used to mark orders as paid.
    db.add(PaymentEvent(provider_event_id=event_id, event_type=event_type))
    db.commit()
    return {"status": "received"}
