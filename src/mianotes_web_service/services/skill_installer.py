from __future__ import annotations

import hashlib
import secrets
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from mianotes_web_service.db.models import ApiToken, SkillInstallCode, User
from mianotes_web_service.services.auth import create_api_token

INSTALL_CODE_HOURS = 1
DEFAULT_SKILL_CLIENT = "Codex"
DEFAULT_PERSONAL_TOKEN_NAME = "Mianotes API"
DEFAULT_PERSONAL_TOKEN_SCOPES = (
    "folders:read",
    "folders:write",
    "notes:read",
    "notes:write",
    "tags:read",
    "tags:write",
)


class SkillInstallError(ValueError):
    pass


def hash_install_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def normalize_api_url(api_url: str) -> str:
    parsed = urlparse(api_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SkillInstallError("Mianotes API URL must start with http:// or https://")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def create_skill_install_code(
    session: Session,
    *,
    user: User,
    api_url: str,
    client_name: str = DEFAULT_SKILL_CLIENT,
) -> tuple[SkillInstallCode, str]:
    raw_code = secrets.token_urlsafe(32)
    install_code = SkillInstallCode(
        user_id=user.id,
        code_hash=hash_install_code(raw_code),
        api_url=normalize_api_url(api_url),
        client_name=client_name.strip() or DEFAULT_SKILL_CLIENT,
        expires_at=datetime.now(UTC) + timedelta(hours=INSTALL_CODE_HOURS),
    )
    session.add(install_code)
    return install_code, raw_code


def skill_install_url(api_url: str, code: str) -> str:
    return f"{api_url.rstrip('/')}/install/skill.sh?{urlencode({'code': code})}"


def skill_install_command(api_url: str, code: str) -> str:
    return f"curl -fsSL {shlex.quote(skill_install_url(api_url, code))} | bash"


def read_skill_install_code(session: Session, raw_code: str) -> SkillInstallCode | None:
    return session.scalars(
        select(SkillInstallCode).where(SkillInstallCode.code_hash == hash_install_code(raw_code))
    ).one_or_none()


def redeem_skill_install_code(
    session: Session,
    *,
    raw_code: str,
) -> tuple[SkillInstallCode, str]:
    install_code = read_skill_install_code(session, raw_code)
    if install_code is None:
        raise SkillInstallError("Install code not found")
    if install_code.used_at is not None:
        raise SkillInstallError("Install code has already been used")

    expires_at = install_code.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise SkillInstallError("Install code has expired")

    _revoke_existing_default_tokens(session, install_code.user_id)
    token, raw_token = create_api_token(
        session,
        install_code.user,
        name=DEFAULT_PERSONAL_TOKEN_NAME,
        scopes=DEFAULT_PERSONAL_TOKEN_SCOPES,
    )
    install_code.used_at = datetime.now(UTC)
    session.flush()
    session.refresh(token)
    return install_code, raw_token


def _revoke_existing_default_tokens(session: Session, user_id: str) -> None:
    now = datetime.now(UTC)
    tokens = session.scalars(
        select(ApiToken).where(
            ApiToken.user_id == user_id,
            ApiToken.name == DEFAULT_PERSONAL_TOKEN_NAME,
            ApiToken.revoked_at.is_(None),
        )
    ).all()
    for token in tokens:
        token.revoked_at = now


def bundled_skill_text() -> str:
    source_root = Path(__file__).resolve().parents[3] / "skills" / "mianotes" / "SKILL.md"
    if source_root.exists():
        return source_root.read_text(encoding="utf-8")

    packaged = Path(__file__).resolve().parent.parent / "skills" / "mianotes" / "SKILL.md"
    return packaged.read_text(encoding="utf-8")


def render_skill_install_script(
    *,
    api_url: str,
    api_key: str,
    api_user: str,
    skill_text: str | None = None,
) -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "",
            'echo "Installing Mianotes agent skill..."',
            "",
            'MIANOTES_DIR="${HOME}/.mianotes"',
            'MIANOTES_ENV_FILE="${MIANOTES_DIR}/env"',
            'mkdir -p "${MIANOTES_DIR}"',
            "",
            'cat > "${MIANOTES_ENV_FILE}" <<\'__MIANOTES_ENV__\'',
            f"export MIANOTES_API_URL={shlex.quote(api_url)}",
            f"export MIANOTES_API_KEY={shlex.quote(api_key)}",
            f"export MIANOTES_API_USER={shlex.quote(api_user)}",
            "__MIANOTES_ENV__",
            'chmod 600 "${MIANOTES_ENV_FILE}"',
            "",
            'install_skill() {',
            '  target="$1"',
            '  mkdir -p "$(dirname "${target}")"',
            "  cat > \"${target}\" <<'__MIANOTES_SKILL_MD__'",
            skill_text if skill_text is not None else bundled_skill_text(),
            "__MIANOTES_SKILL_MD__",
            "}",
            "",
            'install_skill "${HOME}/.codex/skills/mianotes/SKILL.md"',
            'install_skill "${HOME}/.claude/skills/mianotes/SKILL.md"',
            "",
            'PROFILE_FILE="${HOME}/.profile"',
            'case "${SHELL##*/}" in',
            '  zsh) PROFILE_FILE="${HOME}/.zshrc" ;;',
            '  bash) PROFILE_FILE="${HOME}/.bashrc" ;;',
            "esac",
            'touch "${PROFILE_FILE}"',
            'TMP_PROFILE="$(mktemp)"',
            "awk '",
            "  /^# >>> Mianotes agent environment >>>$/ { skip = 1; next }",
            "  /^# <<< Mianotes agent environment <<<$/{ skip = 0; next }",
            "  skip != 1 { print }",
            "' \"${PROFILE_FILE}\" > \"${TMP_PROFILE}\"",
            'cat >> "${TMP_PROFILE}" <<\'__MIANOTES_PROFILE__\'',
            "# >>> Mianotes agent environment >>>",
            '[ -f "${HOME}/.mianotes/env" ] && . "${HOME}/.mianotes/env"',
            "# <<< Mianotes agent environment <<<",
            "__MIANOTES_PROFILE__",
            'mv "${TMP_PROFILE}" "${PROFILE_FILE}"',
            "",
            'echo "Mianotes skill installed for Codex and Claude."',
            'echo "Open a new terminal session so MIANOTES_API_URL and MIANOTES_API_KEY are available."',
            "",
        ]
    )
