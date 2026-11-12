# PayPal Sandbox

Kadoku currently implements PayPal Orders v2 **Sandbox** checkout. Live payments are not enabled.

## Configure

Create a Sandbox REST app and a separate Personal buyer account in the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/).

Set in `apps/api/.env`:

```dotenv
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your-sandbox-client-id
PAYPAL_CLIENT_SECRET=your-sandbox-client-secret
FRONTEND_URL=http://localhost:3000
```

Restart FastAPI. Use the [README](../README.md#local-setup) to start the app and [sample data](sample-data.md) for optional products.

## Test checkout

1. Sign in to Kadoku and select a sample product.
2. Continue to PayPal and approve using a **Sandbox buyer**, not the merchant account.
3. Return to Kadoku; the backend captures and verifies the completed payment, currency, and exact amount.
4. Confirm the order is **Paid** in **My Orders**. Test cancellation separately; cancellation before capture is not a refund.

Checkout currently requires USD products flagged `demo_only`; prices are read from the database, not the browser. `PayPal-Request-Id` supports idempotent create/capture retries.

## Webhooks and failures

Optionally register `/api/v1/webhooks/paypal` on a public HTTPS endpoint and set `PAYPAL_WEBHOOK_ID`. Signatures are verified and event IDs deduplicated, but webhooks **do not** yet update payment state.

- **503:** Check Sandbox credentials and `PAYPAL_MODE`.
- **502:** Check provider response, connectivity, and callback/approval URLs.
- **409:** Capture was not completed or amount/currency did not match.

## Refunds and recovery

If the capture callback loses its response, Kadoku checks PayPal's order status before reporting failure. A signed-in buyer can retry via `POST /api/v1/orders/{id}/reconcile`. Admins can check `POST /api/v1/admin/orders/{id}/reconcile`; neither endpoint initiates a new charge.

A `super_admin` can issue a full or partial Sandbox refund through the API docs:

```http
POST /api/v1/admin/orders/{id}/refund
Content-Type: application/json

{"request_key":"e5b20ecf-07e8-4f9e-841a-5bd6c4043487","amount_minor":2500}
```

Use a **new UUID per refund**, but reuse the same UUID when retrying an uncertain result. Amounts are integer cents. Only verified, unfulfilled USD captures qualify; seeded fictional paid orders are not refundable. View status with `GET /api/v1/admin/orders/{id}/refunds`. Pending refunds must be resolved before another refund.

Run Alembic migration `0005_payment_refunds` before using these endpoints. Webhooks are still verified and logged, **not automatically reconciled**. PayPal Live, shipping, and tax remain future work; changing `.env` alone does not enable Live.
