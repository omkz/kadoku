"""Authenticated checkout and order history: ownership is enforced by signed JWT."""
from app.models import Order, Product
from app.routers import checkout


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
                       json={"product_id": product["id"]}).status_code == 401
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
                                         json={"product_id": product["id"]}, headers=headers)
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
    assert client.get("/api/v1/orders/" + other_id, headers=a).status_code == 404
