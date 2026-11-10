# Kadoku

**Thoughtful gifts, made easy.** A mobile-first AI gifting companion that recommends a small set of curated products from a **shop-owned** catalog.

**Status:** Functional foundation / non-production MVP. This repository is intended for iterative product development. It is **not** a live store and cannot fulfill real orders.

## Technology

- **Web:** Next.js 16, React 19, TypeScript, CSS, Better Auth (email/password; optional Google OAuth).
- **API:** Python, FastAPI, SQLAlchemy 2, Alembic; traditional layered architecture.
- **Database:** PostgreSQL (native/local is supported); SQLite is supported for backend-only local tests.
- **AI:** Deterministic recommendation engine with optional LiteLLM intent extraction; model can be changed using `AI_MODEL`. LangChain/advanced agent orchestration is a **future integration**, not required for the working baseline.
- **Checkout:** PayPal Orders v2 Sandbox using redirect approval and server-side capture. The integration is intentionally **blocked in live mode**.
- **Voice:** Browser SpeechRecognition where supported, with typing fallback; may rely on the browser vendor's speech service.

## What works now

- Conversation-first homepage with voice-capable input; **no catalog-first homepage**.
- End-to-end recommendation request to FastAPI, grounded in 100 **demo-only** products, showing up to three swipeable cards with one highlighted pick.
- Budget, interests, occasion filtering and ranking; different product categories when possible.
- Guest recommendation quota enforced on the backend; signed HttpOnly guest identity cookie issued by Next.js. Members have a larger daily quota.
- Better Auth wiring, JWT/JWKS validation in FastAPI, private recipient and birthday endpoints, My People form.
- Product selection, gift note display, PayPal Sandbox order create/approve/capture if configured.
- Versioned Alembic migration and automated API tests.

## Conversational refinements (MVP)

On the gifts screen, Kadoku now lets shoppers ask for changes such as **"Make it cheaper"**, **"Something more personal"**, **"No plants"**, or **"Budget $50 instead"**. Each response includes a bounded `context` object containing the previously understood interests, exclusions, budget, occasion and the latest top-pick price. The Next.js client submits this context with the next message; the API validates it and applies deterministic hard filters before recommending up to three catalog products.

- "Cheaper" means strictly below the last recommended top-pick price, if available; Kadoku does **not** silently convert IDR into USD.
- "More personal" prioritizes demo products marked as personal (subject to budget and stock).
- Explicit dollar budgets in a new turn override the earlier budget; existing exclusions are retained.
- Chat context is **kept only in the current browser tab's React state**, not persisted to PostgreSQL. Home starts a fresh conversation. Saved recipient profiles remain separate.
- **Every recommendation/refinement call consumes the existing daily quota**. Guests are currently limited to one call/day and need to sign in to refine further. This flow is not unlimited chat.
- No LLM-generated product or price is accepted; recommendations always come from the catalog.

## Demo catalog (100 products) and product images

Five AI-generated **concept illustrations** are committed as compressed WebP assets (600×600 px) under `apps/web/public/products/`. They are matched to the existing demo catalog entries: Garden Lover's Box, Artisan Coffee Ritual, Handmade Tea Box, Book Lover Bundle, and Cozy Evening Box.

Product `image_url` is optional. Recommendation and gift-detail cards render the catalog image with Next.js `Image`; when the image URL is absent or fails, Kadoku displays its branded `/products/default.webp` illustration (a compressed 256×256 WebP), then falls back to the product emoji only if even the local default image fails to load. The default is explicitly labeled *Illustrative image* in the artwork and is **not** a real product photo. No database migration or seed changes are needed for this presentation fallback.



The 100-item demo set covers personalized gifts, home, tech, creative hobbies,
coffee/tea/food, books, wellness, travel, accessories and music. Its prices and
stock are **fictional USD test data** and every new item has `demo_only = true`.
The products use the existing 10-interest extraction vocabulary so no AI or
ranking changes are necessary. Adding more items does not by itself prove
recommendation relevance; the tests verify hard constraints and seed behavior,
not subjective gift quality.

For an **existing database**, run any outstanding Alembic migrations and rerun the seed command after checking out this branch:

```bash
cd apps/api
uv run alembic upgrade head
uv run python -m app.seed
```

The idempotent seed adds **88 curated new demo products** to an existing 12-item catalog, or all 100 items to a blank database. Existing product IDs, prices, stock, images, and linked orders remain untouched; no destructive reseeding. New products have `image_url = NULL` and render `/products/default.webp`. Five original products retain their studio concept photos. New demo items have stable UUID5 IDs to prevent re-creation after a store-side rename. The seed reports how many rows were added and returns 0 on a repeated run.

**Note:** These AI-generated photos are illustrative visuals, not verified supplier product photos. Real-product descriptions, pictures, inventory, sourcing, taxes, delivery, and returns must be validated before accepting live payments.

## MVP release smoke check (Sandbox only)

This release check is for a **demo**, not a production store or real checkout.

1. Run `uv run pytest -q` from `apps/api`, then `npm run typecheck:web` and `npm run build:web` from the repository root. CI runs these checks on PRs (with throwaway build-time values; CI does **not** connect to a real DB).
2. Apply pending API migrations with `uv run alembic upgrade head`, run `uv run python -m app.seed`, and verify `GET /api/v1/products` returns the demo catalog.
3. Check home → recommendation (including zero-match state) → details → sign-in → PayPal **Sandbox** → return/cancel → My Orders; also verify the saved-person loading/retry state, mobile swipe and desktop arrows in a real browser.
4. Use real deployment secrets, HTTPS, the correct `BETTER_AUTH_URL`, `FRONTEND_URL`, `CORS_ORIGINS` and database endpoints. `GUEST_COOKIE_SECRET` and `GUEST_QUOTA_SECRET` must match; do not copy the CI placeholder values to deployments. Keep `PAYPAL_MODE=sandbox`; live PayPal is not implemented.
5. Before making the demo public, review privacy/terms, login security, abuse and AI-cost limits, and what is disclosed about fictional catalog items and non-fulfillment. Passing CI alone **does not** make Kadoku ready for real commerce.

## Local setup (Linux / macOS)

### 1. PostgreSQL (native; no Docker needed)

Create a role and database using your existing PostgreSQL installation:

```bash
sudo -u postgres psql -c "CREATE ROLE kadoku LOGIN PASSWORD 'local-only-password';"
sudo -u postgres psql -c "CREATE DATABASE kadoku OWNER kadoku;"
```

Use your own password, and update both app environment files accordingly. On macOS or a configured Postgres installation, use the equivalent `psql` commands.

### 2. FastAPI

```bash
cd apps/api
cp .env.example .env
# Set DATABASE_URL to postgresql+psycopg://kadoku:<password>@localhost:5432/kadoku
# Set a random GUEST_QUOTA_SECRET and use the same secret in the Next.js env file.
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

API health: <http://localhost:8000/api/health>  ·  OpenAPI: <http://localhost:8000/docs>

Install AI support when you have a provider API key:

```bash
uv sync --extra ai
# Set AI_MODEL=provider/model and the matching provider API key in apps/api/.env
```

Without an AI key, the application still works in **rules-based demo mode**. The LLM is used only for gift-intent extraction; the server independently ranks products, enforces stock and price limits, and returns catalog data. Set `AI_MODEL` (LiteLLM provider/model), install optional AI dependencies with `uv sync --extra ai`, and provide the provider API key. `AI_TIMEOUT_SECONDS` and `AI_MAX_OUTPUT_TOKENS` cap each AI call. Invalid or unavailable model responses fall back to the rule parser; the API response identifies the path with `provider` (`llm`, `rules`, or `rules-fallback`). A model failure does not grant extra guest recommendations.

### 3. Next.js and Better Auth

From the **repository root**, use **pnpm inside the web app**:

```bash
cd apps/web
cp .env.example .env
pnpm install
# Set AUTH_DATABASE_URL, BETTER_AUTH_URL and a random BETTER_AUTH_SECRET in .env.
# Set GUEST_COOKIE_SECRET to the API's GUEST_QUOTA_SECRET.
pnpm dlx auth@latest migrate --yes
pnpm dev
```

Open <http://localhost:3000>. Email/password sign-in works without Google OAuth.

#### Google sign-in (optional)

Create an OAuth Client ID of type **Web application** in Google Cloud Console. Add this **Authorized redirect URI** for local development:

```text
http://localhost:3000/api/auth/callback/google
```

Set these values in `apps/web/.env` (never commit credentials):

```dotenv
GOOGLE_CLIENT_ID=your-google-web-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
NEXT_PUBLIC_GOOGLE_OAUTH_ENABLED=true
```

Restart `pnpm dev` after changing environment variables. In production, register the corresponding HTTPS redirect URI, e.g. `https://your-domain.com/api/auth/callback/google`, and set `BETTER_AUTH_URL=https://your-domain.com`. Leave the public Google button disabled if the server credentials are not configured.

**JWT integration:** Better Auth issues short-lived JWTs using the JWT plugin's JWKS. FastAPI verifies the EdDSA signature, expiration, issuer and audience, and exposes `GET /api/v1/auth/me` as an authentication smoke test. Better Auth manages the web session; don't pass session cookies directly to FastAPI.

**Before production:** configure email verification/delivery for password accounts, anti-abuse controls, and test OAuth, session expiration and logout with real credentials. The backend tests cover JWT validation, not Google's external OAuth service.

> The Better Auth migration creates its authentication tables in PostgreSQL. Alembic owns the Kadoku application tables. Both can coexist in the same database.

### 4. PayPal Sandbox (optional)

Create a **Sandbox** REST application in PayPal Developer and populate `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `apps/api/.env`. Optionally configure webhook ID for signature verification. Use PayPal **test buyer** accounts only. Without credentials, the checkout endpoint returns HTTP 503 (the UI shows the error). **No real fulfillment or shipping occurs.**

This implementation uses the Orders API `payer-action` redirect and PayPal's approval return page, not the JavaScript SDK buttons yet. Do not call it production-ready. A shipping/tax quote, fulfillment, stock reservations, refunds, fraud review, and stronger abuse prevention are required before real commerce.

## Authenticated checkout and My Orders

**A signed-in user is required to pay with PayPal Sandbox.** Gift discovery remains available to guests. If a guest selects a product and presses **Continue to checkout**, Kadoku opens sign-in; the current gift and note remain in place. For a full-page Google OAuth redirect, a short-lived tab-local pending selection is recovered (no payment credentials or server-authoritative prices are stored).

- Only the authenticated owner can create, capture, cancel, list, or view their orders.
- **My Orders** in bottom navigation lists the user's latest 100 orders. Select an item for its detail, historical price, payment status, and Sandbox PayPal IDs.
- Backend endpoints: `GET /api/v1/orders`, `GET /api/v1/orders/{order_id}`, and `POST /api/v1/orders/{order_id}/cancel`; all require a valid Bearer JWT. A payment return cannot capture a different user's order even with its PayPal token.
- The cancellation endpoint only marks an **uncaptured, approval-pending** order as locally cancelled; it never refunds or cancels already captured PayPal payments.
- **Legacy guest orders** (`user_id IS NULL`) remain unassigned and are **not automatically visible** to newly signed-in users. No migration or ownership guessing is performed.
- Product name and emoji currently come from the catalog; the order amount and currency are preserved from checkout-time snapshots. This remains a **Sandbox-only demo**, not commercial fulfillment.

## Admin dashboard (MVP)

The separate **`/admin`** area is a wide, desktop-friendly workspace (the shopper homepage remains mobile-first at 470px). It includes:

- **Overview:** total and active products, out-of-stock items, Sandbox orders, and captured test payment amounts. Sandbox captures are **not business revenue**.
- **Products:** server-paginated search/filter, add, edit, activate/deactivate, USD price and stock editing. A deactivated product disappears from recommendations while linked orders remain intact. All newly created products are **demo-only**. Existing catalog images are preserved; image upload is not implemented.
- **Orders:** server-paginated, read-only order list and payment statuses, with shortened buyer references. Shipping addresses, payment identifiers and other private details are not exposed in the list.

No AG Grid or TanStack Table dependency is required for this bounded MVP. React tables with API-side pagination and filtering are used; revisit a grid library only if bulk-editing or more complex workflows become necessary.

### Give an account admin access

1. Start the backend and web app as above. Register or sign in through the normal Kadoku storefront first.
2. Retrieve **that existing account's Better Auth user ID**, for example from the PostgreSQL auth database:
   ```sql
   SELECT id, email FROM "user";
   ```
   Do not use the email address itself as an admin authorization rule.
3. Set **`ADMIN_USER_IDS=<the-id>`** in `apps/api/.env` (comma-separated for multiple administrators). Restart the FastAPI service to reload the environment.
4. Open **`http://localhost:3000/admin`** (or `https://your-domain/admin` after deployment) while signed into that account.

**Security:** The FastAPI admin endpoints validate each Better Auth JWT (signed EdDSA, issuer, audience, expiration and subject) and require its `sub` to be in the server-side `ADMIN_USER_IDS` allowlist. An empty allowlist denies everybody. Visitors cannot fetch admin data merely by opening the page; protected actions must pass the API's admin authorization check. Do not copy the local example ID or secrets into production.

The admin MVP deliberately **cannot** manually mark an order paid, initiate refunds, charge a buyer, override PayPal status, or delete products permanently. This remains demo infrastructure, not a commercial store. There is no migration, extra frontend package or new authorization table.

## Automated tests

```bash
cd apps/api
uv run --extra test pytest -q
```

With uv, no manual venv activation is required: use `uv sync` and `uv run` consistently. No PayPal network calls are made in unit tests. End-to-end PayPal approval requires your own sandbox credentials and manual buyer interaction.

## Architecture

```text
Next.js (presentation, Better Auth)
         |
  REST / Bearer JWT
         |
FastAPI routers       Presentation/API layer
         |
services/             Business layer (gifting, quota)
         |
repositories/         Persistence layer
         |
PostgreSQL            Database layer

integrations/         External adapters (PayPal, LiteLLM)
```

The code is organized by **technical layers** rather than separate feature folders, following our decision to use traditional layered architecture. No microservices are required.

## Privacy and security notes

- Recipient profiles are private: backend checks ownership of all saved recipient/occasion endpoints.
- Recipient birthdays are stored as month/day, with optional year. A birth year is not required.
- Reminder sending is **not implemented** yet; saving a birthday does not automatically send email or push notifications.
- Guest quota is per signed browser cookie/day, with IP fallback for direct API clients. Clearing cookies or using new accounts can evade quotas; implement WAF/rate limiting, verification and cost budgets before public launch.
- API model keys and PayPal credentials stay server-side. Buyer approval is mandatory.
- Demo products, availability, delivery, inventory and pricing are **fixtures**, not sourced from suppliers.
- Do not log personal gift recipient details or full chat prompts in third-party telemetry without permission; review your chosen LLM provider's data policies.

## Roadmap (not implemented yet)

1. Real supplier sourcing, verified inventory, admin catalog and delivery estimator.
2. AI evaluation set, contextual feedback loop, budget/semantic search, improved multilingual extraction, LangChain if useful.
3. Shipping address, tax calculation, inventory reservations, fulfillment, refunds, order history.
4. Persistent gift history, occasion reminder worker, emails and recipient preference editing/deletion in UI.
5. Hardened auth abuse limits, privacy controls, accessibility review, monitoring and full integration tests.
6. PayPal JS SDK integration after the checkout and order lifecycle are production-ready.

## Repository map

```text
apps/
  api/app/
    routers/         HTTP endpoints
    schemas/         Pydantic request/response schemas
    services/        Recommendation and quota business rules
    repositories/    Data access
    models/          SQLAlchemy models
    integrations/    PayPal integration
    db/              SQLAlchemy engine/session
    core/            Configuration and auth
  api/alembic/       Database migrations
  api/tests/         Automated backend tests
  web/app/           Next.js application and auth routes
  web/components/    Mobile UX
  web/lib/           API and auth clients
docs/                Project notes
```

## Licensing

MIT license. Review trademarks and the final product name before publishing Kadoku as a commercial brand.
