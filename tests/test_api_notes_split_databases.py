from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mianotes_web_service.app import create_app
from mianotes_web_service.core.config import get_settings


def test_note_listing_search_uses_workspace_database_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIANOTES_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        joined = client.post(
            "/api/auth/join",
            json={
                "email": "search@example.com",
                "name": "Search User",
                "password": "house-password",
                "password_confirmation": "house-password",
            },
        )
        assert joined.status_code == 201

        folder = client.post("/api/folders", json={"name": "Research"}).json()
        created = client.post(
            "/api/notes/from-text",
            json={
                "folder_id": folder["id"],
                "title": "Elephant field notes",
                "text": "Research notes with searchable evidence.",
                "tags": ["evidence"],
            },
        )
        assert created.status_code == 201
        note = created.json()

        response = client.get(
            "/api/notes",
            params={
                "limit": 10,
                "folder_id": folder["id"],
                "query": "e",
            },
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [note["id"]]

    get_settings.cache_clear()
