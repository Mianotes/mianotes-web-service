from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base, Note
from mianotes_web_service.db.session import get_session


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
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
    app.state.testing_session = testing_session
    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def _join(client: TestClient) -> dict:
    return client.post(
        "/api/auth/join",
        json={
            "email": "publisher@example.com",
            "name": "Publisher",
            "password": "mianotes",
            "password_confirmation": "mianotes",
        },
    ).json()["user"]


def _create_note(client: TestClient, folder_id: str, title: str, text: str) -> dict:
    response = client.post(
        "/api/notes/from-text",
        json={
            "folder_id": folder_id,
            "title": title,
            "text": text,
            "tags": ["Docs"],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_publish_themes_are_listed(client: TestClient):
    _join(client)

    response = client.get("/api/publish/themes")

    assert response.status_code == 200
    theme_ids = {theme["id"] for theme in response.json()}
    assert {"mianotes", "minimal"}.issubset(theme_ids)


def test_publish_draft_returns_editable_blocks(client: TestClient):
    _join(client)
    folder = client.post("/api/folders", json={"name": "About MCP"}).json()
    note = _create_note(
        client,
        folder["id"],
        "Architecture",
        "Mianotes publishes Markdown notes into static HTML.",
    )

    response = client.get("/api/publish/draft", params={"folder_id": folder["id"]})

    assert response.status_code == 200
    draft = response.json()
    assert draft["theme"] == "mianotes"
    assert draft["folder_id"] == folder["id"]
    assert draft["tag_id"] is None
    assert draft["site_configuration"]["brand"] == "mianotes"
    assert draft["site_configuration"]["headerLinks"] == [
        {"title": "GitHub", "url": "https://github.com/Mianotes"},
        {"title": "Contact", "url": "mailto:mianotes@proton.me"},
    ]
    assert draft["site_configuration"]["footerHtml"] == "Copyright © Your Name Here."
    assert draft["navigation"] == [
        {
            "title": "About MCP",
            "items": [
                {
                    "title": "Architecture",
                    "path": f"architecture-{note['id'][:8]}.html",
                }
            ],
        }
    ]
    assert draft["updated_notes"] == []


def test_publish_site_writes_html_markdown_assets_and_records(client: TestClient, tmp_path: Path):
    _join(client)
    folder = client.post("/api/folders", json={"name": "About MCP"}).json()
    note = _create_note(
        client,
        folder["id"],
        "Clients",
        "# Clients\n\nMCP clients connect agents to local tools.",
    )
    note_path = f"clients-{note['id'][:8]}.html"
    payload = {
        "folder_id": folder["id"],
        "theme": "mianotes",
        "site_configuration": {
            "brand": "Mia Docs",
            "version": "0.1.1",
            "headerLinks": [{"title": "GitHub", "url": "https://github.com/Mianotes"}],
            "footerHtml": "Copyright © Test.",
        },
        "navigation": [{"title": "About MCP", "items": [{"title": "Clients", "path": note_path}]}],
        "updated_notes": [{"title": "Clients", "path": note_path}],
    }

    response = client.post("/api/publish", json=payload)

    assert response.status_code == 201
    published = response.json()
    assert published["theme"] == "mianotes"
    assert published["version"] == "0.1.1"
    assert published["folder_id"] == folder["id"]
    assert published["tag_id"] is None
    assert published["note_count"] == 1
    assert published["html_path"] == "html/0.1.1"
    assert published["markdown_path"] == ""
    assert published["url_path"] == "html/0.1.1/index.html"
    assert published["site_url"].endswith("/html/0.1.1/index.html")

    html_root = tmp_path / "data" / "html" / "0.1.1"
    assert (html_root / "index.html").is_file()
    assert (html_root / "styles.css").is_file()
    assert (html_root / "site.js").is_file()
    assert (html_root / "search.js").is_file()
    assert (tmp_path / "data" / "html" / "navigation.js").is_file()
    assert (html_root / note_path).read_text(encoding="utf-8").find("styles.css") > -1
    assert (tmp_path / "data" / "markdown" / "about-mcp").is_dir()

    listed_note = client.get(f"/api/notes/{note['id']}").json()
    assert listed_note["is_published"] is True
    assert listed_note["published_at"] is not None

    published_file = client.get("/html/0.1.1/index.html")
    assert published_file.status_code == 200
    note_file = client.get(f"/html/0.1.1/{note_path}")
    assert note_file.status_code == 200
    assert "Mia Docs" in note_file.text
    assert "MCP clients" in note_file.text
    assert "https://github.com/Mianotes" in (html_root / "site.js").read_text(encoding="utf-8")

    next_draft = client.get("/api/publish/draft", params={"folder_id": folder["id"]}).json()
    assert next_draft["site_configuration"]["brand"] == "Mia Docs"
    assert next_draft["navigation"] == payload["navigation"]
    assert next_draft["updated_notes"] == []


def test_publish_draft_reuses_saved_navigation_and_stages_later_updates(client: TestClient):
    _join(client)
    folder = client.post("/api/folders", json={"name": "Publish staging"}).json()
    first_note = _create_note(
        client,
        folder["id"],
        "Architecture",
        "Architecture notes.",
    )
    first_path = f"architecture-{first_note['id'][:8]}.html"
    saved_navigation = [
        {
            "title": "Publish staging",
            "items": [
                {
                    "title": "Architecture",
                    "path": first_path,
                }
            ],
        }
    ]
    published_at = datetime.now(UTC) - timedelta(hours=1)

    with client.app.state.testing_session() as session:
        stored = session.get(Note, first_note["id"])
        assert stored is not None
        stored.updated_at = published_at
        session.commit()

    publish_response = client.post(
        "/api/publish",
        json={
            "folder_id": folder["id"],
            "theme": "mianotes",
            "site_configuration": {
                "brand": "mianotes",
                "version": "0.1.0",
                "headerLinks": [],
                "footerHtml": "Copyright © Test.",
            },
            "navigation": saved_navigation,
            "updated_notes": [],
        },
    )
    assert publish_response.status_code == 201

    second_note = _create_note(
        client,
        folder["id"],
        "Settings page",
        "New settings page notes.",
    )
    second_path = f"settings-page-{second_note['id'][:8]}.html"

    next_draft = client.get("/api/publish/draft", params={"folder_id": folder["id"]}).json()

    assert next_draft["navigation"] == saved_navigation
    assert next_draft["updated_notes"] == [
        {
            "title": "Settings page",
            "path": second_path,
        }
    ]


def test_all_folders_draft_stages_notes_missing_from_saved_navigation(client: TestClient):
    _join(client)
    improvements_folder = client.post("/api/folders", json={"name": "Improvements"}).json()
    mianotes_folder = next(
        folder for folder in client.get("/api/folders").json() if folder["name"] == "Mianotes"
    )
    improvements_note = _create_note(
        client,
        improvements_folder["id"],
        "Improvements",
        "Improvement notes.",
    )
    mianotes_note = _create_note(
        client,
        mianotes_folder["id"],
        "How to use Mianotes",
        "Mianotes notes.",
    )
    improvements_path = f"improvements/improvements-{improvements_note['id'][:8]}.html"
    mianotes_path = f"mianotes/how-to-use-mianotes-{mianotes_note['id'][:8]}.html"
    saved_navigation = [
        {
            "title": "Improvements",
            "items": [
                {
                    "title": "Improvements",
                    "path": improvements_path,
                }
            ],
        }
    ]

    publish_response = client.post(
        "/api/publish",
        json={
            "theme": "mianotes",
            "site_configuration": {
                "brand": "mianotes",
                "version": "0.1.0",
                "headerLinks": [],
                "footerHtml": "Copyright © Test.",
            },
            "navigation": saved_navigation,
            "updated_notes": [],
        },
    )
    assert publish_response.status_code == 201

    folder_publish_response = client.post(
        "/api/publish",
        json={
            "folder_id": mianotes_folder["id"],
            "theme": "mianotes",
            "site_configuration": {
                "brand": "mianotes",
                "version": "0.1.0",
                "headerLinks": [],
                "footerHtml": "Copyright © Test.",
            },
            "navigation": [
                {
                    "title": "Mianotes",
                    "items": [
                        {
                            "title": "How to use Mianotes",
                            "path": f"how-to-use-mianotes-{mianotes_note['id'][:8]}.html",
                        }
                    ],
                }
            ],
            "updated_notes": [],
        },
    )
    assert folder_publish_response.status_code == 201

    draft = client.get("/api/publish/draft").json()

    assert draft["navigation"] == saved_navigation
    assert {
        "title": "How to use Mianotes",
        "path": mianotes_path,
    } in draft["updated_notes"]
    assert all(note["path"].startswith("mianotes/") for note in draft["updated_notes"])


def test_publish_draft_includes_published_status_notes(client: TestClient):
    _join(client)
    folder = client.post("/api/folders", json={"name": "Published Docs"}).json()
    note = _create_note(
        client,
        folder["id"],
        "Published Note",
        "Already published text.",
    )
    with client.app.state.testing_session() as session:
        stored = session.get(Note, note["id"])
        assert stored is not None
        stored.status = "published"
        stored.is_published = True
        session.commit()

    response = client.get("/api/publish/draft", params={"folder_id": folder["id"]})

    assert response.status_code == 200
    assert response.json()["navigation"] == [
        {
            "title": "Published Docs",
            "items": [
                {
                    "title": "Published Note",
                    "path": f"published-note-{note['id'][:8]}.html",
                }
            ],
        }
    ]
