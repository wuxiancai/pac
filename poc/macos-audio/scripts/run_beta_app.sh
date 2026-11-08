#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BACKEND_DIR="$REPO_ROOT/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"
APP_DIR="$REPO_ROOT/.poc-data/personal-assistant-beta.app"

if [ ! -x "$PYTHON" ]; then
  printf 'Missing local Python runtime: %s\n' "$PYTHON" >&2
  printf 'Create the backend environment with: cd %s && uv sync --locked\n' "$BACKEND_DIR" >&2
  exit 1
fi
"$SCRIPT_DIR/build_beta_app.sh"
open -n "$APP_DIR" \
  --env "PAC_POC_PYTHON=$PYTHON" \
  --env "PAC_POC_BACKEND=$BACKEND_DIR"
