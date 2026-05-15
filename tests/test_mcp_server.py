from mianotes_web_service.mcp_server import TOOL_DEFINITIONS, handle_request


def test_mcp_initialize_and_tool_list():
    initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert initialized is not None
    assert initialized["result"]["serverInfo"]["name"] == "mianotes"

    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert listed is not None
    tool_names = {tool["name"] for tool in listed["result"]["tools"]}
    assert "search_notes" in tool_names
    assert "summarise_note" in tool_names
    assert "rewrite_note" in tool_names


def test_mcp_initialized_notification_has_no_response():
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


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
