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

To provision a **separate super administrator** in local development, set these values in the untracked `apps/web/.env`:

```dotenv
DEV_SUPER_ADMIN_EMAIL=superadmin@kadoku.test
DEV_SUPER_ADMIN_PASSWORD=<unique-16+-character-password>
DEV_SUPER_ADMIN_NAME=Super Admin
```

From the repository root, on the branch containing this CLI:

```bash
pnpm admin:create
```

Like `db:seed`, this command requires no confirmation flag. It uses Better Auth to hash and store the password, then assigns the database-backed `super_admin` role. It is safe to rerun with the same credentials and role; it never overwrites an existing account or resets its password. A conflicting role or password is rejected.

For a regular admin, set `DEV_ADMIN_EMAIL`/`DEV_ADMIN_PASSWORD` and run `pnpm admin:create --role admin`. This CLI only accepts local PostgreSQL and a local Better Auth URL, and never runs automatically on application startup or deployment. Keep `.env` out of version control.

To promote **an existing registered account**, use this command from a trusted API shell:

```bash
cd apps/api
uv run python -m app.bootstrap_super_admin --email your-registered-email@example.com --confirm
```

Sign out and back in; use **/admin → Team** to manage other roles. Admins cannot change team roles. A super admin cannot change their own role or remove the last super admin. Changes are authorized server-side.

For sample users, use [sample data](sample-data.md), which provisions separate test accounts. Do not run demo seeds or role bootstrap automatically during deploy.
