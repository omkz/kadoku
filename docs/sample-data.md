# Kadoku sample data — localhost and staging

Kadoku already has 100 illustrative `demo_only` products and a local-only
scenario generator. The new explicit `app.seed_sample` command provides the
**same synthetic dataset in either environment**, but does **not** create
credentials, alter roles, or contact PayPal. The separate operator-only
`app.seed_users` command provisions three Better Auth demo accounts and
explicitly grants their test roles.

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

## Automated demo user provisioning

A dedicated operator-only \`app.seed_users\` command makes three working
Better Auth identities. Passwords are passed **only via environment variables**
and are hashed by Better Auth itself; the script never writes hashes,
\`account\`, or \`session\` records.

| Default local email | Role | Purpose |
| --- | --- | --- |
| \`customer@demo.test\` | \`user\` | My People, My Orders, checkout |
| \`admin@demo.test\` | \`admin\` | Products, orders, analytics |
| \`owner@demo.test\` | \`super_admin\` | Team and role changes |

The script creates missing users using Better Auth's public signup API and
verifies existing demo users with a normal Better Auth password login before
reusing them. It **never adopts** an unrelated account with a colliding
email, resets its password, or overwrites a non-demo role. Reruns don't
duplicate user records, fixture orders or recipients. On first run, it also
seeds demo-only products and synthetic business data for the customer
account unless \`--skip-business-data\` is specified.

## Localhost

1. Ensure \`apps/web/.env.local\` \`AUTH_DATABASE_URL\` and
   \`apps/api/.env\` \`DATABASE_URL\` reference the **same local PostgreSQL**.
   Apply Alembic and Better Auth migrations, including the Admin plugin.
2. Start Next.js on \`http://localhost:3000\` so Better Auth signup works.
3. From \`apps/api\`, set three **different**, at-least-16-character
   development-only passwords through your shell (do not commit them):

   \`\`\`sh
   export DEMO_CUSTOMER_PASSWORD='choose-one-strong-demo-password'
   export DEMO_ADMIN_PASSWORD='choose-a-second-strong-demo-password'
   export DEMO_OWNER_PASSWORD='choose-a-third-strong-demo-password'
   uv run python -m app.seed_users --confirm-demo-users
   \`\`\`

   The above values are placeholders; choose your own private passwords.
   The command provisions the three identities and their sample catalog,
   analytics and customer fixtures. It does **not** touch PayPal.

4. Sign in as \`owner@demo.test\` and open \`/admin\` → Team; then sign in
   as \`admin@demo.test\` and \`customer@demo.test\` to compare permissions.

You can optionally override the three local emails with
\`DEMO_CUSTOMER_EMAIL\`, \`DEMO_ADMIN_EMAIL\`, and \`DEMO_OWNER_EMAIL\`.

To seed *additional* already-registered accounts without creating them:

\`\`\`sh
uv run python -m app.seed_sample \
  --email "your-other-test-account@example.test" --confirm-demo-data
\`\`\`

## Render staging (later; don't run on live production)

Only run once you've intentionally designated this deployment/database as
**staging** and migrated Better Auth's Admin plugin schema. The user seeder
can create separate staging identities through Better Auth when explicitly
requested.

The paid `kadoku-api` Render service supports SSH or Dashboard Shell;
the Free web service does not. Run from the API service's **trusted shell**,
where the staging `DATABASE_URL` is already configured.

Check host and database name without printing credentials:

```sh
uv run python -c "from app.core.config import get_settings; from sqlalchemy.engine import make_url; u=make_url(get_settings().database_url); print('host:', u.host, 'database:', u.database)"
```

To create three *staging-only* demo identities through Better Auth, choose
three unique passwords and three email addresses that are not real customer
accounts. From the trusted API shell, set:

```sh
export DEMO_CUSTOMER_EMAIL='customer-staging@example.test'
export DEMO_ADMIN_EMAIL='admin-staging@example.test'
export DEMO_OWNER_EMAIL='owner-staging@example.test'
export DEMO_CUSTOMER_PASSWORD='choose-one-strong-staging-password'
export DEMO_ADMIN_PASSWORD='choose-a-second-strong-staging-password'
export DEMO_OWNER_PASSWORD='choose-a-third-strong-staging-password'
```

Then, *only if that connection is really staging* and `BETTER_AUTH_URL` points
to the staging web service (not production), run:

```sh
ENVIRONMENT=staging STAGING_DEMO_SEED_ENABLED=true \
uv run python -m app.seed_users \
  --target staging \
  --expected-db-host 'ACTUAL_STAGING_DB_HOST' \
  --expected-db-name 'kadoku' \
  --expected-auth-host 'kadoku-web.onrender.com' \
  --confirm-demo-users --confirm-staging
```

This is the complete automatic user + business fixture setup. The old
`seed_sample` CLI remains available for an *additional* existing account.

To populate only an already-registered staging user, run:

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
- `seed_users` creates identities via Better Auth; `seed_sample` instead requires an account that already exists.
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
