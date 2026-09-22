import os

os.environ.setdefault("LLM_PROVIDER", "mock")

from langchain_core.messages import AIMessage

from fastapi.testclient import TestClient

import app.agent.nodes as nodes
from app.agent.graph import run_agent
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# HTTP-level tests using the built-in MockChatModel (default LLM_PROVIDER).
# It never returns tool_calls, so these only exercise the "no tool" path.
# TestClient handles the now-async /api/agent/run endpoint transparently.
# ---------------------------------------------------------------------------


def test_agent_run_returns_mock_response():
    response = client.post("/api/agent/run", json={"message": "hello"})
    assert response.status_code == 200
    assert "hello" in response.json()["response"]


def test_agent_run_rejects_empty_message():
    response = client.post("/api/agent/run", json={"message": ""})
    assert response.status_code == 422


def test_agent_run_rejects_missing_field():
    response = client.post("/api/agent/run", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Deterministic fake LLMs to prove the tool-calling loop itself works,
# without paying for a real API call.
# ---------------------------------------------------------------------------


class FakeNoToolLLM:
    """Always answers directly - simulates a question the LLM doesn't need a tool for."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="An AI agent perceives, decides, and acts.")


class FakeToolCallingLLM:
    """First turn: asks to call get_project_info. Second turn (tool result
    present): answers using that result. Simulates a real tool-calling LLM."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        already_ran_tool = any(m.type == "tool" for m in messages)
        if already_ran_tool:
            tool_result = next(m.content for m in messages if m.type == "tool")
            return AIMessage(content=f"Based on the tool: {tool_result}")
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_project_info", "args": {}, "id": "call_1"}],
        )


async def test_no_tool_needed(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FakeNoToolLLM())
    result = await run_agent("What is an AI agent?")
    assert result == "An AI agent perceives, decides, and acts."


async def test_tool_call_required(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FakeToolCallingLLM())
    result = await run_agent("What is this project's name?")
    assert "Production-Oriented AI Engineering Agent" in result


async def test_graph_execution_directly():
    result = await run_agent("ping")
    assert "ping" in result


# ---------------------------------------------------------------------------
# Phase 3: prove a GitHub MCP tool is selected and executed, without a real
# Docker container or GitHub token. A fake MCP tool stands in for the real
# one discovered from github-mcp-server - same shape (name + ainvoke), just
# not talking to a subprocess.
# ---------------------------------------------------------------------------


class FakeGithubMcpTool:
    name = "list_issues"

    async def ainvoke(self, args):
        return f"2 open issues in {args.get('repo', 'unknown repo')}"


class FakeGithubToolCallingLLM:
    """First turn: asks to call the GitHub MCP tool. Second turn: answers
    using its result."""

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        already_ran_tool = any(m.type == "tool" for m in messages)
        if already_ran_tool:
            tool_result = next(m.content for m in messages if m.type == "tool")
            return AIMessage(content=f"Here's what I found: {tool_result}")
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "list_issues",
                    "args": {"owner": "octocat", "repo": "Hello-World"},
                    "id": "call_1",
                }
            ],
        )


async def test_mcp_tool_call_required(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FakeGithubToolCallingLLM())

    async def fake_get_mcp_tools(settings):
        return [FakeGithubMcpTool()]

    monkeypatch.setattr(nodes, "get_mcp_tools", fake_get_mcp_tools)

    result = await run_agent("List open issues in octocat/Hello-World")
    assert "2 open issues in Hello-World" in result
