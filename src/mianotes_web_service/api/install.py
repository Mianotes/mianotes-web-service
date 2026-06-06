from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from mianotes_web_service.api.dependencies import CurrentUser, SystemSessionDep
from mianotes_web_service.domain.schemas import SkillInstallCreate, SkillInstallRead
from mianotes_web_service.services.skill_installer import (
    SkillInstallError,
    create_skill_install_code,
    read_redeemable_skill_install_code,
    redeem_skill_install_code,
    render_skill_env_file,
    render_skill_install_script,
    skill_install_command,
    skill_install_url,
)

router = APIRouter(tags=["install"])


@router.post(
    "/api/install/skill",
    response_model=SkillInstallRead,
    status_code=status.HTTP_201_CREATED,
)
def create_skill_install(
    payload: SkillInstallCreate,
    session: SystemSessionDep,
    user: CurrentUser,
) -> SkillInstallRead:
    try:
        install_code, raw_code = create_skill_install_code(
            session,
            user=user,
            api_url=payload.api_url,
        )
    except SkillInstallError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    session.commit()
    api_url = install_code.api_url
    return SkillInstallRead(
        install_url=skill_install_url(api_url, raw_code),
        command=skill_install_command(api_url, raw_code),
        expires_at=install_code.expires_at,
    )


@router.get("/skill/install.sh", response_class=PlainTextResponse)
def download_skill_install_script(
    session: SystemSessionDep,
    code: str = Query(min_length=1),
) -> PlainTextResponse:
    try:
        install_code = read_redeemable_skill_install_code(session, raw_code=code)
    except SkillInstallError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    script = render_skill_install_script(
        install_base_url=install_code.api_url,
        install_code=code,
    )
    return PlainTextResponse(script, media_type="text/x-shellscript")


@router.get("/install/skill.sh", response_class=PlainTextResponse, include_in_schema=False)
def download_alternate_skill_install_script(
    session: SystemSessionDep,
    code: str = Query(min_length=1),
) -> PlainTextResponse:
    return download_skill_install_script(session=session, code=code)


@router.get("/skill/install.env", response_class=PlainTextResponse, include_in_schema=False)
def download_skill_install_env(
    session: SystemSessionDep,
    code: str = Query(min_length=1),
) -> PlainTextResponse:
    try:
        install_code, raw_token = redeem_skill_install_code(session, raw_code=code)
    except SkillInstallError as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc

    env_file = render_skill_env_file(
        api_url=install_code.api_url,
        api_key=raw_token,
        api_user=install_code.user.email,
    )
    session.commit()
    return PlainTextResponse(env_file, media_type="text/plain")
