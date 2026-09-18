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

    def invoke(self, messages):
        return AIMessage(content="An AI agent perceives, decides, and acts.")


class FakeToolCallingLLM:
    """First turn: asks to call get_project_info. Second turn (tool result
    present): answers using that result. Simulates a real tool-calling LLM."""

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        already_ran_tool = any(m.type == "tool" for m in messages)
        if already_ran_tool:
            tool_result = next(m.content for m in messages if m.type == "tool")
            return AIMessage(content=f"Based on the tool: {tool_result}")
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_project_info", "args": {}, "id": "call_1"}],
        )


def test_no_tool_needed(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FakeNoToolLLM())
    result = run_agent("What is an AI agent?")
    assert result == "An AI agent perceives, decides, and acts."


def test_tool_call_required(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FakeToolCallingLLM())
    result = run_agent("What is this project's name?")
    assert "Production-Oriented AI Engineering Agent" in result


def test_graph_execution_directly():
    result = run_agent("ping")
    assert "ping" in result
