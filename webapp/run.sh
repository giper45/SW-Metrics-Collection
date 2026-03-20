#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/venv/bin/activate"
fi

if [[ -z "${ENV_PWD:-}" ]]; then
    echo "ENV_PWD is required. Example: ENV_PWD='choose-a-strong-password' bash webapp/run.sh" >&2
    exit 1
fi

HOST="${MAVIS_WEB_HOST:-${MARS_WEB_HOST:-127.0.0.1}}"
PORT="${MAVIS_WEB_PORT:-${MARS_WEB_PORT:-9999}}"

cd "$PROJECT_ROOT"

exec python3 -m flask \
    --app webapp:create_app \
    run \
    --debug \
    --host "$HOST" \
    --port "$PORT"
