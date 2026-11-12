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

To create a **new admin account** in local development, run from the repository root:

```bash
pnpm admin:create --email superadmin@kadoku.test --role super_admin --confirm
```

The CLI prompts for a password (no plaintext password in arguments), uses Better Auth to create the account, then assigns its database-backed role. It refuses to overwrite existing accounts and is disabled with a production environment. Use `--role admin` for a regular admin account. Run only from a trusted shell with `apps/web/.env` configured; no seeding or app startup automatically creates a super admin.

To promote **an existing registered account**, use this command from a trusted API shell:

```bash
cd apps/api
uv run python -m app.bootstrap_super_admin --email your-registered-email@example.com --confirm
```

Sign out and back in; use **/admin → Team** to manage other roles. Admins cannot change team roles. A super admin cannot change their own role or remove the last super admin. Changes are authorized server-side.

For sample users, use [sample data](sample-data.md), which provisions separate test accounts. Do not run demo seeds or role bootstrap automatically during deploy.
