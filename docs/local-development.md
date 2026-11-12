# Local development

Start with the [README quick start](../README.md#run-locally). The commands below are for development and test data, not production.

## Optional sample data

Run migrations for an empty database, then seed sample products **only if you want demo data**:

```bash
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed  # Optional: populate the demo catalog
```

`app.seed` is idempotent and adds 100 fictional products with illustrative images and test prices. Without it, you can manage products through the admin interface. The current Sandbox checkout flow accepts only USD products marked `demo_only`; support for real inventory and PayPal Live is on the roadmap.

To populate admin analytics with fictional orders on a **disposable local database**:

```bash
uv run python -m app.seed_scenarios --confirm-demo-data
```

To associate those orders and six sample recipients with an existing test account:

```bash
uv run python -m app.seed_scenarios --confirm-demo-data --user-id "BETTER_AUTH_USER_ID"
```

Choose **one** scenario variant per database; running both duplicates test orders. The seeded paid orders are **not real PayPal captures**.

### Reset and seed (destructive)

For a fresh local database, set `DEV_ADMIN_EMAIL`, `DEV_ADMIN_PASSWORD`, `DEV_CUSTOMER_NAME`, `DEV_CUSTOMER_EMAIL`, and `DEV_CUSTOMER_PASSWORD` in `apps/web/.env`, then run:

```bash
cd apps/api
uv run python -m app.db reset
uv run python -m app.db seed
```

`reset` **deletes all data in the local Kadoku schema**. The CLI restricts reset/seed to local development or test PostgreSQL with PayPal Sandbox. `seed` creates two test users, 100 products, 38 fictional orders, and sample recipients. Re-running seed does not overwrite user passwords.

To repair missing Better Auth tables without deleting data:

```bash
uv run python -m app.db migrate
```

See [Render staging runbook](render-staging.md) for the separately guarded staging workflow. Do not reset staging or production from local setup commands.

## Admin access

Register a user through the storefront, then obtain its Better Auth user ID (not email):

```sql
SELECT id, email FROM "user";
```

Set `ADMIN_USER_IDS=<user-id>` in `apps/api/.env`, restart FastAPI, and open `http://localhost:3000/admin`. An empty allowlist denies all admin access. Do not use a real customer account for demo fixtures.

## Optional integrations

- **Gemini:** Set `AI_MODEL=gemini/gemini-2.5-flash` and `GEMINI_API_KEY` in `apps/api/.env`. Without an AI key, catalog-grounded rules still generate gift recommendations.
- **PayPal Sandbox:** Set `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `apps/api/.env`. Use a Sandbox buyer account. Checkout is disabled without credentials.
- **Google sign-in:** Configure `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `NEXT_PUBLIC_GOOGLE_OAUTH_ENABLED=true` in `apps/web/.env`. Local redirect URI: `http://localhost:3000/api/auth/callback/google`.
- **AG Studio AI Analyst:** See [Admin analytics](analytics.md).

Keep API keys server-side and out of git.

## Verify

```bash
cd apps/api
uv run --extra test pytest -q
```

In `apps/web`, run `pnpm build` and `pnpm typecheck`. Then manually test gift discovery, refinement, sign-in, Sandbox approval/capture/cancel, My Orders, and admin analytics.

API health: `http://localhost:8000/api/health`; web proxy: `http://localhost:3000/backend/api/health`.

If gift chat fails:
1. Confirm both servers are running and `API_PROXY_TARGET=http://localhost:8000` is set in `apps/web/.env`.
2. Ensure `GUEST_COOKIE_SECRET` matches `GUEST_QUOTA_SECRET`. The default quota is **3 guest** or **5 member** requests per UTC day; HTTP 429 may mean the limit was reached.
3. Confirm `AI_MODEL` and its provider key only if you need model-powered replies. `rules` and `rules-fallback` are expected without a working model.

Better Auth migrations and Alembic migrations manage different tables in the same PostgreSQL database.

## Payment environments

PayPal Sandbox is the currently implemented payment environment; changing `PAYPAL_MODE` to `live` does **not** activate live checkout. The payment client and checkout validation deliberately reject live mode. Sample orders are fictional, and Sandbox captures are test transactions, not revenue.

PayPal Live and real-order fulfillment are planned after supplier integration, tax/shipping quotes, stock reservations, refunds, reconciliation, fraud controls, and production security review.
