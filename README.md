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
- End-to-end recommendation request to FastAPI, grounded in 12 **demo-only** products, showing up to three swipeable cards with one highlighted pick.
- Budget, interests, occasion filtering and ranking; different product categories when possible.
- Guest recommendation quota enforced on the backend; signed HttpOnly guest identity cookie issued by Next.js. Members have a larger daily quota.
- Better Auth wiring, JWT/JWKS validation in FastAPI, private recipient and birthday endpoints, My People form.
- Product selection, gift note display, PayPal Sandbox order create/approve/capture if configured.
- Versioned Alembic migration and automated API tests.

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
uv pip install -e '.[ai]'
# Set AI_MODEL=provider/model and the matching provider API key in apps/api/.env
```

Without an AI key, the application still works in **rules-based demo mode**. The LLM is used only for gift-intent extraction; the server independently ranks products, enforces stock and price limits, and returns catalog data. Set `AI_MODEL` (LiteLLM provider/model), install optional AI dependencies with `uv sync --extra ai`, and provide the provider API key. `AI_TIMEOUT_SECONDS` and `AI_MAX_OUTPUT_TOKENS` cap each AI call. Invalid or unavailable model responses fall back to the rule parser; the API response identifies the path with `provider` (`llm`, `rules`, or `rules-fallback`). A model failure does not grant extra guest recommendations.

### 3. Next.js and Better Auth

From the **repository root**, install dependencies:

```bash
npm install
cd apps/web
cp .env.example .env
# Update AUTH_DATABASE_URL and BETTER_AUTH_SECRET (at least 32 random characters).
# Set GUEST_COOKIE_SECRET to EXACTLY the value of FastAPI's GUEST_QUOTA_SECRET.
# Match BETTER_AUTH_URL in both services (default http://localhost:3000).
npx auth@latest migrate --yes
npm run dev
```

Open <http://localhost:3000>. Google OAuth is optional and will not be offered until client/server Google credentials and the public feature flag are configured. The email/password flow can work without Google OAuth.

> The Better Auth migration creates its authentication tables in PostgreSQL. Alembic owns the Kadoku application tables. Both can coexist in the same database.

### 4. PayPal Sandbox (optional)

Create a **Sandbox** REST application in PayPal Developer and populate `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in `apps/api/.env`. Optionally configure webhook ID for signature verification. Use PayPal **test buyer** accounts only. Without credentials, the checkout endpoint returns HTTP 503 (the UI shows the error). **No real fulfillment or shipping occurs.**

This implementation uses the Orders API `payer-action` redirect and PayPal's approval return page, not the JavaScript SDK buttons yet. Do not call it production-ready. A shipping/tax quote, fulfillment, stock reservations, refunds, fraud review, and stronger abuse prevention are required before real commerce.

## Automated tests

```bash
cd apps/api
source .venv/bin/activate
pytest -q
```

No PayPal network calls are made in unit tests. End-to-end PayPal approval requires your own sandbox credentials and manual buyer interaction.

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
