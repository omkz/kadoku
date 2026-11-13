# Unified Render staging

One native **Python** Web Service (`kadoku-api`, Starter 512 MB) runs Next.js and FastAPI without Docker. PostgreSQL stays separate.

- Next.js: public $PORT, Better Auth, pages, and `/backend/*` proxy.
- FastAPI: private `127.0.0.1:8000`, forwarded by Next.js rewrites.
- `/api/v1/*` (including PayPal webhooks) also forwards to FastAPI.
- `/api/health` checks both processes.
- `kadoku-web` (Free) stays on `main` for rollback; do not delete it yet.

## Prepare the existing Starter

After merging this PR into `staging`, review and apply the Blueprint settings to the **existing** `kadoku-api` service, not a new paid service.

| Setting | Value |
| --- | --- |
| Branch | `staging` |
| Runtime | Python |
| Root directory | Repository root (`.`), not `apps/api` |
| Build | `bash scripts/render-unified-build.sh` |
| Pre-deploy | `bash scripts/render-unified-migrate.sh` |
| Start | `bash scripts/render-unified-start.sh` |
| Health | `/api/health` |
| Instance | Existing Starter (`0.5c-512mb`) |

Automatic deploy is disabled; manually deploy once the config is reviewed. `render.yaml` configures both DB URLs, Better Auth secret, and pinned Node/Python versions. Startup derives `BETTER_AUTH_URL`, `FRONTEND_URL` and `CORS_ORIGINS` from `RENDER_EXTERNAL_URL` rather than the old web domain.

Retain existing Sandbox credentials and backend API keys in Render's environment. Check `AUTH_DATABASE_URL` and `DATABASE_URL` target the same database. Do **not** point the public `PORT` to FastAPI: that port is for Next.js. Back up staging data before changing the deployment. **Never run `db:reset` on Render**; migrations run in pre-deploy, and no seeding runs automatically.

## Verify before deleting the Free service

1. `https://<kadoku-api-domain>/api/health` must return OK for web and API.
2. Test login/logout, `/admin`, gift chat, and API proxy at the **unified domain**. Existing web-domain cookies will not transfer.
3. Test PayPal Sandbox approval and return URL using the unified domain; if configured, update the webhook URL to `/api/v1/webhooks/paypal` on that domain.
4. Inspect Render logs and RAM under concurrent usage. **512 MB may be insufficient** for Next.js + FastAPI + LiteLLM.

The old `kadoku-web` remains deployed but is **not a transparent live fallback** after the auth issuer changes.

## Rollback

Restore `kadoku-api` to `main`, rootDir `apps/api`, build `uv sync --frozen`, and start `uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Set `BETTER_AUTH_URL`, `FRONTEND_URL`, and `CORS_ORIGINS` back to the old web service origin, then redeploy. `kadoku-web` remains on `main` for the split architecture. Re-login may be required.
