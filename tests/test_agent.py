import os

os.environ.setdefault("LLM_PROVIDER", "mock")

from langchain_core.messages import AIMessage

from fastapi.testclient import TestClient

import app.agent.graph as graph
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


# ---------------------------------------------------------------------------
# Phase 5: multi-step. The LLM chains several tool calls - across different
# MCP servers - feeding each result back before deciding the next step.
# ---------------------------------------------------------------------------


class FakeMcpTool:
    """Stands in for a tool discovered from an MCP server; records calls."""

    def __init__(self, name, result, calls):
        self.name = name
        self._result = result
        self._calls = calls

    async def ainvoke(self, args):
        self._calls.append(self.name)
        return self._result


class ScriptedLLM:
    """Requests each planned tool in turn, one per LLM turn, then answers
    with every tool result it has seen. Records each turn's history."""

    def __init__(self, plan):
        self.plan = plan
        self.seen = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.seen.append(list(messages))
        results = [m.content for m in messages if m.type == "tool"]
        if len(results) < len(self.plan):
            name = self.plan[len(results)]
            return AIMessage(
                content="",
                tool_calls=[{"name": name, "args": {}, "id": f"call_{len(results)}"}],
            )
        return AIMessage(content="Summary: " + " | ".join(results))


def _use_fakes(monkeypatch, llm, mcp_tools):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: llm)

    async def fake_get_mcp_tools(settings):
        return mcp_tools

    monkeypatch.setattr(nodes, "get_mcp_tools", fake_get_mcp_tools)


async def test_multiple_sequential_tool_calls(monkeypatch):
    calls = []
    tools = [
        FakeMcpTool("list_directory", "README.md, app/", calls),
        FakeMcpTool("read_file", "# Production-Oriented AI Engineering Agent", calls),
    ]
    llm = ScriptedLLM(["list_directory", "read_file"])
    _use_fakes(monkeypatch, llm, tools)

    result = await run_agent("List the files, then read README.md")

    assert calls == ["list_directory", "read_file"]
    # LLM ran 3 times, and each turn saw the previous tool's result.
    assert len(llm.seen) == 3
    assert [m.content for m in llm.seen[1] if m.type == "tool"] == ["README.md, app/"]
    assert result == "Summary: README.md, app/ | # Production-Oriented AI Engineering Agent"


async def test_tools_from_different_mcp_servers_in_one_request(monkeypatch):
    calls = []
    tools = [
        FakeMcpTool("read_file", "README says Phase 4", calls),  # filesystem server
        FakeMcpTool("get_repository", "repo: mcp-tool-calling-agent", calls),  # github server
    ]
    _use_fakes(monkeypatch, ScriptedLLM(["read_file", "get_repository"]), tools)

    result = await run_agent("Read README.md and then check the GitHub repository")

    assert calls == ["read_file", "get_repository"]
    assert "README says Phase 4" in result
    assert "repo: mcp-tool-calling-agent" in result


class AlwaysCallsToolLLM:
    """Never produces a final answer - would loop forever without a cap."""

    def __init__(self):
        self.turns = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.turns += 1
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_project_info", "args": {}, "id": f"call_{self.turns}"}],
        )


async def test_step_limit_stops_infinite_tool_loop(monkeypatch):
    llm = AlwaysCallsToolLLM()
    monkeypatch.setattr(nodes, "get_llm", lambda settings: llm)

    result = await run_agent("loop forever")

    assert f"limit of {graph.MAX_TOOL_STEPS} tool steps" in result
    assert llm.turns == graph.MAX_TOOL_STEPS + 1  # 8 round trips + the turn that hit the cap
