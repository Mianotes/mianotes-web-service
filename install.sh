#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
INSTALL_PACKAGE=1
INSTALL_DEV=0
INSTALL_SKILLS=1

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Options:
  --dev             Install Python development dependencies.
  --skip-package    Do not install the Python package.
  --skip-skills     Do not install Codex/Claude skills.
  -h, --help        Show this help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)
      INSTALL_DEV=1
      ;;
    --skip-package)
      INSTALL_PACKAGE=0
      ;;
    --skip-skills)
      INSTALL_SKILLS=0
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

if [[ "$INSTALL_PACKAGE" -eq 1 ]]; then
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

if [[ "$INSTALL_SKILLS" -eq 1 ]]; then
  if [[ -z "${HOME:-}" ]]; then
    echo "HOME is not set; cannot install agent skills." >&2
    exit 1
  fi

  install_skill "${CODEX_HOME:-$HOME/.codex}/skills/mianotes"
  install_skill "${CLAUDE_HOME:-$HOME/.claude}/skills/mianotes"
fi

cat <<'NEXT'

Mianotes web service installed.

Next:
  mianotes-web-service init-db
  mianotes-web-service --host 0.0.0.0 --port 8200
NEXT
