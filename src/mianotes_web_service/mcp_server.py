from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mianotes_web_service import __version__

JsonObject = dict[str, Any]

DEFAULT_API_URL = "http://127.0.0.1:8200"
_AGENT_SESSION_TOKEN: str | None = None


TOOL_DEFINITIONS: list[JsonObject] = [
    {
        "name": "list_workspaces",
        "description": "List configured Mianotes workspaces.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "list_folders",
        "description": "List folders in a Mianotes workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_archived": {"type": "boolean", "default": False},
                "user_id": {"type": "string"},
            },
        },
    },
    {
        "name": "create_folder",
        "description": "Create a Mianotes folder.",
        "inputSchema": {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
    },
    {
        "name": "list_notes",
        "description": "List Mianotes notes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder_id": {"type": "string"},
                "user_id": {"type": "string"},
            },
        },
    },
    {
        "name": "read_note_context",
        "description": (
            "Read a Mianotes note by workspace, folder name, and note title. "
            "Use this for requests like Mia(workspace: Docs, folder: About, note: Use Cases). "
            "Returns the full note text when a matching note exists."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["workspace", "folder", "note"],
            "properties": {
                "workspace": {
                    "type": "string",
                    "description": "Workspace name or id, for example Docs.",
                },
                "folder": {"type": "string"},
                "note": {"type": "string", "description": "Note title to read."},
                "limit": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "get_note",
        "description": "Get a Mianotes note by ID.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {"note_id": {"type": "string"}},
        },
    },
    {
        "name": "create_note",
        "description": "Create a Mianotes note from text.",
        "inputSchema": {
            "type": "object",
            "required": ["folder_id", "text"],
            "properties": {
                "folder_id": {"type": "string"},
                "text": {"type": "string"},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "create_note_in_folder",
        "description": (
            "Create a Mianotes note by workspace and folder name. "
            "Use this for save/document requests like Mia(workspace: My App, folder: Architecture)."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["workspace", "folder", "text"],
            "properties": {
                "workspace": {
                    "type": "string",
                    "description": "Workspace name or id, for example Docs.",
                },
                "folder": {"type": "string"},
                "text": {"type": "string"},
                "title": {
                    "type": "string",
                    "description": "Useful note title. Create one from the content if omitted.",
                },
                "tags": {"type": "array", "items": {"type": "string"}},
                "create_folder_if_missing": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "create_note_from_url",
        "description": "Create a Mianotes note from a URL and queue parsing.",
        "inputSchema": {
            "type": "object",
            "required": ["folder_id", "url"],
            "properties": {
                "folder_id": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "update_note",
        "description": "Update a Mianotes note folder, title, text, published state, or tags.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {
                "note_id": {"type": "string"},
                "folder_id": {"type": "string"},
                "title": {"type": "string"},
                "text": {"type": "string"},
                "is_published": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "set_tags",
        "description": "Replace a note's tags.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id", "tags"],
            "properties": {
                "note_id": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "search_notes",
        "description": "Search Mianotes Markdown notes with ripgrep.",
        "inputSchema": {
            "type": "object",
            "required": ["q"],
            "properties": {"q": {"type": "string"}, "limit": {"type": "integer"}},
        },
    },
]


for tool in TOOL_DEFINITIONS:
    if tool["name"] == "list_workspaces":
        continue
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict):
        continue
    properties = schema.setdefault("properties", {})
    if isinstance(properties, dict):
        properties.setdefault(
            "workspace",
            {
                "type": "string",
                "description": (
                    "Workspace name or id to use for this call. "
                    "Omit to use the current/default workspace."
                ),
            },
        )


def _api_url() -> str:
    return os.environ.get("MIANOTES_API_URL", DEFAULT_API_URL).rstrip("/")


def _raw_api_token() -> str:
    token = os.environ.get("MIANOTES_API_KEY") or os.environ.get("MIANOTES_API_TOKEN")
    if not token:
        raise RuntimeError("MIANOTES_API_KEY is required")
    return token


def _client_name() -> str:
    return os.environ.get("MIANOTES_CLIENT_NAME") or os.environ.get("MIANOTES_CLIENT") or "MCP"


def _api_token() -> str:
    global _AGENT_SESSION_TOKEN
    if _AGENT_SESSION_TOKEN:
        return _AGENT_SESSION_TOKEN

    request = Request(
        f"{_api_url()}/api/auth/agent-session",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {_raw_api_token()}",
            "Content-Type": "application/json",
            "X-Mianotes-Client": _client_name(),
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        if exc.code == 401:
            raise RuntimeError(
                "Mianotes rejected the configured API key. "
                "Create or rotate the API key in Mianotes Settings, "
                "then restart this agent session so MCP reloads the service .env file."
            ) from exc
        raise RuntimeError(f"Mianotes API returned {exc.code}: {detail}") from exc
    _AGENT_SESSION_TOKEN = str(payload["token"])
    return _AGENT_SESSION_TOKEN


def _request(
    method: str,
    path: str,
    *,
    query: JsonObject | None = None,
    body: JsonObject | None = None,
    workspace: str | None = None,
) -> Any:
    url = f"{_api_url()}{path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{urlencode(clean_query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {_api_token()}",
        "Content-Type": "application/json",
    }
    if workspace:
        headers["X-Mianotes-Workspace"] = workspace
    request = Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Mianotes API returned {exc.code}: {detail}") from exc
    return json.loads(payload) if payload else None


def _workspace_argument(arguments: JsonObject) -> str | None:
    workspace = arguments.get("workspace")
    return workspace if isinstance(workspace, str) and workspace else None


def _without_workspace(arguments: JsonObject) -> JsonObject:
    return {key: value for key, value in arguments.items() if key != "workspace"}


def _normalised_name(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _folder_slug(value: str) -> str:
    return "-".join(part for part in _normalised_name(value).replace("_", "-").split() if part)


def _folder_by_name(folders: list[JsonObject], folder_name: str) -> JsonObject | None:
    wanted_name = _normalised_name(folder_name)
    wanted_slug = _folder_slug(folder_name)
    for folder in folders:
        name = str(folder.get("name") or "")
        slug = str(folder.get("slug") or "")
        if _normalised_name(name) == wanted_name or slug.lower() == wanted_slug:
            return folder
    return None


def call_tool(name: str, arguments: JsonObject) -> Any:
    workspace = _workspace_argument(arguments)
    if name == "list_folders":
        return _request(
            "GET",
            "/api/folders",
            query=_without_workspace(arguments),
            workspace=workspace,
        )
    if name == "list_workspaces":
        return _request("GET", "/api/settings/storage")
    if name == "create_folder":
        return _request(
            "POST",
            "/api/folders",
            body={"name": arguments["name"]},
            workspace=workspace,
        )
    if name == "list_notes":
        return _request(
            "GET",
            "/api/notes",
            query=_without_workspace(arguments),
            workspace=workspace,
        )
    if name == "get_note":
        return _request("GET", f"/api/notes/{arguments['note_id']}", workspace=workspace)
    if name == "read_note_context":
        return _request(
            "GET",
            "/api/context",
            query={
                "folder": arguments["folder"],
                "title": arguments["note"],
                "limit": arguments.get("limit", 5),
            },
            workspace=workspace,
        )
    if name == "create_note":
        body = {
            key: arguments[key]
            for key in ("folder_id", "text", "title", "tags")
            if key in arguments
        }
        return _request("POST", "/api/notes/from-text", body=body, workspace=workspace)
    if name == "create_note_in_folder":
        folders = _request("GET", "/api/folders", workspace=workspace)
        if not isinstance(folders, list):
            raise RuntimeError("Mianotes API returned an unexpected folders response")
        folder = _folder_by_name(folders, arguments["folder"])
        if folder is None and arguments.get("create_folder_if_missing"):
            folder = _request(
                "POST",
                "/api/folders",
                body={"name": arguments["folder"]},
                workspace=workspace,
            )
        if folder is None:
            raise RuntimeError(f"Mianotes folder not found: {arguments['folder']}")
        body = {
            key: arguments[key]
            for key in ("text", "title", "tags")
            if key in arguments
        }
        body["folder_id"] = folder["id"]
        return _request("POST", "/api/notes/from-text", body=body, workspace=workspace)
    if name == "create_note_from_url":
        body = {
            key: arguments[key]
            for key in ("folder_id", "url", "title", "tags")
            if key in arguments
        }
        return _request("POST", "/api/notes/from-url", body=body, workspace=workspace)
    if name == "update_note":
        note_id = arguments["note_id"]
        body = {
            key: arguments[key]
            for key in ("folder_id", "title", "text", "is_published", "tags")
            if key in arguments
        }
        return _request("PATCH", f"/api/notes/{note_id}", body=body, workspace=workspace)
    if name == "set_tags":
        return _request(
            "PUT",
            f"/api/notes/{arguments['note_id']}/tags",
            body={"tags": arguments["tags"]},
            workspace=workspace,
        )
    if name == "search_notes":
        return _request(
            "GET",
            "/api/search",
            query=_without_workspace(arguments),
            workspace=workspace,
        )
    raise RuntimeError(f"Unknown tool: {name}")


def _tool_result(result: Any) -> JsonObject:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, indent=2, sort_keys=True),
            }
        ]
    }


def handle_request(message: JsonObject) -> JsonObject | None:
    request_id = message.get("id")
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mianotes", "version": __version__},
            }
        elif method == "tools/list":
            result = {"tools": TOOL_DEFINITIONS}
        elif method == "tools/call":
            params = message.get("params") or {}
            result = _tool_result(call_tool(params["name"], params.get("arguments") or {}))
        else:
            raise RuntimeError(f"Unsupported MCP method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle_request(json.loads(line))
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
