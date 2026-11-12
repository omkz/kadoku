# Kadoku

**Your AI Gift Concierge.** Thoughtful gifts, made easy.

Kadoku helps people find gifts through conversation instead of browsing endless product catalogs.

## Features

- Mobile-first gift discovery with one top pick, up to two alternatives, and catalog-grounded refinements.
- Saved recipients, birthdays, gift notes, and order history.
- PayPal Orders v2 Sandbox checkout, capture recovery, and admin refunds.
- Admin catalog, order management, and AG Studio analytics with AI Analyst.

## Stack

Next.js, TypeScript, Better Auth, FastAPI, SQLAlchemy 2, PostgreSQL, PayPal Orders v2, and AG Studio. Gemini powers gift conversations; Nebius Token Factory powers the admin AI Analyst, both via LiteLLM. The gift recommender also supports a rules-based fallback.

## Local setup

Requires PostgreSQL, Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22+, and pnpm.

Create a local database:

```bash
sudo -u postgres psql -c "CREATE ROLE kadoku LOGIN PASSWORD 'local-only-password';"
sudo -u postgres psql -c "CREATE DATABASE kadoku OWNER kadoku;"
```

**API** (terminal 1):

```bash
cd apps/api
cp .env.example .env
# Set DATABASE_URL and a strong GUEST_QUOTA_SECRET in .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

**Web** (terminal 2, from the repository root):

```bash
cd apps/web
cp .env.example .env
# Set AUTH_DATABASE_URL, BETTER_AUTH_SECRET, and GUEST_COOKIE_SECRET
pnpm install
pnpm dlx auth@latest migrate --yes --config ./lib/auth.ts
pnpm dev
```

Use the same PostgreSQL database for both apps. `GUEST_COOKIE_SECRET` must match the API's `GUEST_QUOTA_SECRET`.

Open [localhost:3000](http://localhost:3000). API docs: [localhost:8000/docs](http://localhost:8000/docs).

**Optional sample data:** Run `uv run python -m app.seed` from `apps/api` to populate 100 fictional products. See [sample data](docs/sample-data.md) for sample orders and accounts.

**Optional integrations:** Set `AI_MODEL` and its key for model-backed responses, or `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` for Sandbox checkout. Keep credentials in the backend `.env`.

## Tests

```bash
cd apps/api && uv run --extra test pytest -q
cd ../web && pnpm build && pnpm typecheck
```

External AI calls and PayPal approval/capture require separate manual tests.

## Documentation

[Sample data](docs/sample-data.md) · [PayPal Sandbox](docs/paypal-sandbox.md) · [Admin roles](docs/admin-roles.md) · [AI Analyst](docs/analytics.md) · [Architecture](docs/architecture.md) · [Render staging](docs/render-staging.md)

## Roadmap

- Automate webhook reconciliation and strengthen payment failure monitoring.
- Integrate real suppliers, inventory, shipping, tax, and fulfillment.
- Add production safeguards, then enable PayPal Live.

Live payments and real-order fulfillment are not implemented yet.

## License

[MIT](LICENSE).
