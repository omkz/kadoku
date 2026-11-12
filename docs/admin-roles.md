# Admin roles

Kadoku uses Better Auth for identity and **database-backed roles** for authorization. FastAPI checks `user.role` and `user.banned` on every admin API request; it does not trust a browser role or `ADMIN_USER_IDS`.

| Role | Access |
| --- | --- |
| `user` | Storefront and own account |
| `admin` | Products, orders, analytics |
| `super_admin` | Admin features and Team role management |

## Setup

Apply the Better Auth Admin plugin migration before enabling admin access:

```bash
cd apps/web
pnpm dlx auth@latest migrate --yes --config ./lib/auth.ts
```

Create a normal account through Kadoku, then promote **that existing account** from a trusted API shell:

```bash
cd apps/api
uv run python -m app.bootstrap_super_admin --email your-registered-email@example.com --confirm
```

Sign out and back in; use **/admin → Team** to manage other roles. Admins cannot change team roles. A super admin cannot change their own role or remove the last super admin. Changes are authorized server-side.

For sample users, use [sample data](sample-data.md), which provisions separate test accounts. Do not run demo seeds or role bootstrap automatically during deploy.
