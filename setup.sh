#!/bin/bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT_DIR/src"

clone_if_missing() {
  local url="$1"
  local name="$2"

  if [ -d "$ROOT_DIR/src/$name" ]; then
    echo "[SKIP] src/$name already exists"
  else
    echo "[CLONE] $url -> src/$name"
    git clone --depth 1 "$url" "$ROOT_DIR/src/$name"
  fi
}

clone_if_missing https://gitlab.com/libtiff/libtiff libtiff

echo "Dependencies ready."
