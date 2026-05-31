import zipfile
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from shutil import rmtree

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings
from mianotes_web_service.db.models import Base, Folder, Note, PublishedSite, User
from mianotes_web_service.db.session import get_session
from mianotes_web_service.domain.schemas import PublishRequest
from mianotes_web_service.services.publishing import publish_site
from mianotes_web_service.services.storage_settings import (
    DEFAULT_DATABASE_FILE,
    StorageConfig,
    StorageLocation,
    write_storage_config,
)
from mianotes_web_service.services.workspace_context import WorkspaceContext


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


def test_workspace_scoped_html_route_serves_published_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    data_dir = tmp_path / "data"
    docs_dir = tmp_path / "docs"
    config_path = tmp_path / "workspaces.json"
    write_storage_config(
        config_path,
        StorageConfig(
            active_location="default",
            database_file=DEFAULT_DATABASE_FILE,
            locations=[
                StorageLocation(
                    id="default",
                    name="Main workspace",
                    folder_path=data_dir,
                ),
                StorageLocation(
                    id="docs",
                    name="Docs",
                    folder_path=docs_dir,
                ),
            ],
        ),
    )
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MIANOTES_STORAGE_CONFIG_PATH", str(config_path))
    get_settings.cache_clear()
    (docs_dir / "html" / "0.2.7").mkdir(parents=True)
    (docs_dir / "html" / "0.2.7" / "index.html").write_text(
        "<!doctype html><title>Docs</title>",
        encoding="utf-8",
    )

    app = create_app()
    with TestClient(app) as workspace_client:
        response = workspace_client.get("/html/workspaces/docs/0.2.7/index.html")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "Docs" in response.text


def test_publish_themes_are_listed(client: TestClient):
    _join(client)

    response = client.get("/api/publish/themes")

    assert response.status_code == 200
    themes = response.json()
    assert [theme["id"] for theme in themes] == ["mialight", "miadocs", "miadev", "miadark"]


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
    assert draft["theme"] == "mialight"
    assert draft["folder_id"] == folder["id"]
    assert draft["tag_id"] is None
    assert draft["site_configuration"]["brand"] == "mianotes"
    assert draft["site_configuration"]["headerLinks"] == [
        {"title": "Website", "url": "https://www.mianotes.com/"},
        {"title": "Feedback", "url": "https://tally.so/r/xXvQbk"},
    ]
    assert draft["site_configuration"]["showPreviousVersions"] is True
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
        (
            "# Clients\n\n"
            "MCP clients connect agents to local tools.\n\n"
            "## Configuration\n\n"
            "| Field | Type | Description |\n"
            "|---|---|---|\n"
            "| `id` | string | Unique client ID. |\n"
            "| `archived_at` | string \\| null | ISO 8601 archive timestamp. |\n\n"
            "```json\n"
            "{\"method\": \"tools/list\"}\n"
            "```\n\n"
            "> [!TIP] Understanding the configuration\n"
            "> Use `MIANOTES_API_KEY` to connect agents.\n\n"
            ":::note\n"
            "**Note**\n\n"
            "This documentation was generated with Codex using [Mianotes](https://www.mianotes.com/).\n"
            ":::\n\n"
            "> [!WARNING] Security consideration\n"
            "> Keep API keys private.\n\n"
            "1. Run MarkItDown's converter.\n"
            "2. Try Tesseract for `.jpg` files.\n"
        ),
    )
    note_path = f"clients-{note['id'][:8]}.html"
    payload = {
        "folder_id": folder["id"],
        "theme": "mialight",
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
    assert published["theme"] == "mialight"
    assert published["version"] == "0.1.1"
    assert published["folder_id"] == folder["id"]
    assert published["tag_id"] is None
    assert published["note_count"] == 1
    assert published["html_path"] == "html/0.1.1"
    assert published["markdown_path"] == ""
    assert published["url_path"] == "html/0.1.1/index.html"
    assert published["site_url"].endswith("/html/workspaces/default/0.1.1/index.html")
    assert published["download_url"].endswith(f"/api/publish/{published['id']}/download")

    html_root = tmp_path / "data" / "html" / "0.1.1"
    assert (html_root / "index.html").is_file()
    assert (html_root / "styles.css").is_file()
    assert (html_root / "site.js").is_file()
    assert (html_root / "search.js").is_file()
    assert (tmp_path / "data" / "html" / "navigation.js").is_file()
    latest_index = tmp_path / "data" / "html" / "latest" / "index.html"
    assert latest_index.is_file()
    latest_index_text = latest_index.read_text(encoding="utf-8")
    assert "../0.1.1/index.html" in latest_index_text
    assert 'const latestBase = "../0.1.1/";' in latest_index_text
    assert 'hash.startsWith("#/")' in latest_index_text
    assert "hash.slice(2)" in latest_index_text
    assert "`${latestBase}${requestedPath}`" in latest_index_text
    readme_md = (tmp_path / "data" / "html" / "README.md")
    assert readme_md.is_file()
    assert readme_md.read_text(encoding="utf-8") == (
        "# Mia Docs Documentation\n"
        "\n"
        "- **About MCP**\n"
        f"  - [Clients](markdown/about-mcp/clients-{note['id'][:8]}.md)\n"
    )
    note_html = (html_root / note_path).read_text(encoding="utf-8")
    assert note_html.find("styles.css") > -1
    assert '<meta name="generator" content="Mianotes - https://github.com/Mianotes">' in note_html
    assert note_html.count("<h1>Clients</h1>") == 1
    assert '<table class="doc-table">' in note_html
    assert "<th>Field</th>" in note_html
    assert "<code>id</code>" in note_html
    assert "<code>archived_at</code>" in note_html
    assert "<td>string | null</td>" in note_html
    assert "<td>null</td>" not in note_html
    assert "| Field | Type | Description |" not in note_html
    assert '<div class="code-card">' in note_html
    assert '<span class="tok-key">&quot;method&quot;</span>' in note_html
    assert 'class="admonition admonition-note"' in note_html
    assert '<aside class="admonition admonition-note"><div class="admonition-body">' in note_html
    assert (
        '<div class="admonition-title"><span class="admonition-icon" aria-hidden="true"></span>'
        "<strong>Note</strong></div>"
    ) not in note_html
    assert "<p><strong>Note</strong></p>" in note_html
    assert 'class="admonition admonition-tip"' in note_html
    assert "<strong>Understanding the configuration</strong>" in note_html
    assert 'class="admonition admonition-warning"' in note_html
    assert "<strong>Security consideration</strong>" in note_html
    assert (
        "<ol><li>Run MarkItDown&#x27;s converter.</li>"
        "<li>Try Tesseract for <code>.jpg</code> files.</li></ol>"
    ) in note_html
    assert "<p>1. Run MarkItDown" not in note_html
    assert '<aside class="page-toc" data-page-toc></aside>' in note_html
    assert (tmp_path / "data" / "markdown" / "about-mcp").is_dir()

    listed_note = client.get(f"/api/notes/{note['id']}").json()
    assert listed_note["is_published"] is True
    assert listed_note["published_at"] is not None

    published_file = client.get("/html/0.1.1/index.html")
    assert published_file.status_code == 200
    assert published_file.headers["cache-control"] == "no-store"
    workspace_published_file = client.get("/html/workspaces/default/0.1.1/index.html")
    assert workspace_published_file.status_code == 200
    assert workspace_published_file.headers["cache-control"] == "no-store"
    note_file = client.get(f"/html/0.1.1/{note_path}")
    assert note_file.status_code == 200
    assert note_file.headers["cache-control"] == "no-store"
    assert "Mia Docs" in note_file.text
    assert "MCP clients" in note_file.text
    site_js = (html_root / "site.js").read_text(encoding="utf-8")
    assert "https://github.com/Mianotes" in site_js
    assert site_js.find("${versionLinks}") < site_js.find("${externalLinks}")
    assert "renderPageToc();" in site_js

    public_client = TestClient(client.app)
    public_root = public_client.get("/html")
    assert public_root.status_code == 200
    public_published_file = public_client.get("/html/0.1.1/index.html")
    assert public_published_file.status_code == 200
    public_latest_file = public_client.get("/html/latest/")
    assert public_latest_file.status_code == 200
    assert 'const latestBase = "../0.1.1/";' in public_latest_file.text
    public_workspace_published_file = public_client.get(
        "/html/workspaces/default/0.1.1/index.html"
    )
    assert public_workspace_published_file.status_code == 200
    public_workspace_latest_file = public_client.get("/html/workspaces/default/latest/")
    assert public_workspace_latest_file.status_code == 200
    assert 'const latestBase = "../0.1.1/";' in public_workspace_latest_file.text
    public_note_file = public_client.get(f"/html/0.1.1/{note_path}")
    assert public_note_file.status_code == 200
    public_markdown = public_client.get(f"/markdown/about-mcp/clients-{note['id'][:8]}.md")
    assert public_markdown.status_code == 200
    assert "MCP clients" in public_markdown.text
    public_source_file = public_client.get(
        f"/markdown/about-mcp/sources/{note['id'][:8]}/original.txt"
    )
    assert public_source_file.status_code == 200
    assert "# Clients" in public_source_file.text
    assert public_client.get("/markdown").status_code == 404

    archive_response = client.get(published["download_url"])
    assert archive_response.status_code == 200
    assert archive_response.headers["content-type"].startswith("application/zip")
    with zipfile.ZipFile(BytesIO(archive_response.content)) as archive:
        names = set(archive.namelist())
    assert "0.1.1-static-site/index.html" in names
    assert "0.1.1-static-site/navigation.js" in names
    assert "0.1.1-static-site/README.md" in names
    assert "0.1.1-static-site/latest/index.html" in names
    assert f"0.1.1-static-site/0.1.1/{note_path}" in names

    next_draft = client.get("/api/publish/draft", params={"folder_id": folder["id"]}).json()
    assert next_draft["site_configuration"]["brand"] == "Mia Docs"
    assert next_draft["site_configuration"]["showPreviousVersions"] is True
    assert next_draft["navigation"] == payload["navigation"]
    assert next_draft["updated_notes"] == []


def test_publish_site_replaces_same_version_html(client: TestClient, tmp_path: Path):
    _join(client)
    folder = client.post("/api/folders", json={"name": "Release Notes"}).json()
    note = _create_note(client, folder["id"], "Changelog", "First published body.")
    note_path = f"changelog-{note['id'][:8]}.html"
    payload = {
        "folder_id": folder["id"],
        "theme": "mialight",
        "site_configuration": {
            "brand": "Mia Docs",
            "version": "1.0.0",
            "headerLinks": [],
            "footerHtml": "",
        },
        "navigation": [
            {"title": "Release Notes", "items": [{"title": "Changelog", "path": note_path}]}
        ],
        "updated_notes": [{"title": "Changelog", "path": note_path}],
    }

    first_response = client.post("/api/publish", json=payload)
    assert first_response.status_code == 201
    first_html = (tmp_path / "data" / "html" / "1.0.0" / note_path).read_text(
        encoding="utf-8"
    )
    assert "First published body." in first_html

    update_response = client.patch(
        f"/api/notes/{note['id']}",
        json={"text": "Second published body."},
    )
    assert update_response.status_code == 200

    second_response = client.post("/api/publish", json=payload)
    assert second_response.status_code == 201
    second_html = (tmp_path / "data" / "html" / "1.0.0" / note_path).read_text(
        encoding="utf-8"
    )
    assert "Second published body." in second_html
    assert "First published body." not in second_html

    served_html = client.get(f"/html/1.0.0/{note_path}")
    assert served_html.status_code == 200
    assert served_html.headers["cache-control"] == "no-store"
    assert "Second published body." in served_html.text


def test_publish_site_resolves_markdown_from_session_workspace(
    client: TestClient,
    tmp_path: Path,
):
    workspace_dir = tmp_path / "portable-docs"
    note_path = workspace_dir / "markdown" / "about" / "what-is-mianotes-c08cbf08.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# What is Mianotes?\n\nPortable workspace content.", encoding="utf-8")
    workspace = WorkspaceContext(
        id="docs",
        name="Docs",
        folder_path=workspace_dir,
        database_file=".mianotes/mia.db",
    )
    session_factory = client.app.state.testing_session

    with session_factory() as session:
        session.info["workspace"] = workspace
        user = User(
            email="portable-publisher@example.com",
            name="Portable Publisher",
            username="portable-publisher",
            password_hash="hash",
            is_admin=True,
        )
        folder = Folder(user=user, name="About", slug="about", path="about")
        note = Note(
            user=user,
            folder=folder,
            title="What is Mianotes?",
            status="ready",
            source_type="text",
            filename=note_path.name,
            note_path="data/markdown/about/what-is-mianotes-c08cbf08.md",
        )
        session.add_all([user, folder, note])
        session.commit()
        note_id = note.id

        published = publish_site(
            session,
            user,
            PublishRequest(
                folder_id=None,
                theme="mialight",
                site_configuration={
                    "brand": "Mia Docs",
                    "version": "0.3.0",
                    "headerLinks": [],
                    "footerHtml": "",
                },
                navigation=[
                    {
                        "title": "About",
                        "items": [
                            {
                                "title": "What is Mianotes?",
                                "path": f"about/what-is-mianotes-{note_id[:8]}.html",
                            }
                        ],
                    }
                ],
                updated_notes=[{"title": "What is Mianotes?", "path": "unused.html"}],
            ),
        )

    assert published.version == "0.3.0"
    assert (
        workspace_dir / "html" / "0.3.0" / "about" / f"what-is-mianotes-{note_id[:8]}.html"
    ).is_file()
    readme = (workspace_dir / "html" / "README.md").read_text(encoding="utf-8")
    assert "markdown/about/what-is-mianotes-c08cbf08.md" in readme
    assert "0.3.0/about/what-is-mianotes" not in readme
    assert not (tmp_path / "data" / "html" / "0.3.0").exists()


def test_publish_prunes_missing_static_versions_from_navigation_and_db(
    client: TestClient,
    tmp_path: Path,
):
    _join(client)
    folder = client.post("/api/folders", json={"name": "Docs"}).json()
    note = _create_note(client, folder["id"], "Guide", "Published guide.")
    note_path = f"guide-{note['id'][:8]}.html"
    base_payload = {
        "folder_id": folder["id"],
        "theme": "mialight",
        "site_configuration": {
            "brand": "Mia Docs",
            "version": "0.1.0",
            "headerLinks": [],
            "footerHtml": "",
        },
        "navigation": [{"title": "Docs", "items": [{"title": "Guide", "path": note_path}]}],
        "updated_notes": [{"title": "Guide", "path": note_path}],
    }

    first_response = client.post("/api/publish", json=base_payload)
    assert first_response.status_code == 201
    first_version_dir = tmp_path / "data" / "html" / "0.1.0"
    assert first_version_dir.is_dir()
    rmtree(first_version_dir)

    next_payload = {
        **base_payload,
        "site_configuration": {
            **base_payload["site_configuration"],
            "version": "0.2.0",
        },
    }
    second_response = client.post("/api/publish", json=next_payload)
    assert second_response.status_code == 201

    navigation_js = (tmp_path / "data" / "html" / "navigation.js").read_text(encoding="utf-8")
    assert "0.2.0/index.html" in navigation_js
    assert "0.1.0/index.html" not in navigation_js
    latest_index = (tmp_path / "data" / "html" / "latest" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "../0.2.0/index.html" in latest_index
    assert 'const latestBase = "../0.2.0/";' in latest_index
    assert "../0.1.0/index.html" not in latest_index

    session_factory = client.app.state.testing_session
    with session_factory() as session:
        versions = [
            site.version
            for site in session.query(PublishedSite).order_by(PublishedSite.version).all()
        ]
    assert versions == ["0.2.0"]


def test_publish_site_uses_navigation_as_published_note_set(client: TestClient, tmp_path: Path):
    _join(client)
    removed_folder = client.post("/api/folders", json={"name": "Removed"}).json()
    kept_folder = client.post("/api/folders", json={"name": "Kept"}).json()
    removed_note = _create_note(client, removed_folder["id"], "Removed note", "Removed body.")
    kept_note = _create_note(client, kept_folder["id"], "Kept note", "Kept body.")
    removed_path = f"removed/removed-note-{removed_note['id'][:8]}.html"
    kept_path = f"kept/kept-note-{kept_note['id'][:8]}.html"
    payload = {
        "folder_id": None,
        "theme": "mialight",
        "site_configuration": {
            "brand": "Mia Docs",
            "version": "0.2.0",
            "headerLinks": [],
        },
        "navigation": [{"title": "Kept", "items": [{"title": "Kept note", "path": kept_path}]}],
        "updated_notes": [{"title": "Kept note", "path": kept_path}],
    }

    response = client.post("/api/publish", json=payload)

    assert response.status_code == 201
    assert response.json()["note_count"] == 1
    html_root = tmp_path / "data" / "html" / "0.2.0"
    index_html = (html_root / "index.html").read_text(encoding="utf-8")
    assert f"url=./{kept_path}" in index_html
    assert removed_path not in index_html
    assert (html_root / kept_path).is_file()
    assert not (html_root / removed_path).exists()
    search_js = (html_root / "search.js").read_text(encoding="utf-8")
    assert "Kept body." in search_js
    assert "Removed body." not in search_js
    assert client.get(f"/api/notes/{kept_note['id']}").json()["is_published"] is True
    assert client.get(f"/api/notes/{removed_note['id']}").json()["is_published"] is False


def test_publish_draft_regenerates_navigation_and_stages_new_navigation_items(
    client: TestClient,
):
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
    publish_response = client.post(
        "/api/publish",
        json={
            "folder_id": folder["id"],
            "theme": "mialight",
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

    assert next_draft["navigation"] == [
        {
            "title": "Publish staging",
            "items": [
                {
                    "title": "Architecture",
                    "path": first_path,
                },
                {
                    "title": "Settings page",
                    "path": second_path,
                },
            ],
        }
    ]
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
    reorder_response = client.patch(
        "/api/folders/order",
        json={"folder_ids": [improvements_folder["id"], mianotes_folder["id"]]},
    )
    assert reorder_response.status_code == 200
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
            "theme": "mialight",
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

    new_mianotes_note = _create_note(
        client,
        mianotes_folder["id"],
        "New Mianotes note",
        "Fresh Mianotes notes.",
    )
    new_mianotes_path = f"mianotes/new-mianotes-note-{new_mianotes_note['id'][:8]}.html"

    folder_publish_response = client.post(
        "/api/publish",
        json={
            "folder_id": mianotes_folder["id"],
            "theme": "mialight",
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

    assert draft["navigation"][0] == {
        "title": "Improvements",
        "items": [
            {
                "title": "Improvements",
                "path": improvements_path,
            }
        ],
    }
    mianotes_group = draft["navigation"][1]
    assert mianotes_group["title"] == "Mianotes"
    assert mianotes_group["items"] == [
        {
            "title": "New Mianotes note",
            "path": new_mianotes_path,
        }
    ]
    assert draft["updated_notes"] == mianotes_group["items"]


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
