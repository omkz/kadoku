#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Migrate before the new release serves requests, not on every startup.
(
  cd apps/api
  .venv/bin/alembic upgrade head
)

(
  cd apps/web
  npx --yes auth@latest migrate --yes --config ./lib/auth.ts
)
