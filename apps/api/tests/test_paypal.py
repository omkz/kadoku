from app.routers.checkout import verified_capture


def test_capture_matches_amount_currency_and_state():
    payload = {"status":"COMPLETED", "purchase_units":[{"payments":{"captures":[{
        "id":"capture-123", "status":"COMPLETED", "amount":{"currency_code":"USD","value":"48.00"}
    }]}}]}
    assert verified_capture(payload, 4800, "USD") == "capture-123"
    assert verified_capture(payload, 4900, "USD") is None
    assert verified_capture(payload, 4800, "EUR") is None
    payload["status"] = "APPROVED"
    assert verified_capture(payload, 4800, "USD") is None
