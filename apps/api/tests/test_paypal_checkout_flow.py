"""PayPal Sandbox checkout contract tests: no live money/network requests."""
import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import Order, Product
from app.routers import checkout
from app.integrations.paypal import PayPalClient


SHIP_TO = {
    "full_name": "Demo Recipient",
    "address_line_1": "123 Example Street",
    "address_line_2": "Apt 4",
    "city": "Surakarta",
    "region": "Central Java",
    "postal_code": "57111",
    "country": "Indonesia",
    "phone_country_code": "+62",
    "phone_number": "81234567890",
}

def completed_payload(amount="68.00", *, currency="USD", capture_id="capture-123"):
    return {
        "status": "COMPLETED",
        "purchase_units": [{
            "payments": {"captures": [{
                "id": capture_id,
                "status": "COMPLETED",
                "amount": {"currency_code": currency, "value": amount},
            }]}
        }],
    }


@pytest.mark.parametrize("payload", [
    completed_payload("68.001"),
    completed_payload("68.00", currency="EUR"),
    completed_payload("69.00"),
    completed_payload("68.00", capture_id=""),
    {"status": "APPROVED", "purchase_units": completed_payload()["purchase_units"]},
    {"status": "COMPLETED", "purchase_units": []},
    {"status": "COMPLETED", "purchase_units": [*completed_payload()["purchase_units"]] * 2},
    {"status": "COMPLETED", "purchase_units": [
        {"payments": {"captures": completed_payload()["purchase_units"][0]["payments"]["captures"] * 2}}
    ]},
])
def test_reject_invalid_capture_payloads(payload):
    assert checkout.verified_capture(payload, 6800, "USD") is None


def test_accept_exact_completed_capture():
    assert checkout.verified_capture(completed_payload(), 6800, "USD") == "capture-123"


@pytest.mark.parametrize("response,expected", [
    ({"links": [{"rel":"payer-action", "href":"https://www.sandbox.paypal.com/checkoutnow?token=123"}]},
     "https://www.sandbox.paypal.com/checkoutnow?token=123"),
    ({"links": [{"rel":"approve", "href":"https://www.sandbox.paypal.com/checkoutnow?token=123"}]},
     "https://www.sandbox.paypal.com/checkoutnow?token=123"),
    ({"links": [{"rel":"payer-action", "href":"https://fake.example/checkout"}]}, None),
    ({"links": [{"rel":"payer-action", "href":"http://www.sandbox.paypal.com/checkout"}]}, None),
    ({"links": [{"rel":"payer-action", "href":"https://www.sandbox.paypal.com.evil.example/checkout"}]}, None),
    ({"links": []}, None),
])
def test_approval_link_validation(response, expected):
    assert checkout.approval_link(response) == expected


def test_paypal_order_payload_amount_return_and_cancel_urls():
    client = PayPalClient.__new__(PayPalClient)
    client.settings = SimpleNamespace(frontend_url="http://localhost:3000")
    calls = []

    async def fake_post(path, payload, request_id=None):
        calls.append((path, payload, request_id))
        return {"id": "paypal-example"}

    client._post = fake_post
    asyncio.run(client.create_order("local-123", 6800))
    path, payload, request_id = calls[0]
    assert path == "/v2/checkout/orders"
    assert payload["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "68.00"}
    assert payload["purchase_units"][0]["custom_id"] == "local-123"
    ctx = payload["payment_source"]["paypal"]["experience_context"]
    assert ctx["return_url"] == "http://localhost:3000/checkout/return?order_id=local-123"
    assert ctx["cancel_url"] == "http://localhost:3000/checkout/cancel?order_id=local-123"
    assert request_id == "create-local-123"


def test_sandbox_checkout_create_capture_and_idempotent_return(client, database, monkeypatch, token_factory):
    calls = []

    class FakePayPal:
        async def create_order(self, order_id, price):
            calls.append(("create", order_id, price))
            return {
                "id": "PAYPAL-SANDBOX-ORDER",
                "links": [{"rel":"payer-action", "href":
                           "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-SANDBOX-ORDER"}],
            }

        async def capture_order(self, paypal_id, local_id):
            calls.append(("capture", paypal_id, local_id))
            return completed_payload("68.00")

    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)
    headers = {"Authorization": f"Bearer {token_factory()}"}
    product = client.get("/api/v1/products").json()
    garden = next(item for item in product if item["name"] == "Garden Lover's Box")

    created = client.post("/api/v1/checkout/paypal/orders", json={"product_id":garden["id"], "shipping_address":SHIP_TO}, headers=headers)
    assert created.status_code == 200, created.text
    order = created.json()
    assert order["status"] == "approval_pending"
    assert "sandbox.paypal.com" in order["approval_url"]
    assert calls[0][2] == garden["price_minor"]

    payload = {"order_id":order["order_id"], "paypal_order_id":"PAYPAL-SANDBOX-ORDER"}
    confirmed = client.post("/api/v1/checkout/paypal/capture", json=payload, headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json() == {"status":"paid", "order_id":order["order_id"]}

    repeated = client.post("/api/v1/checkout/paypal/capture", json=payload, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "paid"
    assert len([call for call in calls if call[0] == "capture"]) == 1

    with database() as db:
        saved = db.get(Order, order["order_id"])
        assert saved.status == "paid"
        assert saved.price_snapshot_minor == garden["price_minor"]
        assert saved.paypal_capture_id == "capture-123"
        assert saved.shipping_address == SHIP_TO


def test_capture_does_not_accept_wrong_order_or_amount(client, database, monkeypatch, token_factory):
    capture_calls = []

    class FakePayPal:
        async def create_order(self, order_id, price):
            return {
                "id": "PP-ORDER",
                "links": [{"rel":"approve", "href":"https://www.sandbox.paypal.com/checkoutnow?token=PP-ORDER"}],
            }

        async def capture_order(self, paypal_id, local_id):
            capture_calls.append(local_id)
            return completed_payload("0.01")

    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)
    headers = {"Authorization": f"Bearer {token_factory()}"}
    product = client.get("/api/v1/products").json()[0]
    created = client.post("/api/v1/checkout/paypal/orders", json={"product_id":product["id"], "shipping_address":SHIP_TO}, headers=headers)
    assert created.status_code == 200
    local_id = created.json()["order_id"]

    wrong = client.post("/api/v1/checkout/paypal/capture",
                        json={"order_id":local_id, "paypal_order_id":"FAKE-ID"}, headers=headers)
    assert wrong.status_code == 404
    assert capture_calls == []

    not_paid = client.post("/api/v1/checkout/paypal/capture",
                           json={"order_id":local_id, "paypal_order_id":"PP-ORDER"}, headers=headers)
    assert not_paid.status_code == 409
    with database() as db:
        saved = db.get(Order, local_id)
        assert saved.status == "approval_pending"
        assert saved.paypal_capture_id is None


def test_reject_open_redirect_or_invalid_approval_response(client, monkeypatch, token_factory):
    class FakePayPal:
        async def create_order(self, order_id, price):
            return {
                "id": "PP-ORDER",
                "links": [{"rel":"payer-action", "href":"https://fake.example/checkout"}],
            }

    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)
    headers = {"Authorization": f"Bearer {token_factory()}"}
    product = client.get("/api/v1/products").json()[0]
    created = client.post("/api/v1/checkout/paypal/orders", json={"product_id":product["id"], "shipping_address":SHIP_TO}, headers=headers)
    assert created.status_code == 502


def test_unavailable_or_zero_price_products_cannot_be_checked_out(client, database, monkeypatch, token_factory):
    class FakePayPal:
        def __init__(self):
            raise AssertionError("Should reject invalid catalog product before calling PayPal")

    # The route must filter products before instantiating the provider;
    # in this test we expect the existing provider initialization behavior
    # to be mocked, not called for valid catalog values.
    class NoNetworkPayPal:
        async def create_order(self, *args, **kwargs):
            raise AssertionError("Invalid product should not call provider")

    monkeypatch.setattr(checkout, "PayPalClient", NoNetworkPayPal)
    headers = {"Authorization": f"Bearer {token_factory()}"}
    product = client.get("/api/v1/products").json()[0]
    with database() as db:
        db_prod = db.get(Product, product["id"])
        db_prod.price_minor = 0
        db.commit()
    response = client.post("/api/v1/checkout/paypal/orders", json={"product_id":product["id"], "shipping_address":SHIP_TO}, headers=headers)
    assert response.status_code == 409
