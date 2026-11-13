# Render staging

Render is a test environment, not the future production store. PayPal stays in **Sandbox**. Normal deploys run migrations only; they **must not** reset or seed the database.

For the **single Starter service (Next.js + FastAPI)**, follow [unified staging deployment](render-unified-staging.md) first. The commands below run from `apps/api`; in the unified Render Shell, run `cd apps/api` before using them and set `export BETTER_AUTH_URL="$RENDER_EXTERNAL_URL"` for the current authentication origin. The original split API Render Shell already starts in `apps/api`.

## Seed staging

Run commands from a **trusted kadoku-api Render Shell** after confirming both API and web services are healthy and Better Auth migrations are applied.

First verify the connected DB and auth hosts **without printing credentials**:

```bash
uv run --active python -c 'from app.core.config import get_settings; from sqlalchemy.engine import make_url; from urllib.parse import urlsplit; s=get_settings(); u=make_url(s.database_url); print("db host:",u.host,"db name:",u.database,"auth host:",urlsplit(s.better_auth_url).hostname)'
```

Create three distinct **test-only** Better Auth accounts (customer, admin, super admin). Set their staging-specific addresses and passwords in the Shell, **not** in Git or persistent service settings:

```bash
export DEMO_CUSTOMER_EMAIL='customer-staging@example.test'
export DEMO_ADMIN_EMAIL='admin-staging@example.test'
export DEMO_OWNER_EMAIL='owner-staging@example.test'
read -r -s -p 'Customer password: ' DEMO_CUSTOMER_PASSWORD; echo; export DEMO_CUSTOMER_PASSWORD
read -r -s -p 'Admin password: ' DEMO_ADMIN_PASSWORD; echo; export DEMO_ADMIN_PASSWORD
read -r -s -p 'Owner password: ' DEMO_OWNER_PASSWORD; echo; export DEMO_OWNER_PASSWORD
```

Use **three different passwords of 8+ characters**. Substitute the actual confirmed DB/auth hosts:

```bash
ENVIRONMENT=staging STAGING_DEMO_SEED_ENABLED=true \
uv run --active python -m app.seed_users --target staging \
  --expected-db-host '<DB_HOST>' --expected-db-name '<DB_NAME>' \
  --expected-auth-host '<WEB_HOST>'
unset DEMO_CUSTOMER_PASSWORD DEMO_ADMIN_PASSWORD DEMO_OWNER_PASSWORD
```

This is the same seed implementation as `pnpm run db:seed`, invoked from the API directory in Render Shell. It uses Better Auth signup/login, assigns test roles, and adds synthetic catalog, orders, and recipients. It makes **no PayPal transactions**, does not overwrite existing passwords, and is not executed by normal deploys.

## Reset staging (destructive)

Only for a disposable staging database after confirming it contains **no real data**. The guarded CLI requires an explicit opt-in, the exact DB name, and matching DB/auth hosts:

```bash
STAGING_DB_RESET_ENABLED=true ENVIRONMENT=staging \
uv run --active python -m app.db reset --target staging --confirm-staging \
  --expected-db-host '<DB_HOST>' --expected-db-name '<DB_NAME>' \
  --expected-auth-host '<WEB_HOST>' --confirm-db '<DB_NAME>'
```

This deletes **all staging data**, including Better Auth accounts. Restart/redeploy the web service to restore Better Auth tables before seeding again. Never set the reset flag on the running service or deploy pipeline.

See [sample data](sample-data.md) for local commands. Do not use these workflows on production.
