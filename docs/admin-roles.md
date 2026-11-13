# Admin roles

Kadoku uses Better Auth for identity and **database-backed roles** for authorization. FastAPI checks `user.role` and `user.banned` on every admin API request; it does not trust a browser role or `ADMIN_USER_IDS`.

| Role | Access |
| --- | --- |
| `user` | Storefront and own account |
| `admin` | Products, orders, analytics |
| `super_admin` | Admin features, refunds, and Team role management |

## Setup

Apply the Better Auth Admin plugin migration before enabling admin access:

```bash
cd apps/web
pnpm dlx auth@latest migrate --yes --config ./lib/auth.ts
```

For **local demo accounts**, configure `DEV_SUPER_ADMIN_EMAIL`, `DEV_SUPER_ADMIN_PASSWORD`, and optional `DEV_SUPER_ADMIN_NAME` in untracked `apps/web/.env`. The same file holds `DEV_ADMIN_*` and `DEV_CUSTOMER_*` settings. Configure each demo account's email and password explicitly in `.env` (8+ characters, distinct passwords). No default emails or passwords are hardcoded in the seed implementation.

From the repository root, with the web server running and both services using the same local PostgreSQL database:

```bash
pnpm run db:seed
```

This manually provisions three distinct Better Auth test identities (customer, admin, super admin), then adds sample products/orders. No confirmation flag or separate `admin:create` command. Re-running verifies existing credentials and roles; it never overwrites passwords or demotes/promotes unrelated accounts. The command refuses production and non-local targets. Staging requires an explicit target and DB/auth host checks; see [Render staging](render-staging.md).

To promote **an existing registered account**, use this command from a trusted API shell:

```bash
cd apps/api
uv run python -m app.bootstrap_super_admin --email your-registered-email@example.com --confirm
```

Sign out and back in; use **/admin → Team** to manage other roles. Admins cannot change team roles. A super admin cannot change their own role or remove the last super admin. Changes are authorized server-side.

For sample users, use [sample data](sample-data.md), which provisions separate test accounts. Do not run demo seeds or role bootstrap automatically during deploy.
