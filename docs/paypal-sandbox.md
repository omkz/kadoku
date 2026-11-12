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

Refunds, reconciliation, shipping and tax calculations, and PayPal Live are future work. Do not enable Live by only changing `.env`.
