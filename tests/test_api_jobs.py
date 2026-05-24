from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base, Note, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.services.jobs import (
    MAX_JOB_LOG_ENTRIES,
    MAX_JOB_LOG_FIELD_LENGTH,
    append_job_log,
    cancel_job,
    create_job,
    decode_job_log,
    mark_job_failed,
    mark_job_succeeded,
)


@pytest.fixture
def app_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, sessionmaker[Session]], None, None]:
    get_settings.cache_clear()
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_session() -> Generator[Session, None, None]:
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client, testing_session
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_jobs_can_be_read_by_owner(app_client: tuple[TestClient, sessionmaker[Session]]):
    client, testing_session = app_client
    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    folder = client.post("/api/folders", json={"name": "Jobs"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={"folder_id": folder["id"], "text": "A note for Mia jobs."},
    ).json()

    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        stored_note = session.get(Note, note["id"])
        assert stored_note is not None
        job = create_job(
            session,
            user,
            job_type="parse_file",
            note_id=stored_note.id,
            input_payload={"note_id": stored_note.id},
        )
        append_job_log(job, command="MarkItDown.convert(original.pdf)", response="started")
        session.commit()
        job_id = job.id

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id
    assert listed.json()[0]["status"] == "queued"
    assert listed.json()[0]["input"] == {"note_id": note["id"]}
    assert listed.json()[0]["note_title"] == note["title"]
    assert listed.json()[0]["log"][0]["command"] == "MarkItDown.convert(original.pdf)"

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["job_type"] == "parse_file"


def test_job_status_helpers(app_client: tuple[TestClient, sessionmaker[Session]]):
    client, testing_session = app_client
    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        job = create_job(session, user, job_type="rewrite")
        append_job_log(job, command="running command", response="running response")
        mark_job_succeeded(job, {"message": "done"})
        assert job.status == "succeeded"
        assert job.result_json == '{"message": "done"}'
        assert decode_job_log(job.log_json) == []
        append_job_log(job, command="failed command", response="failed response")
        mark_job_failed(job, "boom")
        assert job.status == "failed"
        assert job.error == "boom"
        assert decode_job_log(job.log_json)[0]["command"] == "failed command"
        append_job_log(job, command="cancel command", response="cancel response")
        cancel_job(job)
        assert job.status == "cancelled"
        assert decode_job_log(job.log_json) == []


def test_job_logs_are_bounded(app_client: tuple[TestClient, sessionmaker[Session]]):
    client, testing_session = app_client
    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        job = create_job(session, user, job_type="parse_file")
        for index in range(MAX_JOB_LOG_ENTRIES + 8):
            append_job_log(
                job,
                command=f"command {index}",
                response="x" * (MAX_JOB_LOG_FIELD_LENGTH + 50),
            )

        log = decode_job_log(job.log_json)

    assert len(log) == MAX_JOB_LOG_ENTRIES
    assert log[0]["command"] == "command 8"
    assert len(log[-1]["response"]) == MAX_JOB_LOG_FIELD_LENGTH + 3
