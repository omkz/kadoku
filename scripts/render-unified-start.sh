#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

: "${DATABASE_URL:?DATABASE_URL must be configured}"
: "${AUTH_DATABASE_URL:?AUTH_DATABASE_URL must be configured}"
: "${GUEST_QUOTA_SECRET:?GUEST_QUOTA_SECRET must be configured}"
: "${BETTER_AUTH_SECRET:?BETTER_AUTH_SECRET must be configured}"
: "${PORT:=10000}"

# Render's public URL is authoritative for staging auth and PayPal redirects.
if [[ -n "${RENDER_EXTERNAL_URL:-}" ]]; then
  export BETTER_AUTH_URL="$RENDER_EXTERNAL_URL"
  export FRONTEND_URL="$RENDER_EXTERNAL_URL"
  export CORS_ORIGINS="$RENDER_EXTERNAL_URL"
else
  : "${BETTER_AUTH_URL:=http://localhost:${PORT}}"
  : "${FRONTEND_URL:=$BETTER_AUTH_URL}"
  : "${CORS_ORIGINS:=$BETTER_AUTH_URL}"
fi
export BETTER_AUTH_URL FRONTEND_URL CORS_ORIGINS

# Both services sign/verify the same guest quota cookie.
export GUEST_COOKIE_SECRET="$GUEST_QUOTA_SECRET"
export API_PROXY_TARGET="http://127.0.0.1:8000"

api_pid=""
web_pid=""
cleanup() {
  trap - EXIT
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
  [[ -z "$api_pid" ]] || wait "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || wait "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

(
  cd apps/api
  exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
) &
api_pid="$!"

(
  cd apps/web
  exec node ./node_modules/next/dist/bin/next start --hostname 0.0.0.0 --port "$PORT"
) &
web_pid="$!"

# Fail the service if either process exits; never serve a half-working app.
set +e
wait -n "$api_pid" "$web_pid"
status="$?"
set -e
echo "Unified service process exited (status $status); shutting down."
exit 1
