#!/bin/sh
set -eu

DOCKERD_LOG=/tmp/dockerd.log
dockerd-entrypoint.sh >"$DOCKERD_LOG" 2>&1 &
daemon_pid=$!

cleanup() {
    kill "$daemon_pid" >/dev/null 2>&1 || true
}

trap cleanup INT TERM EXIT

attempt=0
until docker info >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "Docker daemon did not become ready." >&2
        cat "$DOCKERD_LOG" >&2 || true
        exit 1
    fi
    sleep 1
done

exec python3 -m webapp
