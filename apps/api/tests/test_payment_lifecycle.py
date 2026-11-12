"""Contract tests for PayPal Sandbox recovery and refunds (no network)."""
import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.integrations.paypal import PayPalClient
from app.models import Order, PaymentRefund, Product
from app.routers import payments


def bearer(token_factory, subject="test-user-a"):
    return {"Authorization": "Bearer " + token_factory(sub=subject)}


def make_order(database, *, status="paid", fulfillment="unfulfilled", paypal_order_id="PAYPAL-ORDER-A"):
    with database() as db:
        product = db.scalar(select(Product).limit(1))
        order = Order(
            user_id="test-user-a", product_id=product.id, price_snapshot_minor=6800,
            currency="USD", status=status, fulfillment_status=fulfillment,
            paypal_order_id=paypal_order_id,
            paypal_capture_id="CAP-A" if status != "approval_pending" else None,
        )
        db.add(order)
        db.commit()
        return order.id


def paypal_amount(minor):
    return {"currency_code": "USD", "value": f"{minor // 100}.{minor % 100:02d}"}


def refund_reply(minor, status="COMPLETED", refund_id="REFUND-A"):
    return {"id": refund_id, "status": status, "amount": paypal_amount(minor)}


def payment_order(order_id, status="COMPLETED", amount_minor=6800):
    return {
        "id": "PAYPAL-ORDER-A", "status": status,
        "purchase_units": [{
            "reference_id": order_id, "custom_id": order_id,
            "payments": {"captures": [{
                "id": "CAP-A", "status": "COMPLETED",
                "amount": paypal_amount(amount_minor),
            }]} if status == "COMPLETED" else {},
        }],
    }


def test_reconcile_capture_after_lost_callback(client, database, token_factory, monkeypatch):
    order_id = make_order(database, status="approval_pending")
    class FakePayPal:
        async def get_order(self, paypal_id):
            assert paypal_id == "PAYPAL-ORDER-A"
            return payment_order(order_id)
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    response = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=bearer(token_factory))
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "paid", "order_id": order_id, "reconciled": True}
    with database() as db:
        order = db.get(Order, order_id)
        assert order.paypal_capture_id == "CAP-A"
        assert order.status == "paid"
    assert client.post(f"/api/v1/orders/{order_id}/reconcile", headers=bearer(token_factory)).status_code == 200
    assert client.post(f"/api/v1/orders/{order_id}/reconcile", headers=bearer(token_factory, "other")).status_code == 404
    assert client.post(f"/api/v1/orders/{order_id}/reconcile").status_code == 401


def test_reconcile_never_invents_capture(client, database, token_factory, monkeypatch):
    order_id = make_order(database, status="approval_pending")
    class FakePayPal:
        async def get_order(self, _):
            return payment_order(order_id, status="APPROVED")
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    response = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=bearer(token_factory))
    assert response.status_code == 200
    assert response.json()["status"] == "approval_pending"
    assert response.json()["reconciled"] is False
    with database() as db:
        assert db.get(Order, order_id).paypal_capture_id is None


@pytest.mark.parametrize("change", [
    lambda x: x.update(id="OTHER-ORDER"),
    lambda x: x["purchase_units"][0].update(custom_id="other-local-id"),
    lambda x: x["purchase_units"][0]["payments"]["captures"][0].update(amount=paypal_amount(6801)),
    lambda x: x["purchase_units"][0]["payments"]["captures"][0].update(status="PENDING"),
])
def test_reconcile_rejects_provider_mismatch(client, database, token_factory, monkeypatch, change):
    order_id = make_order(database, status="approval_pending")
    payload = payment_order(order_id)
    change(payload)
    class FakePayPal:
        async def get_order(self, _):
            return payload
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    response = client.post(f"/api/v1/orders/{order_id}/reconcile", headers=bearer(token_factory))
    assert response.status_code in (409, 502)
    with database() as db:
        assert db.get(Order, order_id).status == "approval_pending"


def test_super_admin_full_refund_is_idempotent(client, database, token_factory, set_auth_role, monkeypatch):
    order_id = make_order(database)
    set_auth_role("test-user-a", "super_admin")
    calls = []
    class FakePayPal:
        async def refund_capture(self, capture_id, amount_minor, currency, key):
            calls.append((capture_id, amount_minor, currency, key))
            return refund_reply(amount_minor)
        async def get_refund(self, _):
            raise AssertionError("Completed refund must not be requested again")
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    key = str(uuid4())
    payload = {"request_key": key, "amount_minor": 6800}
    url = f"/api/v1/admin/orders/{order_id}/refund"
    response = client.post(url, json=payload, headers=bearer(token_factory))
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["paypal_refund_id"] == "REFUND-A"
    repeated = client.post(url, json=payload, headers=bearer(token_factory))
    assert repeated.status_code == 200
    assert len(calls) == 1
    assert client.post(url, json={**payload, "amount_minor": 100}, headers=bearer(token_factory)).status_code == 409
    assert client.post(url, json={"request_key": str(uuid4()), "amount_minor": 1},
                       headers=bearer(token_factory)).status_code == 409
    with database() as db:
        assert db.get(Order, order_id).status == "refunded"
        assert len(db.scalars(select(PaymentRefund)).all()) == 1
    audit = client.get(f"/api/v1/admin/orders/{order_id}/refunds", headers=bearer(token_factory))
    assert audit.status_code == 200
    assert audit.json()[0]["amount_minor"] == 6800


def test_partial_refund_remaining_amount(client, database, token_factory, set_auth_role, monkeypatch):
    order_id = make_order(database)
    set_auth_role("test-user-a", "super_admin")
    count = 0
    class FakePayPal:
        async def refund_capture(self, capture_id, amount_minor, currency, key):
            nonlocal count
            count += 1
            return refund_reply(amount_minor, refund_id=f"REFUND-{count}")
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    url = f"/api/v1/admin/orders/{order_id}/refund"
    headers = bearer(token_factory)
    first = client.post(url, json={"request_key":str(uuid4()),"amount_minor":2500}, headers=headers)
    assert first.status_code == 200, first.text
    with database() as db:
        assert db.get(Order, order_id).status == "partially_refunded"
    over = client.post(url, json={"request_key":str(uuid4()),"amount_minor":4301}, headers=headers)
    assert over.status_code == 409
    second = client.post(url, json={"request_key":str(uuid4()),"amount_minor":4300}, headers=headers)
    assert second.status_code == 200, second.text
    with database() as db:
        assert db.get(Order, order_id).status == "refunded"
    assert count == 2


def test_pending_refund_reconciles_using_paypal_refund_id(client, database, token_factory, set_auth_role, monkeypatch):
    order_id = make_order(database)
    set_auth_role("test-user-a", "super_admin")
    calls = []
    class FakePayPal:
        async def refund_capture(self, capture_id, amount_minor, currency, key):
            calls.append("post")
            return refund_reply(amount_minor, status="PENDING")
        async def get_refund(self, refund_id):
            assert refund_id == "REFUND-A"
            calls.append("get")
            return refund_reply(6800)
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    url = f"/api/v1/admin/orders/{order_id}/refund"
    body = {"request_key":str(uuid4()),"amount_minor":6800}
    first = client.post(url, json=body, headers=bearer(token_factory))
    assert first.status_code == 200
    assert first.json()["status"] == "pending"
    assert client.post(url, json={"request_key":str(uuid4()),"amount_minor":100},
                       headers=bearer(token_factory)).status_code == 409
    second = client.post(url, json=body, headers=bearer(token_factory))
    assert second.status_code == 200
    assert second.json()["status"] == "completed"
    assert calls == ["post", "get"]


def test_unknown_provider_outcome_keeps_retry_key(client, database, token_factory, set_auth_role, monkeypatch):
    order_id = make_order(database)
    set_auth_role("test-user-a", "super_admin")
    keys = []
    class FakePayPal:
        async def refund_capture(self, capture_id, amount_minor, currency, key):
            keys.append(key)
            if len(keys) == 1:
                raise HTTPException(502, "Connection lost")
            return refund_reply(amount_minor)
    monkeypatch.setattr(payments, "PayPalClient", FakePayPal)
    body = {"request_key":str(uuid4()),"amount_minor":6800}
    url = f"/api/v1/admin/orders/{order_id}/refund"
    assert client.post(url, json=body, headers=bearer(token_factory)).status_code == 502
    with database() as db:
        row = db.scalar(select(PaymentRefund))
        assert row.status == "pending" and row.request_key == body["request_key"]
    assert client.post(url, json=body, headers=bearer(token_factory)).status_code == 200
    assert keys == [body["request_key"], body["request_key"]]


def test_refund_rejects_unauthorized_shipped_or_unpaid(client, database, token_factory, set_auth_role, monkeypatch):
    paid_id = make_order(database, fulfillment="shipped")
    headers = bearer(token_factory)
    url = f"/api/v1/admin/orders/{paid_id}/refund"
    body = {"request_key":str(uuid4()),"amount_minor":6800}
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body, headers=headers).status_code == 403
    set_auth_role("test-user-a", "admin")
    assert client.post(url, json=body, headers=headers).status_code == 403
    assert client.get(f"/api/v1/admin/orders/{paid_id}/refunds", headers=headers).status_code == 200
    set_auth_role("test-user-a", "super_admin")
    class NoProvider:
        def __init__(self):
            raise AssertionError("Invalid refund must not contact PayPal")
    monkeypatch.setattr(payments, "PayPalClient", NoProvider)
    assert client.post(url, json=body, headers=headers).status_code == 409
    unpaid_id = make_order(database, status="approval_pending", paypal_order_id="PAYPAL-ORDER-B")
    assert client.post(f"/api/v1/admin/orders/{unpaid_id}/refund", json=body, headers=headers).status_code == 409
    assert client.post(url, json={"request_key":"not-a-uuid","amount_minor":6800}, headers=headers).status_code == 422


def test_checked_refund_rejects_inexact_money_or_wrong_status():
    for response in [
        refund_reply(6801),
        refund_reply(6800, status="UNKNOWN"),
        {**refund_reply(6800), "amount":{"currency_code":"EUR","value":"68.00"}},
        {**refund_reply(6800), "id": ""},
        {**refund_reply(6800), "amount":{"currency_code":"USD","value":"68.001"}},
    ]:
        with pytest.raises(HTTPException):
            payments.checked_refund(response, 6800, "USD")


def test_refund_client_uses_cents_idempotency_and_full_representation():
    paypal = PayPalClient.__new__(PayPalClient)
    calls = []

    async def fake_post(path, payload, request_id=None, *, representation=False):
        calls.append((path, payload, request_id, representation))
        return refund_reply(2500)

    paypal._post = fake_post
    result = asyncio.run(paypal.refund_capture("CAP-A", 2500, "USD", "fixed-key"))
    assert result["status"] == "COMPLETED"
    assert calls == [(
        "/v2/payments/captures/CAP-A/refund",
        {"amount": {"currency_code": "USD", "value": "25.00"}},
        "refund-fixed-key", True,
    )]

    async def fake_get(path):
        calls.append(("get", path))
        return {"id": "PAYPAL-ORDER-A"}

    paypal._get = fake_get
    assert asyncio.run(paypal.get_order("PAYPAL-ORDER-A"))["id"] == "PAYPAL-ORDER-A"
    assert calls[-1] == ("get", "/v2/checkout/orders/PAYPAL-ORDER-A")
