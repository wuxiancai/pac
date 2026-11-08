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
if ! command -v ollama >/dev/null 2>&1; then
  printf 'Ollama is required for the local beta model. Install/start Ollama, then retry.\n' >&2
  exit 1
fi
if ! ollama list | awk 'NR > 1 { print $1 }' | grep -Fxq 'qwen3.5:0.8b'; then
  printf 'Required local model qwen3.5:0.8b is not installed in Ollama.\n' >&2
  exit 1
fi

"$SCRIPT_DIR/build_beta_app.sh"
open -n "$APP_DIR" \
  --env "PAC_POC_PYTHON=$PYTHON" \
  --env "PAC_POC_BACKEND=$BACKEND_DIR"
