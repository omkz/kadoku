"""Authenticated checkout and order history: ownership is enforced by signed JWT."""
from app.models import Order, Product
from app.routers import checkout


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

def auth(token_factory, user="test-user-a"):
    return {"Authorization": f"Bearer {token_factory(sub=user)}"}


def fake_paypal(monkeypatch):
    class FakePayPal:
        async def create_order(self, order_id, amount_minor):
            return {
                "id": "PP-" + order_id,
                "links": [{
                    "rel": "payer-action",
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=PP-" + order_id,
                }],
            }

        async def capture_order(self, paypal_id, local_id):
            return {
                "status": "COMPLETED",
                "purchase_units": [{
                    "payments": {"captures": [{
                        "id": "CAPTURE-" + local_id,
                        "status": "COMPLETED",
                        "amount": {"currency_code": "USD", "value": "68.00"},
                    }]}
                }],
            }

    monkeypatch.setattr(checkout, "PayPalClient", FakePayPal)


def test_checkout_and_order_history_require_login(client, database):
    product = client.get("/api/v1/products").json()[0]
    assert client.post("/api/v1/checkout/paypal/orders",
                       json={"product_id": product["id"], "shipping_address":SHIP_TO}).status_code == 401
    assert client.post("/api/v1/checkout/paypal/capture",
                       json={"order_id": "any", "paypal_order_id": "any"}).status_code == 401
    assert client.get("/api/v1/orders").status_code == 401
    assert client.get("/api/v1/orders/any").status_code == 401
    with database() as db:
        assert db.query(Order).count() == 0


def test_order_history_owner_isolation_and_price_snapshot(client, database, monkeypatch, token_factory):
    fake_paypal(monkeypatch)
    product = next(
        item for item in client.get("/api/v1/products").json()
        if item["name"] == "Garden Lover's Box"
    )
    a = auth(token_factory, "user-a")
    b = auth(token_factory, "user-b")

    create = lambda headers: client.post("/api/v1/checkout/paypal/orders",
                                         json={"product_id": product["id"], "shipping_address":SHIP_TO}, headers=headers)
    first = create(a)
    second = create(a)
    other = create(b)
    for result in (first, second, other):
        assert result.status_code == 200, result.text

    first_id = first.json()["order_id"]
    second_id = second.json()["order_id"]
    other_id = other.json()["order_id"]

    # Old guest purchases are intentionally not adopted by the newly signed-in user.
    with database() as db:
        db.add(Order(user_id=None, product_id=product["id"],
                     price_snapshot_minor=6800, currency="USD", status="paid"))
        db.get(Product, product["id"]).price_minor = 9900
        db.commit()

    own_list = client.get("/api/v1/orders", headers=a)
    assert own_list.status_code == 200, own_list.text
    own = own_list.json()
    assert {order["id"] for order in own} == {first_id, second_id}
    assert all(order["price_minor"] == 6800 for order in own)
    assert all(order["product_name"] == "Garden Lover's Box" for order in own)
    assert all(order["status"] == "approval_pending" for order in own)
    assert all(order["created_at"] for order in own)

    b_list = client.get("/api/v1/orders", headers=b)
    assert b_list.status_code == 200
    assert [order["id"] for order in b_list.json()] == [other_id]
    assert client.get("/api/v1/orders/" + first_id, headers=b).status_code == 404
    assert client.get("/api/v1/orders/" + other_id, headers=a).status_code == 404
    assert client.get("/api/v1/orders/" + first_id, headers=a).status_code == 200

    payload = {"order_id": first_id, "paypal_order_id": "PP-" + first_id}
    assert client.post("/api/v1/checkout/paypal/capture", json=payload, headers=b).status_code == 404
    with database() as db:
        assert db.get(Order, first_id).status == "approval_pending"
    captured = client.post("/api/v1/checkout/paypal/capture", json=payload, headers=a)
    assert captured.status_code == 200, captured.text
    assert captured.json() == {"status": "paid", "order_id": first_id}
    repeated = client.post("/api/v1/checkout/paypal/capture", json=payload, headers=a)
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "paid"

    detail = client.get("/api/v1/orders/" + first_id, headers=a)
    assert detail.status_code == 200
    assert detail.json()["status"] == "paid"
    assert detail.json()["paypal_capture_id"] == "CAPTURE-" + first_id
    assert detail.json()["paypal_order_id"] == "PP-" + first_id
    assert detail.json()["price_minor"] == 6800
    assert detail.json()["shipping_address"] == SHIP_TO
    assert client.get("/api/v1/orders/" + other_id, headers=a).status_code == 404


def test_cancelled_checkout_is_owner_scoped_idempotent_and_never_overwrites_paid(
    client, database, monkeypatch, token_factory
):
    fake_paypal(monkeypatch)
    product = next(
        item for item in client.get("/api/v1/products").json()
        if item["name"] == "Garden Lover's Box"
    )
    user_a = auth(token_factory, "user-a")
    user_b = auth(token_factory, "user-b")
    create = lambda: client.post("/api/v1/checkout/paypal/orders",
                                 json={"product_id": product["id"], "shipping_address":SHIP_TO}, headers=user_a)
    abandoned = create()
    completed = create()
    assert abandoned.status_code == completed.status_code == 200
    abandoned_id = abandoned.json()["order_id"]
    paid_id = completed.json()["order_id"]

    cancel_url = f"/api/v1/orders/{abandoned_id}/cancel"
    assert client.post(cancel_url).status_code == 401
    assert client.post(cancel_url, headers=user_b).status_code == 404

    cancelled = client.post(cancel_url, headers=user_a)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json() == {"order_id": abandoned_id, "status": "cancelled"}
    repeated = client.post(cancel_url, headers=user_a)
    assert repeated.status_code == 200
    assert repeated.json()["status"] == "cancelled"
    assert client.get(f"/api/v1/orders/{abandoned_id}", headers=user_a).json()["status"] == "cancelled"
    assert client.post("/api/v1/checkout/paypal/capture", json={
        "order_id": abandoned_id,
        "paypal_order_id": "PP-" + abandoned_id,
    }, headers=user_a).status_code == 409

    captured = client.post("/api/v1/checkout/paypal/capture", json={
        "order_id": paid_id, "paypal_order_id": "PP-" + paid_id
    }, headers=user_a)
    assert captured.status_code == 200
    assert client.post(f"/api/v1/orders/{paid_id}/cancel", headers=user_a).status_code == 409
    assert client.get(f"/api/v1/orders/{paid_id}", headers=user_a).json()["status"] == "paid"
