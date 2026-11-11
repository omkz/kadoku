# Kadoku Render staging database

Kadoku's current Render services are a **staging** environment (not production).
Demo products and fictional orders are allowed, but normal deployments **never
reset the database or provision sample users**. PayPal remains Sandbox.

Use the same Python CLI as localhost, with explicit staging verification:

- `uv run python -m app.db migrate` — non-destructive schema migration
- `uv run python -m app.db reset` — intentionally deletes the selected database's
  Kadoku `public` schema, including accounts, sessions, orders and products
- `uv run python -m app.db seed` — creates the same two test accounts, 100 demo
  products, 38 orders, six My People and five occasions as localhost (idempotent)

All three use `--target staging` and confirmation options. The CLI refuses
remote connections by default.

## Before running staging commands

1. Work from a trusted local checkout of `feature/admin-role-rbac` with
   Python/uv, Node.js and pnpm installed (`cd apps/web && pnpm install`).
2. Locate **kadoku-db → Connect → External Database URL** in Render. The URL
   must use TLS (`sslmode=require`). Confirm the database's exact host and name.
3. Under **kadoku-db → Networking / Access Control**, temporarily allow only
   **your current public IP address (/32)**. Render's existing
   `ipAllowList: []` blocks access from outside Render. Do not open
   `0.0.0.0/0`. Revoke this temporary rule immediately after the operation.
4. Retrieve the existing staging `BETTER_AUTH_SECRET` from the **kadoku-web**
   service's environment (do not generate a replacement for this operation).
5. Put staging connection details and sample-account passwords in *operator shell
   environment variables*, not in Git, a committed `.env`, or `render.yaml`.
   `apps/web/.env` remains configured for localhost.
6. The test emails must not correspond to real accounts. Use **two distinct**
   passwords of at least 16 characters.

Example environment **with placeholders**:

```bash
export ENVIRONMENT=staging
export PAYPAL_MODE=sandbox
export STAGING_DEMO_SEED_ENABLED=true
export DATABASE_URL='<Render External Database URL with sslmode=require>'
export AUTH_DATABASE_URL="$DATABASE_URL"
export BETTER_AUTH_URL='https://kadoku-web.onrender.com'
export BETTER_AUTH_SECRET='<existing kadoku-web BETTER_AUTH_SECRET>'
export DEV_ADMIN_EMAIL='admin@kadoku.test'
export DEV_ADMIN_PASSWORD='<unique-strong-demo-admin-password>'
export DEV_CUSTOMER_NAME='customer'
export DEV_CUSTOMER_EMAIL='customer@kadoku.test'
export DEV_CUSTOMER_PASSWORD='<unique-strong-demo-customer-password>'
```

The hostname `kadoku-web.onrender.com` is an **example**; use the actual
Render service's hostname. Never paste actual secrets into chats or screenshots.

Commands below run from `apps/api`. Replace the hostnames, database name
and auth hostname with their **verified actual values**:

```bash
cd apps/api

# Non-destructive migration (optional before a reset).
uv run python -m app.db migrate \
  --target staging --confirm-staging \
  --expected-db-host <EXTERNAL_DATABASE_HOST> \
  --expected-db-name <DATABASE_NAME> \
  --expected-auth-host <STAGING_WEB_HOST>

# WARNING: destructive. ALL existing staging data is deleted.
export STAGING_DB_RESET_ENABLED=true
uv run python -m app.db reset \
  --target staging --confirm-staging \
  --expected-db-host <EXTERNAL_DATABASE_HOST> \
  --expected-db-name <DATABASE_NAME> \
  --expected-auth-host <STAGING_WEB_HOST> \
  --confirm-db <DATABASE_NAME>
unset STAGING_DB_RESET_ENABLED

# Populate the same fixtures as local app.db seed.
uv run python -m app.db seed \
  --target staging --confirm-staging \
  --expected-db-host <EXTERNAL_DATABASE_HOST> \
  --expected-db-name <DATABASE_NAME> \
  --expected-auth-host <STAGING_WEB_HOST>
```

**Important:** the angle-bracket placeholders above must be substituted
before executing; do not type them literally. A clean reset is only needed
when deliberately replacing all staging data. Normally use `seed` on its
own, which first runs non-destructive migrations.

The CLI checks the PostgreSQL database host/name and the HTTPS Better Auth
hostname, validates both FastAPI and Better Auth database URLs match, blocks
production or live PayPal, inspects unknown schema objects before reset, and
requires a separate opt-in and exact database-name confirmation for a remote
reset. The account seeder verifies passwords for existing accounts rather
than taking ownership of an email address.

## Deployment order and verification

Render's Free tier does not provide an interactive shell or one-off jobs, so
staging administration happens using the temporary allowlisted external
PostgreSQL connection from a trusted machine.

1. Ensure PR CI succeeds. Reset and seed the staging database as above.
   The staging site can briefly fail while its schema is being rebuilt.
2. Merge the PR and let Render deploy both services. The API runs Alembic
   migrations on startup; the web service runs Better Auth migrations before
   serving requests. Both are **non-destructive**. Neither seeds users.
3. Log in to staging with the test admin and customer. Validate the Customers
   table, Orders, My People (Mom), and 7/30/90-day analytics.
4. Revoke the external DB IP allowlist rule immediately and unset shell
   variables holding database URLs, tokens and demo credentials.

Never use these credentials, data or reset procedure against an eventual
production database. Production will have its own database, domains and
secret configuration.
