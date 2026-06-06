import io
import json
from urllib.error import HTTPError

from mianotes_web_service import mcp_server
from mianotes_web_service.mcp_server import TOOL_DEFINITIONS, handle_request
from mianotes_web_service.services import runtime_env


def test_mcp_initialize_and_tool_list():
    initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["name"] == "mianotes"

    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "search_notes" in tool_names
    assert "read_note_context" in tool_names
    assert "create_note_in_folder" in tool_names
    assert "create_note_from_url" in tool_names


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
            "client": None,
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


def test_mcp_tool_call_loads_package_env_file(monkeypatch, tmp_path):
    env_file = tmp_path / "mianotes.env"
    env_file.write_text(
        'MIANOTES_API_URL="http://127.0.0.1:9999"\n'
        'MIANOTES_API_KEY="mia_package_token"\n',
        encoding="utf-8",
    )
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
                "authorization": request.get_header("Authorization"),
            }
        )
        if request.full_url.endswith("/api/auth/agent-session"):
            return FakeResponse({"token": "agent-session-token"})
        return FakeResponse([])

    monkeypatch.delenv("MIANOTES_API_URL", raising=False)
    monkeypatch.delenv("MIANOTES_API_KEY", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_env.sys, "prefix", str(tmp_path / "python"))
    monkeypatch.setattr(runtime_env, "PACKAGED_ENV_FILES", (env_file,))
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 15,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {}},
        }
    )

    assert response is not None
    assert seen[0] == {
        "url": "http://127.0.0.1:9999/api/auth/agent-session",
        "authorization": "Bearer mia_package_token",
    }


def test_mcp_tool_call_loads_source_venv_env_file(monkeypatch, tmp_path):
    project_dir = tmp_path / "mianotes-web-service"
    venv_dir = project_dir / ".venv"
    venv_dir.mkdir(parents=True)
    (project_dir / ".env").write_text(
        'MIANOTES_API_URL="http://127.0.0.1:7777"\n'
        'MIANOTES_API_KEY="mia_source_token"\n',
        encoding="utf-8",
    )
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
                "authorization": request.get_header("Authorization"),
            }
        )
        if request.full_url.endswith("/api/auth/agent-session"):
            return FakeResponse({"token": "agent-session-token"})
        return FakeResponse([])

    monkeypatch.delenv("MIANOTES_API_URL", raising=False)
    monkeypatch.delenv("MIANOTES_API_KEY", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE", raising=False)
    monkeypatch.delenv("MIANOTES_ENV_FILE_PATH", raising=False)
    agent_project = tmp_path / "agent-project"
    agent_project.mkdir()
    monkeypatch.chdir(agent_project)
    monkeypatch.setattr(runtime_env.sys, "prefix", str(venv_dir))
    monkeypatch.setattr(runtime_env, "PACKAGED_ENV_FILES", ())
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {}},
        }
    )

    assert response is not None
    assert seen[0] == {
        "url": "http://127.0.0.1:7777/api/auth/agent-session",
        "authorization": "Bearer mia_source_token",
    }


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


def test_mcp_read_note_context_uses_context_endpoint(monkeypatch):
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
        return FakeResponse(
            {
                "folder": "About",
                "title": "Use Cases",
                "total": 1,
                "results": [{"text": "# Use cases\n\nActual note text."}],
            }
        )

    monkeypatch.setenv("MIANOTES_API_KEY", "mia_test_token")
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {
                "name": "read_note_context",
                "arguments": {
                    "workspace": "Docs",
                    "folder": "About",
                    "note": "Use Cases",
                },
            },
        }
    )

    assert response is not None
    payload = json.loads(response["result"]["content"][0]["text"])
    assert payload["results"][0]["text"] == "# Use cases\n\nActual note text."
    assert seen[-1] == {
        "url": (
            "http://127.0.0.1:8200/api/context?"
            "folder=About&title=Use+Cases&limit=5"
        ),
        "workspace": "Docs",
    }


def test_mcp_create_note_in_folder_resolves_folder_name(monkeypatch):
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
        body = request.data.decode("utf-8") if request.data else None
        seen.append(
            {
                "url": request.full_url,
                "method": request.get_method(),
                "workspace": request.get_header("X-mianotes-workspace"),
                "body": json.loads(body) if body else None,
            }
        )
        if request.full_url.endswith("/api/auth/agent-session"):
            return FakeResponse({"token": "agent-session-token"})
        if request.full_url.endswith("/api/folders"):
            return FakeResponse([{"id": "folder-about", "name": "About", "slug": "about"}])
        return FakeResponse({"id": "note-1", "title": "Architecture notes"})

    monkeypatch.setenv("MIANOTES_API_KEY", "mia_test_token")
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "create_note_in_folder",
                "arguments": {
                    "workspace": "Docs",
                    "folder": "About",
                    "title": "Architecture notes",
                    "text": "Documented architecture.",
                    "tags": ["docs"],
                },
            },
        }
    )

    assert response is not None
    assert json.loads(response["result"]["content"][0]["text"]) == {
        "id": "note-1",
        "title": "Architecture notes",
    }
    assert seen[-1] == {
        "url": "http://127.0.0.1:8200/api/notes/from-text",
        "method": "POST",
        "workspace": "Docs",
        "body": {
            "folder_id": "folder-about",
            "tags": ["docs"],
            "text": "Documented architecture.",
            "title": "Architecture notes",
        },
    }


def test_mcp_tool_call_reports_missing_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("MIANOTES_API_KEY", raising=False)
    monkeypatch.delenv("MIANOTES_API_URL", raising=False)
    monkeypatch.setenv("MIANOTES_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_env.sys, "prefix", str(tmp_path / "python"))
    monkeypatch.setattr(runtime_env, "PACKAGED_ENV_FILES", ())
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

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


def test_mcp_tool_call_reports_rejected_api_key_with_recovery(monkeypatch):
    class FakeErrorResponse:
        def read(self):
            return b'{"detail":"Invalid API token"}'

        def close(self):
            return None

    def fake_urlopen(_request, timeout: int):
        raise HTTPError(
            url="http://127.0.0.1:8200/api/auth/agent-session",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=FakeErrorResponse(),
        )

    monkeypatch.setenv("MIANOTES_API_KEY", "mia_test_token")
    monkeypatch.setattr(mcp_server, "urlopen", fake_urlopen)
    monkeypatch.setattr(mcp_server, "_AGENT_SESSION_TOKEN", None)

    response = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "tools/call",
            "params": {"name": "list_notes", "arguments": {}},
        }
    )

    assert response is not None
    message = response["error"]["message"]
    assert "Mianotes rejected the configured API key" in message
    assert "Create or rotate the API key in Mianotes Settings" in message
    assert "restart this agent session" in message


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
