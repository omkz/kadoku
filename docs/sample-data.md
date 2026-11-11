# Kadoku sample data — localhost and staging

Kadoku already has 100 illustrative `demo_only` products and a local-only
scenario generator. The new explicit `app.seed_sample` command provides the
**same synthetic dataset in either environment**, but does **not** create
credentials, alter roles, or contact PayPal.

| Dataset | Count | Visibility |
| --- | ---: | --- |
| Demo-only catalog | 100 products | Shared storefront/admin, seeded separately |
| Synthetic analytics | 38 fictional orders | Admin analytics/orders |
| Account sample orders | 38 fictional orders | Only the named Better Auth account's My Orders |
| My People | 5 fictional recipients | Only the named account |
| Birthdays | 4 sample birthdays | Only the named account |

Orders include paid, pending, approval-pending, and cancelled states, and
fulfillment statuses. **All payments are fictional; no PayPal capture exists.**
`paid` denotes a sample state, not real funds. IDs use deterministic UUID5
scoped to either analytics or the account's Better Auth ID. Repeating the
command inserts **zero** rows once seeded, does not update existing sample
orders, and never resets existing customer data. Do not use the orders as
evidence of sales. Fixture dates are fixed when first inserted.

## Localhost

1. Make sure Next.js `apps/web/.env.local` `AUTH_DATABASE_URL` and FastAPI
   `apps/api/.env` `DATABASE_URL` point to the **same local database**.
   Better Auth needs PostgreSQL; set up/migrate both application schema
   (Alembic) and Better Auth schema (including the Admin plugin).
2. Start both apps. Sign up **once** at `http://localhost:3000` with an
   account reserved for testing. No default login/password is stored in Git.
3. From `apps/api`, populate the 100 demo catalog products if missing:

   ```sh
   uv run python -m app.seed
   ```

4. Then seed account scenarios and analytics:

   ```sh
   uv run python -m app.seed_sample \
     --email "your-test-account@example.test" \
     --confirm-demo-data
   ```

5. If testing RBAC PR #29, **separately** bootstrap your own registered
   super admin (this script does not promote anyone):

   ```sh
   uv run python -m app.bootstrap_super_admin \
     --email "your-test-account@example.test" --confirm
   ```

6. Sign out/in and inspect `/admin`, My Orders and My People.
   Create a **second account** to verify its data is isolated; its My Orders
   and My People should initially be empty.

## Render staging (later; don't run on live production)

Only run once you've intentionally designated this deployment/database as
**staging**, migrated Better Auth's Admin plugin schema and registered a
separate staging test account via the Kadoku website.

The paid `kadoku-api` Render service supports SSH or Dashboard Shell;
the Free web service does not. Run from the API service's **trusted shell**,
where the staging `DATABASE_URL` is already configured.

Check host and database name without printing credentials:

```sh
uv run python -c "from app.core.config import get_settings; from sqlalchemy.engine import make_url; u=make_url(get_settings().database_url); print('host:', u.host, 'database:', u.database)"
```

Then *only if that connection is really staging* run:

```sh
ENVIRONMENT=staging STAGING_DEMO_SEED_ENABLED=true \
uv run python -m app.seed_sample \
  --target staging \
  --email "registered-staging-test@example.test" \
  --expected-db-host "ACTUAL_STAGING_DB_HOST" \
  --expected-db-name "kadoku" \
  --confirm-demo-data --confirm-staging
```

The per-command environment variables do **not** alter Render service
configuration or `render.yaml`. Run a separate command for every additional
pre-registered demo account if desired; the shared dashboard orders remain
idempotent. **Never put demo-seeding flags on the web service environment
or on the normal deploy/start command.**

Mandatory safety checks:
- `PAYPAL_MODE=sandbox`; staging fails closed in live PayPal mode.
- `ENVIRONMENT=staging` and `STAGING_DEMO_SEED_ENABLED=true` explicitly
  supplied for **this one command**.
- Remote PostgreSQL host and database **must match** the operator-supplied
  expected values; local mode always rejects a remote host.
- Manual `--confirm-demo-data` and `--confirm-staging` flags.
- Account must already exist in Better Auth in that exact database.
- No destructive updates, no user creation/passwords/role grants, no network
  PayPal requests, and no API endpoint that can trigger seeding.

The primary `render.yaml` currently runs the service with
`ENVIRONMENT=production`; **do not change that setting merely to seed
data**. This command overrides `ENVIRONMENT` *only in its own process*
when running on a trusted operator shell. If there is any doubt which
database is connected, stop and verify before proceeding.

## Retiring sample data

This command only inserts deterministic fixtures. Cleanup is intentionally
not automatic because demo accounts may acquire their own real test orders
over time. Plan a reviewed, targeted cleanup by fixture ID prefixes and
account ownership; never `TRUNCATE` application tables.
