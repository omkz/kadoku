# Unified Render staging — keep hackathon URL

Goal: serve **Next.js + FastAPI** from the existing `kadoku-web.onrender.com` service using one native Python Starter. No Docker, no new service, no database migration. PostgreSQL stays Free for now.

## Before merging

- On the **existing Blueprint** currently managing `kadoku-api`, turn **Auto Sync = No**. A Git push can otherwise sync infrastructure immediately.
- Confirm `kadoku-web` is **not already managed by a different Blueprint**. A Render resource must belong to at most one Blueprint.
- Keep `kadoku-api` Starter running until the replacement web service is confirmed healthy; brief double billing is prorated.

## Cutover

1. Merge the deployment PR into `staging`. Open the **existing Blueprint** and choose **Manual Sync** (do **not** create a second Blueprint).
2. Review the proposed changes: the **existing `kadoku-web`** must change from Node/Free to Python/Starter using the monorepo-root build, pre-deploy, start scripts and `/api/health`. **Do not proceed** if the preview proposes a new web service, a suffixed name, a database or the wrong workspace.
3. `kadoku-api` is removed from the Blueprint file, **not automatically deleted** by Render. Leave it active during verification.
4. In `kadoku-web` → Environment, ensure both database URLs refer to the existing `kadoku-db` PostgreSQL instance. Keep the **existing web `BETTER_AUTH_SECRET`** to preserve auth data and sessions.
5. Copy backend settings from `kadoku-api` into `kadoku-web` via Render Environment (never Git): `GUEST_QUOTA_SECRET`, `AI_MODEL`, the actually-used Gemini/Google/OpenAI key, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, and `PAYPAL_WEBHOOK_ID` if configured. Optional backend flags such as `STUDIO_AGENT_ENABLED` should be copied only if needed. If placeholders with `sync: false` do not prompt during an existing Blueprint sync, populate them manually in Environment.
6. Start or repeat the unified deploy on the web service. Its public URL should remain `https://kadoku-web.onrender.com/`. The start script automatically uses that URL as `BETTER_AUTH_URL`, `FRONTEND_URL` and `CORS_ORIGINS`.

## Verify before retiring old API

- `https://kadoku-web.onrender.com/api/health` returns `{"status":"ok","web":"ok","api":"ok"}`.
- Login, admin, AI gift recommendations, PayPal Sandbox checkout and configured webhook all function.
- RAM usage and logs are stable on Starter 512 MB; no restarts.
- Verify the original hackathon URL still opens the correct demo.

Only after successful tests, **delete or downgrade the old `kadoku-api`** to stop its Starter billing. First verify the current Blueprint no longer lists it, or a later sync might recreate it. The Free `kadoku-db` still expires under Render's Free database policy.

## Rollback

If the web deployment fails, keep `kadoku-api` intact (its previously deployed unified version remains the reference). Restore the old `kadoku-web` Node/Free configuration and branch `main` using the previous settings, or reverse this Blueprint change, and redeploy. Existing users may need to sign in again after domain or secret changes. Do **not** run `db:reset`, change database data, or put credentials into Git.
