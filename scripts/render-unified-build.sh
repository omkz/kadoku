#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# The repo root has no uv.lock (the Python project lives in apps/api).
# Render only auto-provisions uv when the service root contains uv.lock.
# Render may expose a uv wrapper without a working uv executable.
# Its Python runtime uses a virtualenv, so do not use pip's --user flag.
if ! python -m uv --version >/dev/null 2>&1; then
  echo "Installing uv into the active Python environment"
  python -m pip install --disable-pip-version-check "uv==0.13.7"
fi

# Bypass Render's uv wrapper and invoke the installed Python module directly.
python -m uv --version
command -v node >/dev/null
command -v npm >/dev/null

(
  cd apps/api
  python -m uv sync --frozen --no-dev
)

(
  cd apps/web
  npx --yes pnpm@10.15.0 install --frozen-lockfile
  npx --yes pnpm@10.15.0 build
)
