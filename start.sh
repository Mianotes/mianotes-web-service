#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
HOST="${MIANOTES_HOST:-0.0.0.0}"
PORT="${MIANOTES_PORT:-8200}"

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    echo "$PYTHON"
    return
  fi

  for candidate in python3 /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      command -v "$candidate"
      return
    fi
  done

  echo "Python 3.11 or newer is required. Install it with Homebrew or your package manager." >&2
  exit 1
}

PYTHON_BIN="$(find_python)"

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
. "$VENV_DIR/bin/activate"

"$ROOT_DIR/install.sh"
mianotes-web-service init-db
mianotes-web-service --host "$HOST" --port "$PORT"
