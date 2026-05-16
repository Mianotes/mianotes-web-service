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
from mianotes_web_service.services.jobs import create_job, mark_job_failed, mark_job_succeeded


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
    project = client.post("/api/projects", json={"name": "Jobs"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={"project_id": project["id"], "text": "A note for Mia jobs."},
    ).json()

    with testing_session() as session:
        user = session.scalars(select(User).where(User.email == "admin@example.com")).one()
        stored_note = session.get(Note, note["id"])
        assert stored_note is not None
        job = create_job(
            session,
            user,
            job_type="summarise",
            note_id=stored_note.id,
            input_payload={"note_id": stored_note.id},
        )
        session.commit()
        job_id = job.id

    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == job_id
    assert listed.json()[0]["status"] == "queued"
    assert listed.json()[0]["input"] == {"note_id": note["id"]}

    fetched = client.get(f"/api/jobs/{job_id}")
    assert fetched.status_code == 200
    assert fetched.json()["job_type"] == "summarise"


def test_mia_operation_stubs_create_queued_jobs(
    app_client: tuple[TestClient, sessionmaker[Session]],
):
    client, _ = app_client
    client.post(
        "/api/auth/join",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "house-password",
            "password_confirmation": "house-password",
        },
    )
    project = client.post("/api/projects", json={"name": "Mia"}).json()
    note = client.post(
        "/api/notes/from-text",
        json={"project_id": project["id"], "text": "Mia should improve this note."},
    ).json()

    for operation in ["summarise", "structure", "extract", "rewrite"]:
        created = client.post(f"/api/notes/{note['id']}/{operation}")
        assert created.status_code == 202
        body = created.json()
        assert body["job_type"] == operation
        assert body["status"] == "queued"
        assert body["note_id"] == note["id"]
        assert body["input"] == {"note_id": note["id"], "operation": operation}


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
        mark_job_succeeded(job, {"message": "done"})
        assert job.status == "succeeded"
        assert job.result_json == '{"message": "done"}'
        mark_job_failed(job, "boom")
        assert job.status == "failed"
        assert job.error == "boom"
