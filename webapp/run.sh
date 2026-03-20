#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

usage() {
    cat <<'EOF'
Usage: bash webapp/run.sh [--port PORT]

Options:
  -p, --port PORT   Override the Flask development port.
  -h, --help        Show this help message.
EOF
}

if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/venv/bin/activate"
fi

PORT_OVERRIDE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port)
            if [[ $# -lt 2 ]]; then
                echo "Missing value for $1" >&2
                usage >&2
                exit 1
            fi
            PORT_OVERRIDE="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "${ENV_PWD:-}" ]]; then
    echo "ENV_PWD is required. Example: ENV_PWD='choose-a-strong-password' bash webapp/run.sh --port 5001" >&2
    exit 1
fi

HOST="${MAVIS_WEB_HOST:-${MARS_WEB_HOST:-127.0.0.1}}"
PORT="${MAVIS_WEB_PORT:-${MARS_WEB_PORT:-9999}}"
if [[ -n "$PORT_OVERRIDE" ]]; then
    PORT="$PORT_OVERRIDE"
fi

cd "$PROJECT_ROOT"

exec python3 -m flask \
    --app webapp:create_app \
    run \
    --debug \
    --host "$HOST" \
    --port "$PORT"
