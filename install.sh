#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${MIANOTES_VENV_DIR:-$ROOT_DIR/.venv}"
INSTALL_DEV=0
MODE="default"

find_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    if "$PYTHON" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))' >/dev/null 2>&1; then
      echo "$PYTHON"
      return
    fi
    echo "PYTHON must point to Python 3.11, 3.12, or 3.13." >&2
    exit 1
  fi

  for candidate in \
    python3.12 \
    python3.11 \
    python3.13 \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3.13 \
    /usr/local/bin/python3.12 \
    /usr/local/bin/python3.11 \
    /usr/local/bin/python3.13 \
    python3 \
    python \
    /usr/bin/python3
  do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; raise SystemExit(not ((3, 11) <= sys.version_info < (3, 14)))' >/dev/null 2>&1; then
      command -v "$candidate"
      return
    fi
  done

  echo "Python 3.11, 3.12, or 3.13 is required. Install it with Homebrew or your package manager." >&2
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
  if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
  fi
  VENV_PYTHON="$VENV_DIR/bin/python"
  if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "Could not find Python in virtual environment: $VENV_PYTHON" >&2
    exit 1
  fi
  if [[ "$INSTALL_DEV" -eq 1 ]]; then
    "$VENV_PYTHON" -m pip install -e "${ROOT_DIR}[dev]"
  else
    "$VENV_PYTHON" -m pip install -e "$ROOT_DIR"
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
  source "$VENV_DIR/bin/activate"
  mianotes-web-service init-db
  mianotes-web-service --host 0.0.0.0 --port 8200
NEXT
fi
