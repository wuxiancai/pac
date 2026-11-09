#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)
BACKEND_DIR="$REPO_ROOT/backend"
PYTHON="$BACKEND_DIR/.venv/bin/python"
APP_DIR="$REPO_ROOT/.poc-data/personal-assistant-beta.app"
APP_EXECUTABLE_PATH="$APP_DIR/Contents/MacOS/personal-assistant-beta"

RUNNING_PID=$(ps -Ao pid=,command= | awk -v executable="$APP_EXECUTABLE_PATH" '$2 == executable { print $1; exit }')
if [ -n "$RUNNING_PID" ]; then
  printf 'The beta app is already running (PID %s).\n' "$RUNNING_PID" >&2
  printf 'To load the latest build, preserve any unsaved chat, quit the app, then run this script again.\n' >&2
  exit 1
fi

if [ ! -x "$PYTHON" ]; then
  printf 'Missing local Python runtime: %s\n' "$PYTHON" >&2
  printf 'Create the backend environment with: cd %s && uv sync --locked\n' "$BACKEND_DIR" >&2
  exit 1
fi
"$SCRIPT_DIR/build_beta_app.sh"
open -n "$APP_DIR" \
  --env "PAC_POC_PYTHON=$PYTHON" \
  --env "PAC_POC_BACKEND=$BACKEND_DIR"
