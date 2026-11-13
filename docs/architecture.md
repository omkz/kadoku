# Architecture

Kadoku is a Next.js web app and a FastAPI API backed by PostgreSQL.

```text
Next.js / Better Auth
         |
   JWT-authenticated API
         |
FastAPI routers → services → repositories → SQLAlchemy → PostgreSQL
         |
    PayPal / LiteLLM adapters
```

- **Identity:** Better Auth manages sessions and auth tables. FastAPI verifies signed JWTs using JWKS.
- **Authorization:** FastAPI reads the current `user.role` and `user.banned` from Better Auth's database. See [admin roles](admin-roles.md).
- **AI:** Gemini via LiteLLM can power gift conversations. Catalog filters enforce price, stock, and exclusions; rules-based fallback works without an LLM.
- **Analytics:** AG Studio uses aggregated admin datasets. Its AI Analyst can use a separate model (Nebius via LiteLLM).
- **Payments:** PayPal Orders v2 Sandbox, authenticated buyer approval, server-verified capture, and full/partial admin refunds with idempotent retry. Webhooks are verified and logged but do not yet reconcile payment state.
- **Migrations:** Alembic owns application tables; Better Auth owns authentication tables.

Supplier-backed inventory, automatic webhook reconciliation, refund-aware analytics, and PayPal Live are planned.
