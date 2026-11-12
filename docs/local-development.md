# Local development

See the [README](../README.md#local-setup) to start the API and web app.

## Sample data (optional)

From `apps/api`, after migrations:

```bash
uv run python -m app.seed
```

Adds up to 100 fictional products. Safe to rerun; existing products are preserved.

For sample orders and analytics on a **disposable local database**, choose **one**:

```bash
uv run python -m app.seed_scenarios --confirm-demo-data
# Or link demo orders and recipients to an existing test user:
uv run python -m app.seed_scenarios --confirm-demo-data --user-id "BETTER_AUTH_USER_ID"
```

Running both variants duplicates demo orders. Seeded `paid` orders are **not** PayPal captures.

For a full local reset, first set `DEV_ADMIN_EMAIL`, `DEV_ADMIN_PASSWORD`, `DEV_CUSTOMER_NAME`, `DEV_CUSTOMER_EMAIL`, and `DEV_CUSTOMER_PASSWORD` in `apps/web/.env`:

```bash
uv run python -m app.db reset
uv run python -m app.db seed
```

**Destructive:** `reset` deletes the local Kadoku database schema. `seed` creates two test accounts, 100 products, 38 fictional orders, and sample recipients. Never run this against production. To repair auth tables without resetting: `uv run python -m app.db migrate`.

For staging, use the separate [Render runbook](render-staging.md).

## Admin access

Register a user, then get the Better Auth user ID:

```sql
SELECT id, email FROM "user";
```

Set `ADMIN_USER_IDS=<user-id>` in `apps/api/.env` and restart FastAPI. Open `http://localhost:3000/admin`. An empty allowlist denies access.

## Optional services

- **Gemini:** `AI_MODEL=gemini/gemini-2.5-flash` and `GEMINI_API_KEY` in `apps/api/.env`. With no key, gift discovery uses rules.
- **PayPal Sandbox:** `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `apps/api/.env`; use Sandbox buyer credentials.
- **Google login:** Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `NEXT_PUBLIC_GOOGLE_OAUTH_ENABLED=true` in `apps/web/.env`. Local redirect: `http://localhost:3000/api/auth/callback/google`.
- **AI Analyst:** See [analytics setup](analytics.md).

Do not commit secrets.

## Checks

```bash
cd apps/api && uv run --extra test pytest -q
cd ../web && pnpm build && pnpm typecheck
```

API health: `http://localhost:8000/api/health`. For chat errors, verify `API_PROXY_TARGET=http://localhost:8000` and that `GUEST_COOKIE_SECRET` matches `GUEST_QUOTA_SECRET`. Default limits: **3 guest / 5 member** requests per UTC day.

## Payments

Kadoku currently supports **PayPal Sandbox only**. Setting `PAYPAL_MODE=live` will not enable real payments. The checkout also requires USD products with `demo_only=true`. Refunds, reconciliation, real inventory, and PayPal Live remain on the roadmap.
