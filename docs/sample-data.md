# Sample data

All fixtures are **optional** and intended for local/staging tests. Seeded `paid` orders are fictional, not PayPal captures. Seeds do not run automatically on app startup.

## Local

Complete database migrations and start Next.js so Better Auth is available. Configure `apps/api/.env` and `apps/web/.env` to use the **same local PostgreSQL database**.

In untracked `apps/web/.env`, set the three email/password pairs: `DEV_CUSTOMER_*`, `DEV_ADMIN_*`, and `DEV_SUPER_ADMIN_*` (16+ characters per password, all different). For example:

```dotenv
DEV_CUSTOMER_EMAIL=customer@kadoku.test
DEV_CUSTOMER_PASSWORD=<unique-local-password-16+>
DEV_ADMIN_EMAIL=admin@kadoku.test
DEV_ADMIN_PASSWORD=<another-local-password-16+>
DEV_SUPER_ADMIN_EMAIL=superadmin@kadoku.test
DEV_SUPER_ADMIN_PASSWORD=<third-local-password-16+>
```

Run manually from the **repository root**:

```bash
pnpm db:seed
```

This creates/verifies the customer, admin, and super admin via Better Auth and seeds 100 fictional products, sample orders, recipients, and birthdays. It is idempotent and does not replace existing passwords, roles, products or customer orders. Missing passwords prompt only in an interactive local terminal.

No separate product seed or `admin:create` command is needed. Synthetic `paid` orders have **no PayPal capture** and cannot be refunded.

## Reset (destructive)

Stop the app servers. Configure `apps/api/.env` and `apps/web/.env.local` to point to the **same dedicated local PostgreSQL database**, then from the repository root:

```bash
pnpm db:reset
```

This deletes local Kadoku accounts, orders, and catalog changes; it then migrates and seeds new test data. The CLI verifies the local target and refuses remote/staging/production databases or unknown database objects. Never use it against real data.

## Staging

See [Render staging](render-staging.md). Use explicit staging flags and test accounts only; never seed a production database or store test passwords in the repository.
