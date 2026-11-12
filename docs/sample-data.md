# Sample data

All fixtures are **optional** and intended for local/staging tests. Seeded `paid` orders are fictional, not PayPal captures. Seeds do not run automatically on app startup.

## Sample products only

```bash
cd apps/api
uv run python -m app.seed
```

Adds up to 100 catalog examples without replacing existing products. The current Sandbox checkout accepts only demo-only USD products.

## Full local sample environment

Use the same local PostgreSQL database for Better Auth and FastAPI, and complete migrations from the [README](../README.md#local-setup). Start the Next.js app so Better Auth can create test users.

From the **repository root**:

```bash
pnpm db:seed
```

Prompts for three distinct 16+ character passwords. Creates/verifies the following test accounts, along with sample products, orders, recipients, and birthdays:

| Account | Role |
| --- | --- |
| `customer@demo.test` | `user` |
| `admin@demo.test` | `admin` |
| `owner@demo.test` | `super_admin` |

The seed checks existing account identity before reuse and does not overwrite passwords. You can supply `DEMO_CUSTOMER_PASSWORD`, `DEMO_ADMIN_PASSWORD`, and `DEMO_OWNER_PASSWORD` in a local shell for non-interactive runs.

To add sample orders/recipients to another **already registered** test account:

```bash
cd apps/api
uv run python -m app.seed_sample --email test-user@example.test --confirm-demo-data
```

## Reset (destructive)

Stop the app servers. Configure `apps/api/.env` and `apps/web/.env.local` to point to the **same dedicated local PostgreSQL database**, then from the repository root:

```bash
pnpm db:reset
```

This deletes local Kadoku accounts, orders, and catalog changes; it then migrates and seeds new test data. The CLI verifies the local target and refuses remote/staging/production databases or unknown database objects. Never use it against real data.

## Staging

See [Render staging](render-staging.md). Use explicit staging flags and test accounts only; never seed a production database or store test passwords in the repository.
