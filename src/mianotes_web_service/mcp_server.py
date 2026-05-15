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


TOOL_DEFINITIONS: list[JsonObject] = [
    {
        "name": "list_topics",
        "description": "List Mianotes topics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_archived": {"type": "boolean", "default": False},
                "user_id": {"type": "string"},
            },
        },
    },
    {
        "name": "create_topic",
        "description": "Create a Mianotes topic.",
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
                "topic_id": {"type": "string"},
                "user_id": {"type": "string"},
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
            "required": ["topic_id", "text"],
            "properties": {
                "topic_id": {"type": "string"},
                "text": {"type": "string"},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "create_note_from_url",
        "description": "Create a Mianotes note from a URL and queue parsing.",
        "inputSchema": {
            "type": "object",
            "required": ["topic_id", "url"],
            "properties": {
                "topic_id": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "update_note",
        "description": "Update a Mianotes note title, text, published state, or tags.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {
                "note_id": {"type": "string"},
                "title": {"type": "string"},
                "text": {"type": "string"},
                "is_published": {"type": "boolean"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "add_comment",
        "description": "Add a comment to a Mianotes note.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id", "body"],
            "properties": {"note_id": {"type": "string"}, "body": {"type": "string"}},
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
    {
        "name": "summarise_note",
        "description": "Create a queued Mia summarise job for a note.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {"note_id": {"type": "string"}},
        },
    },
    {
        "name": "structure_note",
        "description": "Create a queued Mia structure job for a note.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {"note_id": {"type": "string"}},
        },
    },
    {
        "name": "extract_note",
        "description": "Create a queued Mia extract job for a note.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {"note_id": {"type": "string"}},
        },
    },
    {
        "name": "rewrite_note",
        "description": "Create a queued Mia rewrite job for a note.",
        "inputSchema": {
            "type": "object",
            "required": ["note_id"],
            "properties": {"note_id": {"type": "string"}},
        },
    },
]


def _api_url() -> str:
    return os.environ.get("MIANOTES_API_URL", DEFAULT_API_URL).rstrip("/")


def _api_token() -> str:
    token = os.environ.get("MIANOTES_API_TOKEN")
    if not token:
        raise RuntimeError("MIANOTES_API_TOKEN is required")
    return token


def _request(
    method: str,
    path: str,
    *,
    query: JsonObject | None = None,
    body: JsonObject | None = None,
) -> Any:
    url = f"{_api_url()}{path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value is not None}
        if clean_query:
            url = f"{url}?{urlencode(clean_query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_api_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"Mianotes API returned {exc.code}: {detail}") from exc
    return json.loads(payload) if payload else None


def call_tool(name: str, arguments: JsonObject) -> Any:
    if name == "list_topics":
        return _request("GET", "/api/topics", query=arguments)
    if name == "create_topic":
        return _request("POST", "/api/topics", body={"name": arguments["name"]})
    if name == "list_notes":
        return _request("GET", "/api/notes", query=arguments)
    if name == "get_note":
        return _request("GET", f"/api/notes/{arguments['note_id']}")
    if name == "create_note":
        body = {
            key: arguments[key]
            for key in ("topic_id", "text", "title", "tags")
            if key in arguments
        }
        return _request("POST", "/api/notes/from-text", body=body)
    if name == "create_note_from_url":
        body = {
            key: arguments[key]
            for key in ("topic_id", "url", "title", "tags")
            if key in arguments
        }
        return _request("POST", "/api/notes/from-url", body=body)
    if name == "update_note":
        note_id = arguments["note_id"]
        body = {
            key: arguments[key]
            for key in ("title", "text", "is_published", "tags")
            if key in arguments
        }
        return _request("PATCH", f"/api/notes/{note_id}", body=body)
    if name == "add_comment":
        return _request(
            "POST",
            f"/api/notes/{arguments['note_id']}/comments",
            body={"body": arguments["body"]},
        )
    if name == "set_tags":
        return _request(
            "PUT",
            f"/api/notes/{arguments['note_id']}/tags",
            body={"tags": arguments["tags"]},
        )
    if name == "search_notes":
        return _request("GET", "/api/search", query=arguments)
    if name in {"summarise_note", "structure_note", "extract_note", "rewrite_note"}:
        operation = name.removesuffix("_note")
        return _request("POST", f"/api/notes/{arguments['note_id']}/{operation}")
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
