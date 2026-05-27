from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentClient:
    key: str
    name: str


KNOWN_AGENT_CLIENTS = {
    "codex": AgentClient(key="codex", name="Codex"),
    "claude-code": AgentClient(key="claude-code", name="Claude Code"),
    "openclaw": AgentClient(key="openclaw", name="OpenClaw"),
    "vs-code": AgentClient(key="vs-code", name="VS Code"),
    "cursor": AgentClient(key="cursor", name="Cursor"),
    "slack": AgentClient(key="slack", name="Slack"),
    "ollama": AgentClient(key="ollama", name="Ollama"),
    "mcp": AgentClient(key="mcp", name="MCP"),
}

CLIENT_ALIASES = {
    "claude": "claude-code",
    "claude code": "claude-code",
    "claude-code": "claude-code",
    "claude_code": "claude-code",
    "code": "vs-code",
    "codex": "codex",
    "cursor": "cursor",
    "mcp": "mcp",
    "ollama": "ollama",
    "open claw": "openclaw",
    "open-claw": "openclaw",
    "open_claw": "openclaw",
    "openclaw": "openclaw",
    "slack": "slack",
    "visual studio code": "vs-code",
    "vs code": "vs-code",
    "vscode": "vs-code",
}


def resolve_agent_client(client_name: str | None) -> AgentClient:
    if client_name is None:
        return KNOWN_AGENT_CLIENTS["mcp"]
    normalized = " ".join(client_name.strip().lower().replace("_", " ").split())
    key = CLIENT_ALIASES.get(normalized, "mcp")
    return KNOWN_AGENT_CLIENTS[key]
