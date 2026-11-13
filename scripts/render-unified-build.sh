#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# The repo root has no uv.lock (the Python project lives in apps/api).
# Render only auto-provisions uv when the service root contains uv.lock.
if ! command -v uv >/dev/null 2>&1; then
  python -m pip install --user --disable-pip-version-check "uv==0.13.7"
  export PATH="$(python -m site --user-base)/bin:$PATH"
fi

command -v node >/dev/null
command -v npm >/dev/null
command -v uv >/dev/null

(
  cd apps/api
  uv sync --frozen --no-dev
)

(
  cd apps/web
  npx --yes pnpm@10.15.0 install --frozen-lockfile
  npx --yes pnpm@10.15.0 build
)
