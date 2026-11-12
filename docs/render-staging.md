# Render is Kadoku staging

The current Render deployment is a **test environment**, separate from the
future production deployment. PayPal remains Sandbox. Demo data can be
discarded, but **normal deploys never reset or seed the database**.

Use the same `app.db` CLI as localhost, with `--target staging` and
explicit confirmation. Its staging implementation runs entirely in the
**kadoku-api Python Render Shell**, contacting the deployed Better Auth
web API over HTTPS for sign-up/sign-in. No Node.js checkout is needed inside
the API service.

## Recommended: manage staging from Render Shell

1. Merge and deploy the branch containing this CLI and the Better Auth Admin
   plugin, then check the kadoku-api and kadoku-web services are healthy.
   The API starts with Alembic upgrade; web starts with Better Auth migration.
2. Open **Render Dashboard → kadoku-api → Shell**. Its runtime must have
   `ENVIRONMENT=staging`, `PAYPAL_MODE=sandbox`, and a private
   `DATABASE_URL` provided by Render.
3. Inspect your deployment's actual DB and web hosts without printing secrets:

   ```bash
   uv run --active python -c 'from sqlalchemy.engine import make_url; from urllib.parse import urlsplit; from app.core.config import get_settings; s=get_settings(); u=make_url(s.database_url); print("environment:",s.environment,"paypal:",s.paypal_mode,"database host:",u.host,"database name:",u.database,"auth host:",urlsplit(s.better_auth_url).hostname)'
   ```

4. For a **non-destructive** schema verification (optional):

   ```bash
   uv run --active python -m app.db migrate --target staging --confirm-staging \
     --expected-db-host "<DB_HOST>" --expected-db-name "<DB_NAME>" \
     --expected-auth-host "<WEB_HOST>"
   ```

5. If the staging database needs to be **erased entirely**, first ensure
   no real users/data exist and that you accept downtime. This deletes
   Better Auth accounts, sessions, orders and all other Kadoku tables.
   Do **not** use the local `db:reset` script.

   ```bash
   export STAGING_DB_RESET_ENABLED=true
   uv run --active python -m app.db reset --target staging --confirm-staging \
     --expected-db-host "<DB_HOST>" --expected-db-name "<DB_NAME>" \
     --expected-auth-host "<WEB_HOST>" --confirm-db "<DB_NAME>"
   unset STAGING_DB_RESET_ENABLED
   ```

   **After reset**, go to **kadoku-web** in Render and manually **Restart
   Service** or redeploy it. Its startup runs the Better Auth migrations
   that recreate `user`, `session`, `account`, `jwks` and plugin columns.
   **Do not seed until kadoku-web is healthy again.** The API-side reset
   restores Alembic tables only.

6. Seed **the same fixture data as local**, without resetting. Export
   test-only credentials only in the interactive Shell session, not in
   Render environment settings or source control. Choose separate passwords
   of at least 16 characters. The following prompts hide password input:

   ```bash
   export STAGING_DEMO_SEED_ENABLED=true
   export DEV_ADMIN_EMAIL='admin@kadoku.test'
   export DEV_CUSTOMER_NAME='customer'
   export DEV_CUSTOMER_EMAIL='customer@kadoku.test'
   read -r -s -p 'Demo admin password: ' DEV_ADMIN_PASSWORD; echo
   export DEV_ADMIN_PASSWORD
   read -r -s -p 'Demo customer password: ' DEV_CUSTOMER_PASSWORD; echo
   export DEV_CUSTOMER_PASSWORD

   uv run --active python -m app.db seed --target staging --confirm-staging \
     --expected-db-host "<DB_HOST>" --expected-db-name "<DB_NAME>" \
     --expected-auth-host "<WEB_HOST>"

   unset STAGING_DEMO_SEED_ENABLED DEV_ADMIN_PASSWORD DEV_CUSTOMER_PASSWORD
   ```

   This creates/verifies **1 admin and 1 customer** using the Better Auth
   API and populates **100 demo products, 38 account orders, 6 My People
   (including Mom) and 5 occasions**. Synthetic `paid` orders are
   not actual PayPal captures or revenue. Repeating `seed` inserts only
   missing fixtures and does not reset passwords. Existing accounts must
   have the expected name and password to be reused; the process refuses
   to adopt an unrelated account merely because the email matches.

7. Verify the web app: sign in as admin and customer, inspect Customers,
   Orders and My People. The orders and analytics show test data only.

## Security

- Only Render staging and PayPal Sandbox are allowed for remote seed/reset.
- The operator confirms the exact private PostgreSQL host and name and HTTPS
  Better Auth hostname. A separate `STAGING_DB_RESET_ENABLED=true`
  opt-in plus exact DB name are required for any destructive reset.
- Unknown database objects cause reset to abort.
- The API Shell uses Render's **internal PostgreSQL network connection**.
  There is no need to allowlist a developer's public IP.
- Do not put test-account passwords into Git, `render.yaml`, public docs,
  screenshots or issue comments. Use the Shell for one-time execution.
- Production must eventually use separate services and database.
