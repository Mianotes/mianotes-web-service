#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${MIANOTES_ENV_FILE:-$APP_ROOT/.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck source=/dev/null
  . "$ENV_FILE"
  set +a
fi

export MIANOTES_API_URL="${MIANOTES_API_URL:-http://127.0.0.1:8200}"
export MIANOTES_ENV_FILE="${MIANOTES_ENV_FILE:-$ENV_FILE}"
export MIANOTES_CLIENT_NAME="${MIANOTES_CLIENT_NAME:-MCP}"

exec "$APP_ROOT/.venv/bin/mianotes-mcp"
