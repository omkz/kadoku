"""Address snapshots for demo checkout, including validation and owner isolation."""
from copy import deepcopy

import pytest
from app.models import Order, Product
from app.routers import checkout


SHIPPING = {
    "full_name": "Demo Recipient",
    "address_line_1": "123 Example Street",
    "address_line_2": "Unit 4",
    "city": "Surakarta",
    "region": "Central Java",
    "postal_code": "57111",
    "country": "Indonesia",
    "phone_country_code": "+62",
    "phone_number": "81234567890",
}


@pytest.mark.parametrize("shipping", [
    None,
    {},
    {**SHIPPING, "full_name": "   "},
    {**SHIPPING, "full_name": "A"},
    {**SHIPPING, "address_line_1": "x"},
    {**SHIPPING, "city": ""},
    {**SHIPPING, "country": ""},
    {**SHIPPING, "country": "x" * 81},
    {**SHIPPING, "phone_country_code": "62"},
    {**SHIPPING, "phone_country_code": "+000"},
    {**SHIPPING, "phone_country_code": None, "phone_number": "81234567890"},
    {**SHIPPING, "phone_number": "hello"},
    {**SHIPPING, "phone_number": "123"},
    {**SHIPPING, "phone_country_code": "+9999", "phone_number": "123456789012345"},
    {**SHIPPING, "unexpected": "field"},
])
def test_invalid_shipping_rejected_before_paypal(client, monkeypatch, token_factory, shipping):
    class ShouldNotReachPayPal:
        def __init__(self):
            raise AssertionError("Invalid address must be rejected before provider is used")
    monkeypatch.setattr(checkout, "PayPalClient", ShouldNotReachPayPal)
    product = client.get("/api/v1/products").json()[0]
    response = client.post("/api/v1/checkout/paypal/orders", json={
        "product_id": product["id"], "shipping_address": shipping,
    }, headers={"Authorization": f"Bearer {token_factory()}"})
    assert response.status_code == 422, response.text


def test_shipping_stored_per_order_and_read_only_by_owner(client, database, monkeypatch, token_factory):
    class FakePayPal:
        async def create_order(self, order_id, amount):
            return {
                "id": "PP-" + order_id,
                "links": [{"rel": "approve",
                           "href": "https://www.sandbox.paypal.com/checkoutnow?token=PP-" + order_id}],
            }
    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)
    product = client.get("/api/v1/products").json()[0]
    own = {"Authorization": f"Bearer {token_factory(sub='owner')}"}
    other = {"Authorization": f"Bearer {token_factory(sub='other')}"}
    address = deepcopy(SHIPPING)
    created = client.post("/api/v1/checkout/paypal/orders", json={
        "product_id": product["id"], "shipping_address": address,
    }, headers=own)
    assert created.status_code == 200, created.text
    order_id = created.json()["order_id"]
    address["full_name"] = "Tampered after creation"

    detail = client.get(f"/api/v1/orders/{order_id}", headers=own)
    assert detail.status_code == 200, detail.text
    assert detail.json()["shipping_address"] == SHIPPING
    assert "shipping_address" not in client.get("/api/v1/orders", headers=own).json()[0]
    assert client.get(f"/api/v1/orders/{order_id}", headers=other).status_code == 404
    with database() as db:
        assert db.get(Order, order_id).shipping_address == SHIPPING


def test_phone_and_postal_optional_for_international_demo_checkout(client, monkeypatch, token_factory):
    class FakePayPal:
        async def create_order(self, order_id, amount):
            return {"id": "PP-" + order_id, "links": [{"rel": "approve",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=PP-" + order_id}]}
    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)
    product = client.get("/api/v1/products").json()[0]
    address = {
        "full_name": "Example Friend",
        "address_line_1": "12 Example Road",
        "city": "Dubai",
        "country": "United Arab Emirates",
    }
    headers = {"Authorization": f"Bearer {token_factory()}"}
    response = client.post("/api/v1/checkout/paypal/orders", json={
        "product_id": product["id"], "shipping_address": address,
    }, headers=headers)
    assert response.status_code == 200, response.text
    detail = client.get("/api/v1/orders/" + response.json()["order_id"], headers=headers).json()
    assert detail["shipping_address"]["phone_number"] is None
    assert detail["shipping_address"]["phone_country_code"] is None
    assert detail["shipping_address"]["postal_code"] is None


def test_existing_order_without_shipping_remains_readable(client, database, token_factory):
    product = client.get("/api/v1/products").json()[0]
    with database() as db:
        order = Order(user_id="legacy-user", product_id=product["id"],
                      price_snapshot_minor=product["price_minor"], currency="USD",
                      status="paid")
        db.add(order)
        db.commit()
        order_id = order.id
    headers = {"Authorization": f"Bearer {token_factory(sub='legacy-user')}"}
    result = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert result.status_code == 200
    assert result.json()["shipping_address"] is None
