# Test PayPal Checkout — Kadoku Sandbox

Kadoku currently processes **PayPal Sandbox only**. The 12 catalog items are demos. No real money is charged and there is **no product delivery**.

## 1. Get test credentials

1. Open the [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/).
2. Create/select a **Sandbox REST app** linked to a **Sandbox Business** merchant account.
3. Copy its **Client ID** and **Client Secret** (never commit them).
4. Under Sandbox test accounts, identify a separate **Personal** buyer and its test login credentials.

The merchant and test buyer must not be the same account.

## 2. Configure and run locally

In `apps/api/.env` (not `.env.example`), set:

```dotenv
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
FRONTEND_URL=http://localhost:3000
```

Use your existing database/auth settings and secrets. Start the API:

```bash
cd apps/api
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

In another terminal start the web app:

```bash
cd apps/web
pnpm install
pnpm dev
```

`FRONTEND_URL` is used in the PayPal return/cancel URLs, so it must match where your browser can open Kadoku. Localhost works for a buyer browser on the **same machine**. For remote tests use a real externally reachable HTTPS URL.

## 3. Test the end-to-end buyer flow

1. Open http://localhost:3000, ask for a gift, and select one of the demo items.
2. Open its detail and checkout screen. The price is read from PostgreSQL, not from an editable browser total.
3. Click **Continue to PayPal Sandbox**.
4. The backend creates a local pending order and sends `POST /v2/checkout/orders` to the PayPal Sandbox API. The buyer is redirected to the PayPal Sandbox approval URL.
5. Log in with a **Sandbox Personal buyer account**, approve the test payment, and return to Kadoku.
6. Kadoku posts the local order ID and returned PayPal order token to `POST /api/v1/checkout/paypal/capture`.
7. The backend checks PayPal's completed capture, exact USD amount and currency, then records local status `paid`. The return page displays **Sandbox payment complete**.

To test cancellation, repeat the flow and cancel on PayPal. You should see **Checkout cancelled** at `/checkout/cancel`. A canceled flow is **not** treated as a paid order.

To test an API error (for example an invalid Sandbox client secret), the app must show a failure message, not claim the order was paid.

## 4. Debugging

| Symptom | Likely cause | Check |
|---|---|---|
| `503 PayPal Sandbox is not configured` | Missing Client ID or secret, or live mode | `apps/api/.env` and server restart |
| `502 PayPal Sandbox request failed` | Invalid Sandbox credentials, network error, or provider rejection | API logs and Sandbox account/app settings |
| `502 PayPal did not return a buyer approval link` | Missing or untrusted approval URL | PayPal REST app / API response; do not forge links |
| `404 Order not found` on return | PayPal `token` does not match stored local order | Check callback URL and DB |
| `409 Payment was not captured for the expected amount` | Capture wasn't completed or mismatched amount/currency | Test-buyer approval and PayPal Sandbox transactions |

A retry on the return page reuses the local order ID and PayPal order ID. The backend uses a stable **PayPal-Request-Id** for capture and treats a previously saved `paid` order as already completed.

## 5. Optional webhook testing

PayPal webhooks are not required for the browser redirect smoke test. If configured, set `PAYPAL_WEBHOOK_ID` and register a public HTTPS webhook endpoint pointing to `/api/v1/webhooks/paypal`. The backend verifies signatures and deduplicates event IDs, but **webhooks do not mark orders as paid** in this demo. Payment status is based on verified capture response.

## Not production ready

This flow has no real supplier stock, shipping, tax calculation, refund operations or fulfillment. Do not enable live PayPal; `PAYPAL_MODE=live` is intentionally disabled.
