#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DEV=0
MODE="default"

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    echo "$PYTHON"
    return
  fi

  for candidate in python3 python /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
      command -v "$candidate"
      return
    fi
  done

  echo "Python 3.11 or newer is required. Install it with Homebrew or your package manager." >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --dev          Install development dependencies too.
  --skills-only  Only install the Codex/Claude skills.
  -h, --help     Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)
      INSTALL_DEV=1
      ;;
    --skills-only)
      MODE="skills-only"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$MODE" != "skills-only" ]]; then
  PYTHON_BIN="$(find_python)"
  if [[ "$INSTALL_DEV" -eq 1 ]]; then
    "$PYTHON_BIN" -m pip install -e "${ROOT_DIR}[dev]"
  else
    "$PYTHON_BIN" -m pip install -e "$ROOT_DIR"
  fi
fi

install_skill() {
  local target_dir="$1"
  mkdir -p "$target_dir"
  cp "$ROOT_DIR/skills/mianotes/SKILL.md" "$target_dir/SKILL.md"
  echo "Installed Mianotes skill: $target_dir/SKILL.md"
}

if [[ -z "${HOME:-}" ]]; then
  echo "HOME is not set; cannot install agent skills." >&2
  exit 1
fi

install_skill "${CODEX_HOME:-$HOME/.codex}/skills/mianotes"
install_skill "${CLAUDE_HOME:-$HOME/.claude}/skills/mianotes"

if [[ "$MODE" == "skills-only" ]]; then
  cat <<'NEXT'

Mianotes agent skills installed.
NEXT
else
  cat <<'NEXT'

Mianotes web service installed.

Next:
  mianotes-web-service init-db
  mianotes-web-service --host 0.0.0.0 --port 8200
NEXT
fi
