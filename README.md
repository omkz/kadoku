# Kadoku

**Your AI Gift Concierge.** Thoughtful gifts, made easy.

Kadoku helps people choose gifts through a conversation instead of searching a catalog. It is a **Sandbox-only MVP** with fictional products; no real purchases or fulfillment are supported.

## Features

- Conversational gift discovery with budget, interests, occasion, and follow-up refinements.
- Catalog-grounded recommendations: AI cannot invent products, prices, or stock.
- Saved recipients and birthdays, gift notes, and order history.
- PayPal Orders v2 Sandbox checkout with server-side capture verification.
- Admin catalog, orders, fulfillment tracking, and AG Studio analytics with AI Analyst.

Guest users have **3 requests/day** and signed-in users **5 requests/day** by default.

## Stack

- **Web:** Next.js 16, React 19, TypeScript, Better Auth.
- **API:** FastAPI, Python 3.11+, SQLAlchemy 2, Alembic.
- **Database:** PostgreSQL.
- **AI:** Google Gemini via LiteLLM for gift conversations; Nebius Token Factory via LiteLLM for AG Studio AI Analyst. Both are optional and independently configured. Gift recommendations also have a rules-based fallback.
- **Payments:** PayPal Orders v2 Sandbox.
- **Analytics:** AG Studio (commercial licence requirements apply).

## Run locally

Prerequisites: PostgreSQL, Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22+, and pnpm.

**1. Database**

```bash
sudo -u postgres psql -c "CREATE ROLE kadoku LOGIN PASSWORD 'local-only-password';"
sudo -u postgres psql -c "CREATE DATABASE kadoku OWNER kadoku;"
```

**2. API** (terminal 1)

```bash
cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload --port 8000
```

In `apps/api/.env`, set `DATABASE_URL` to the password you chose and replace `GUEST_QUOTA_SECRET` with a random secret (at least 32 characters). The API starts without model or PayPal keys; AI then uses rules-based recommendations and checkout stays disabled.

**3. Web** (terminal 2, from the repository root)

```bash
cd apps/web
cp .env.example .env
pnpm install
pnpm dlx auth@latest migrate --yes
pnpm dev
```

In `apps/web/.env`, set `AUTH_DATABASE_URL` for the same PostgreSQL database, choose a strong `BETTER_AUTH_SECRET`, and make `GUEST_COOKIE_SECRET` match the API's `GUEST_QUOTA_SECRET`.

Open **http://localhost:3000**. API docs: **http://localhost:8000/docs**.

For real model responses, set `AI_MODEL` and its provider key in the **API's** `.env`. For PayPal Sandbox checkout, set `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`, then use Sandbox buyer credentials. Never commit secrets.

## Tests

```bash
cd apps/api
uv run --extra test pytest -q
```

For the frontend, run `pnpm build` and `pnpm typecheck` inside `apps/web`. PayPal approval and live model calls require separate manual testing with test accounts/keys.

## Documentation

- [Local development, seed data, admin access, and troubleshooting](docs/local-development.md)
- [AG Studio analytics and AI Analyst setup](docs/analytics.md)
- [Render staging runbook](docs/render-staging.md)

## Limits

The catalog and seeded orders are fictional. PayPal captures are Sandbox-only, and the dashboard does not represent real revenue. Before live commerce, Kadoku needs verified suppliers, shipping/tax calculation, inventory reservation, refunds, stronger security controls, and customer support.

## License

[MIT](LICENSE).
