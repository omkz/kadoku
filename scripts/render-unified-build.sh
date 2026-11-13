#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# The repo root has no uv.lock (the Python project lives in apps/api).
# Render only auto-provisions uv when the service root contains uv.lock.
# Render exposes a uv wrapper even when uv itself was not provisioned.
# Check executable functionality, not just command -v.
if ! uv --version >/dev/null 2>&1; then
  echo "uv is unavailable; installing a pinned version for the monorepo build"
  python -m pip install --user --disable-pip-version-check "uv==0.13.7"
  # Put the installed binary ahead of Render's nonfunctional wrapper.
  export PATH="$(python -m site --user-base)/bin:$PATH"
  hash -r
fi

uv --version
command -v node >/dev/null
command -v npm >/dev/null

(
  cd apps/api
  uv sync --frozen --no-dev
)

(
  cd apps/web
  npx --yes pnpm@10.15.0 install --frozen-lockfile
  npx --yes pnpm@10.15.0 build
)
