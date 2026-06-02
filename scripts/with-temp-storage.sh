#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mianotes-test.XXXXXX")"

cleanup() {
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT INT TERM

export MIANOTES_DATA_DIR="$TEMP_ROOT/data"
export MIANOTES_DATABASE_URL="sqlite:///$MIANOTES_DATA_DIR/system.db"
export MIANOTES_STORAGE_CONFIG_PATH="$TEMP_ROOT/storage.json"

mkdir -p "$MIANOTES_DATA_DIR"

if [[ $# -eq 0 ]]; then
  set -- pytest
fi

echo "Using temporary Mianotes storage: $TEMP_ROOT"
cd "$ROOT_DIR"
"$@"
