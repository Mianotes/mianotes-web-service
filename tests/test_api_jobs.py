from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
    listed_job = listed.json()["items"][0]
    assert listed_job["id"] == job_id
    assert listed_job["status"] == "queued"
    assert listed_job["input"] is None
    assert listed_job["result"] is None
    assert listed_job["log"] is None
    assert listed_job["note_title"] == note["title"]

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["job_type"] == "parse_file"
    assert fetched.json()["input"] == {"note_id": note["id"]}
    assert fetched.json()["log"][0]["command"] == "MarkItDown.convert(original.pdf)"


def test_jobs_list_keeps_active_failed_and_recent_succeeded_jobs(
    app_client: tuple[TestClient, sessionmaker[Session]],
):
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
    now = datetime.now(UTC)

    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        queued = create_job(session, user, job_type="parse_file")
        running = create_job(session, user, job_type="parse_file")
        running.status = "running"
        failed = create_job(session, user, job_type="parse_file")
        failed.status = "failed"
        failed.finished_at = now - timedelta(days=14)
        recent_succeeded = create_job(session, user, job_type="parse_file")
        recent_succeeded.status = "succeeded"
        recent_succeeded.finished_at = now - timedelta(hours=23, minutes=30)
        old_succeeded = create_job(session, user, job_type="parse_file")
        old_succeeded.status = "succeeded"
        old_succeeded.finished_at = now - timedelta(days=2)
        cancelled = create_job(session, user, job_type="parse_file")
        cancelled.status = "cancelled"
        cancelled.finished_at = now
        session.commit()
        visible_ids = {queued.id, running.id, failed.id, recent_succeeded.id}
        hidden_ids = {old_succeeded.id, cancelled.id}

    listed = client.get("/api/jobs")

    assert listed.status_code == 200
    listed_ids = {job["id"] for job in listed.json()["items"]}
    assert visible_ids <= listed_ids
    assert hidden_ids.isdisjoint(listed_ids)


def test_jobs_status_filter_keeps_retention_window(
    app_client: tuple[TestClient, sessionmaker[Session]],
):
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
    now = datetime.now(UTC)

    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        recent_succeeded = create_job(session, user, job_type="parse_file")
        recent_succeeded.status = "succeeded"
        recent_succeeded.finished_at = now - timedelta(hours=1)
        old_succeeded = create_job(session, user, job_type="parse_file")
        old_succeeded.status = "succeeded"
        old_succeeded.finished_at = now - timedelta(days=2)
        failed = create_job(session, user, job_type="parse_file")
        failed.status = "failed"
        session.commit()
        recent_succeeded_id = recent_succeeded.id
        old_succeeded_id = old_succeeded.id
        failed_id = failed.id

    listed = client.get("/api/jobs", params={"status": "succeeded"})

    assert listed.status_code == 200
    listed_ids = {job["id"] for job in listed.json()["items"]}
    assert recent_succeeded_id in listed_ids
    assert old_succeeded_id not in listed_ids
    assert failed_id not in listed_ids


def test_jobs_list_is_paginated(app_client: tuple[TestClient, sessionmaker[Session]]):
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
        for index in range(6):
            job = create_job(session, user, job_type="parse_file")
            job.created_at = datetime(2026, 1, 1, 12, index, tzinfo=UTC)
        session.commit()

    first_page = client.get("/api/jobs", params={"limit": 3})

    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert len(first_payload["items"]) == 3
    assert first_payload["next_cursor"] is not None

    second_page = client.get(
        "/api/jobs",
        params={"limit": 3, "cursor": first_payload["next_cursor"]},
    )

    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert len(second_payload["items"]) == 3
    assert second_payload["next_cursor"] is None
    assert {
        item["id"] for item in first_payload["items"]
    }.isdisjoint({item["id"] for item in second_payload["items"]})


def test_jobs_list_payload_decoding_is_opt_in(
    app_client: tuple[TestClient, sessionmaker[Session]],
):
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
        job = create_job(
            session,
            user,
            job_type="parse_file",
            input_payload={"source": "upload"},
        )
        append_job_log(job, command="MarkItDown.convert(original.pdf)", response="started")
        mark_job_succeeded(job, {"ok": True})
        job.log_json = (
            """[{"timestamp":"2026-01-01T12:00:00+00:00","status":"info","command":"kept"}]"""
        )
        session.commit()
        job_id = job.id

    default_list = client.get("/api/jobs", params={"status": "succeeded"})
    assert default_list.status_code == 200
    default_job = default_list.json()["items"][0]
    assert default_job["id"] == job_id
    assert default_job["input"] is None
    assert default_job["result"] is None
    assert default_job["log"] is None

    verbose_list = client.get(
        "/api/jobs",
        params={"status": "succeeded", "include_logs": "true", "include_payloads": "true"},
    )
    assert verbose_list.status_code == 200
    verbose_job = verbose_list.json()["items"][0]
    assert verbose_job["input"] == {"source": "upload"}
    assert verbose_job["result"] == {"ok": True}
    assert verbose_job["log"][0]["command"] == "kept"


def test_jobs_list_rejects_invalid_cursor(app_client: tuple[TestClient, sessionmaker[Session]]):
    client, _testing_session = app_client
    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )

    listed = client.get("/api/jobs", params={"cursor": "not-a-cursor"})

    assert listed.status_code == 422
    assert listed.json()["detail"] == "Invalid jobs cursor"


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
        succeeded_log = decode_job_log(job.log_json)
        assert succeeded_log[0]["command"] == "running command"
        append_job_log(job, command="failed command", response="failed response")
        mark_job_failed(job, "boom")
        assert job.status == "failed"
        assert job.error == "boom"
        failed_log = decode_job_log(job.log_json)
        assert failed_log[0]["command"] == "running command"
        assert failed_log[1]["command"] == "failed command"
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
