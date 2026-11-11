# Kadoku administrator roles

Staging currently uses **Better Auth for identity** and **FastAPI for business
authorization**. The Admin plugin adds role/ban fields to Better Auth's user
and session tables; no new role tables are required.

| Role | Storefront | Admin dashboard | Team role changes |
| --- | --- | --- | --- |
| `user` | Yes | No | No |
| `admin` | Yes | Products, orders, analytics | No |
| `super_admin` | Yes | All store operations | Yes |

Only a verified Better Auth JWT subject may access FastAPI. For every admin
request, FastAPI re-reads `user.role` and `user.banned` from the database;
JWT role claims, browser state, and `ADMIN_USER_IDS` are **not** trusted.
The Better Auth Admin plugin's user-management endpoints are deliberately
disabled via empty custom permission sets; Team changes are performed
through super-admin-only FastAPI routes with server checks.

## Deployment / schema migration (required before enabling new auth)

**Do not merge and auto-deploy before preparing the migration.** The Better
Auth Admin plugin adds five fields: `user.role`, `user.banned`,
`user.banReason`, `user.banExpires`, and `session.impersonatedBy`.

From `apps/web` against the **staging database** (with `AUTH_DATABASE_URL`
configured), run the Better Auth CLI once:

```sh
npx --yes auth@latest migrate --yes --config ./lib/auth.ts
```

Render Free web services may not have an interactive shell. For an existing
Render Free deployment, temporarily run that migration before Next.js
in its **start command** and deploy once, verify success in logs, then
restore the normal start command in `render.yaml`. The existing
`initialDeployHook` is **not** a replacement: it does not run again on
subsequent deployments. Never use `generate` in place of `migrate`.
Do not store database URLs/passwords in Git.

After the schema exists, register/sign in to your own staging account and
run this command from a **trusted kadoku-api shell** (with `DATABASE_URL`
configured) **once**:

```sh
uv run python -m app.bootstrap_super_admin --email YOUR_REGISTERED_EMAIL --confirm
```

It promotes only the named existing account. No new admin account or role
is ever created from public signup, the demo seeder, or automatic deploy.
Sign out and sign back in to refresh Better Auth's cached session role.

Then visit `/admin` → **Team** to grant or revoke `admin`/
`super_admin` for already-registered users. The current super admin
cannot alter their own role, and the API refuses to demote the final
super admin. Team changes are logged in the API logs.

## Validation

- `user` accounts must receive HTTP 403 for `/api/v1/admin/*`.
- `admin` may open overview/orders/products/analytics but gets HTTP 403
  for `GET /api/v1/admin/team` and role changes.
- `super_admin` can use the Team panel.
- A demoted/banned account loses admin API privileges immediately even
  when holding an otherwise valid JWT.
- Never run demo scenario seeds on production databases.

## Sample data for login/RBAC testing

After sign-up, you can populate local My Orders, My People, and analytics
with fictional fixtures. See [sample data](sample-data.md). The seeder
intentionally does **not** create Better Auth users or grant administrator
rights. Register the test account first; use `bootstrap_super_admin` only
for the initial trusted administrator.

## Automated demo accounts

For isolated local/staging test accounts (customer, admin, super admin) use the
operator-only \`app.seed_users\` flow in [sample-data.md](sample-data.md).
This is strictly separate from the normal initial administrator bootstrap
for a real account.
