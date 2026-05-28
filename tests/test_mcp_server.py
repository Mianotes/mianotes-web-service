import io
import json

from mianotes_web_service import mcp_server
from mianotes_web_service.mcp_server import TOOL_DEFINITIONS, handle_request


def test_mcp_initialize_and_tool_list():
    initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["name"] == "mianotes"

    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "search_notes" in tool_names
    assert "create_note_from_url" in tool_names
    assert "add_comment" in tool_names


def test_mcp_initialized_notification_has_no_response():
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_stdio_main_handles_initialize(monkeypatch):
    stdin = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(mcp_server.sys, "stdin", stdin)
    monkeypatch.setattr(mcp_server.sys, "stdout", stdout)

    mcp_server.main()

    response = json.loads(stdout.getvalue())
    assert response["id"] == 1
    assert response["result"]["capabilities"] == {"tools": {}}
    assert response["result"]["serverInfo"]["name"] == "mianotes"


def test_mcp_tool_call_sends_authenticated_api_request(monkeypatch):
    seen = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        seen.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "timeout": timeout,
                "authorization": request.get_header("Authorization"),
                "client": request.get_header("X-mianotes-client"),
                "workspace": request.get_header("X-mianotes-workspace"),
            }
        )
        if request.full_url.endswith("/api/auth/agent-session"):
            return FakeResponse({"token": "agent-session-token"})
        return FakeResponse([{"id": "folder-1", "name": "Demo"}])

    monkeypatch.setenv("MIANOTES_API_URL", "http://127.0.0.1:8200/")
    monkeypatch.setenv("MIANOTES_API_KEY", "mia_test_token")
    monkeypatch.setenv("MIANOTES_CLIENT_NAME", "Codex")
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "list_folders",
                "arguments": {"include_archived": True, "user_id": None},
            },
        }
    )

    assert response is not None
    assert response["id"] == 9
    assert json.loads(response["result"]["content"][0]["text"]) == [
        {"id": "folder-1", "name": "Demo"}
    ]
    assert seen == [
        {
            "url": "http://127.0.0.1:8200/api/auth/agent-session",
            "method": "POST",
            "timeout": 30,
            "authorization": "Bearer mia_test_token",
            "client": "Codex",
            "workspace": None,
        },
        {
            "url": "http://127.0.0.1:8200/api/folders?include_archived=True",
            "method": "GET",
            "timeout": 30,
            "authorization": "Bearer agent-session-token",
            "client": None,
            "workspace": None,
        },
    ]


def test_mcp_tool_call_sends_workspace_header(monkeypatch):
    seen = []

    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):
        seen.append(
            {
                "url": request.full_url,
                "workspace": request.get_header("X-mianotes-workspace"),
            }
        )
        if request.full_url.endswith("/api/auth/agent-session"):
            return FakeResponse({"token": "agent-session-token"})
        return FakeResponse([])

    monkeypatch.setenv("MIANOTES_API_KEY", "mia_test_token")
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {
                "name": "search_notes",
                "arguments": {"workspace": "research", "q": "getting started"},
            },
        }
    )

    assert response is not None
    assert seen[-1] == {
        "url": "http://127.0.0.1:8200/api/search?q=getting+started",
        "workspace": "research",
    }


def test_mcp_tool_call_reports_missing_api_key(monkeypatch):
    monkeypatch.delenv("MIANOTES_API_KEY", raising=False)
    monkeypatch.delenv("MIANOTES_API_TOKEN", raising=False)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {}},
        }
    )

    assert response is not None
    assert response["error"]["message"] == "MIANOTES_API_KEY is required"


def test_mcp_unknown_tool_returns_error():
    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing_tool", "arguments": {}},
        }
    )
    assert response is not None
    assert response["error"]["code"] == -32000


def test_mcp_tool_definitions_have_json_schemas():
    assert all(tool["inputSchema"]["type"] == "object" for tool in TOOL_DEFINITIONS)
