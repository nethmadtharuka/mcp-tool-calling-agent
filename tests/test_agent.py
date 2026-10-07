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


# ---------------------------------------------------------------------------
# Phase 6: hardening. LLM, MCP, tool and config failures must end in a
# controlled response or clean HTTP error, never a crash or leaked internals.
# ---------------------------------------------------------------------------

import asyncio  # noqa: E402

import pytest  # noqa: E402

from langchain_core.messages.tool import invalid_tool_call  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

import app.agent.mcp_tools as mcp_tools  # noqa: E402
from app.agent.llm import LLMError  # noqa: E402
from app.core.config import Settings  # noqa: E402


class FailingLLM:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        raise RuntimeError("upstream 503 internal-detail-xyz")


async def test_llm_failure_raises_llm_error(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FailingLLM())
    try:
        await run_agent("hi")
    except LLMError as exc:
        assert isinstance(exc.__cause__, RuntimeError)  # original kept for logs
    else:
        raise AssertionError("expected LLMError")


def test_llm_failure_returns_clean_502(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", lambda settings: FailingLLM())
    response = client.post("/api/agent/run", json={"message": "hi"})
    assert response.status_code == 502
    assert "internal-detail-xyz" not in response.text


def test_unexpected_error_returns_clean_500(monkeypatch):
    async def broken_tools(settings):
        raise RuntimeError("internal-detail-xyz")

    monkeypatch.setattr(nodes, "get_mcp_tools", broken_tools)
    response = client.post("/api/agent/run", json={"message": "hi"})
    assert response.status_code == 500
    assert "internal-detail-xyz" not in response.text


def test_missing_api_key_returns_config_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    response = client.post("/api/agent/run", json={"message": "hi"})
    assert response.status_code == 500
    assert "LLM_API_KEY" in response.json()["detail"]


def test_unsupported_provider_returns_config_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    monkeypatch.setenv("LLM_API_KEY", "not-a-real-key")
    response = client.post("/api/agent/run", json={"message": "hi"})
    assert response.status_code == 500
    assert "Unsupported LLM_PROVIDER" in response.json()["detail"]


class CrashingTool:
    name = "list_issues"

    async def ainvoke(self, args):
        raise ConnectionError("MCP server went away")


class SlowTool:
    name = "read_file"

    async def ainvoke(self, args):
        await asyncio.sleep(5)


async def test_mcp_tool_failure_is_reported_to_llm(monkeypatch):
    _use_fakes(monkeypatch, ScriptedLLM(["list_issues"]), [CrashingTool()])
    result = await run_agent("list issues")
    assert "Error executing 'list_issues': MCP server went away" in result


async def test_tool_timeout_is_reported_to_llm(monkeypatch):
    monkeypatch.setattr(nodes, "TOOL_TIMEOUT_SECONDS", 0.05)
    _use_fakes(monkeypatch, ScriptedLLM(["read_file"]), [SlowTool()])
    result = await run_agent("read a file")
    assert "Error: tool 'read_file' timed out" in result


@tool
def add_one(n: int) -> int:
    """Add one to n."""
    return n + 1


async def test_invalid_tool_arguments_are_reported_to_llm(monkeypatch):
    class BadArgsLLM(ScriptedLLM):
        async def ainvoke(self, messages):
            if not any(m.type == "tool" for m in messages):
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "add_one", "args": {"n": "not-a-number"}, "id": "c1"}],
                )
            return await super().ainvoke(messages)

    _use_fakes(monkeypatch, BadArgsLLM(["add_one"]), [add_one])
    result = await run_agent("add one")
    assert "Error executing 'add_one'" in result


async def test_malformed_tool_call_is_reported_to_llm(monkeypatch):
    class MalformedCallLLM(ScriptedLLM):
        async def ainvoke(self, messages):
            if not any(m.type == "tool" for m in messages):
                return AIMessage(
                    content="",
                    invalid_tool_calls=[
                        invalid_tool_call(
                            name="read_file", args="{not json", id="c1", error="bad JSON"
                        )
                    ],
                )
            return await super().ainvoke(messages)

    _use_fakes(monkeypatch, MalformedCallLLM([]), [])
    result = await run_agent("read a file")
    assert "Error: malformed call to 'read_file': bad JSON" in result


# --- MCP discovery: one server down must not take the others with it ---


class FakeDiscoveredTool:
    def __init__(self, name):
        self.name = name


def _fake_mcp_client(monkeypatch, github_fails):
    class FakeClient:
        def __init__(self, connections):
            self.connections = connections

        async def get_tools(self, server_name):
            if server_name == "github":
                if github_fails:
                    raise FileNotFoundError("docker not found")
                return [FakeDiscoveredTool("get_repository")]  # --read-only server
            names = ["read_file", "list_directory", "write_file", "edit_file",
                     "move_file", "create_directory"]
            return [FakeDiscoveredTool(n) for n in names]

    monkeypatch.setattr(mcp_tools, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(mcp_tools, "_tools_cache", None)


SECRET_PAT = "ghp_FAKE_TEST_TOKEN_123"


def _both_servers_settings():
    return Settings(
        llm_provider="mock", llm_model="m", llm_api_key=None,
        github_pat=SECRET_PAT, github_toolsets="repos", filesystem_mcp_enabled=True,
    )


async def test_unavailable_mcp_server_is_skipped(monkeypatch, caplog):
    _fake_mcp_client(monkeypatch, github_fails=True)
    caplog.set_level("INFO")

    tools = await mcp_tools.get_mcp_tools(_both_servers_settings())

    assert [t.name for t in tools] == ["read_file", "list_directory"]
    assert mcp_tools._tools_cache is None  # partial result not cached; retried later
    assert "github MCP server unavailable" in caplog.text
    assert SECRET_PAT not in caplog.text


async def test_readonly_protections_intact(monkeypatch):
    _fake_mcp_client(monkeypatch, github_fails=False)
    settings = _both_servers_settings()

    tools = await mcp_tools.get_mcp_tools(settings)

    names = {t.name for t in tools}
    assert names == {"get_repository", "read_file", "list_directory"}
    assert names.isdisjoint({"write_file", "edit_file", "move_file", "create_directory"})
    assert "--read-only" in mcp_tools._github_server_config(settings)["github"]["args"]
    fs_args = mcp_tools._filesystem_server_config(settings)["filesystem"]["args"]
    mounts = [a for a in fs_args if a.startswith("type=bind,")]
    assert mounts and all(m.endswith(",ro") for m in mounts)


def test_env_file_not_mounted_into_filesystem_mcp():
    args = mcp_tools._filesystem_server_config(_both_servers_settings())["filesystem"]["args"]
    mounts = [a for a in args if a.startswith("type=bind,")]
    mounted_names = {m.split(",dst=")[1].removesuffix(",ro").rsplit("/", 1)[1] for m in mounts}

    assert "README.md" in mounted_names
    assert ".env.example" in mounted_names  # placeholders only, safe to read
    assert not any(name.lower() == ".env" for name in mounted_names)
    # No mount may expose the project root itself (that would include .env).
    assert not any(f"src={mcp_tools._PROJECT_ROOT}," in m for m in mounts)


# Opt-in: talks to the real mcp/filesystem container. Run with
#   DOCKER_TESTS=1 pytest -k real_filesystem_mcp
@pytest.mark.skipif(os.getenv("DOCKER_TESTS") != "1", reason="set DOCKER_TESTS=1 to run")
async def test_real_filesystem_mcp_hides_env():
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(mcp_tools._filesystem_server_config(_both_servers_settings()))
    tools = {t.name: t for t in await client.get_tools(server_name="filesystem")}
    read = tools.get("read_text_file") or tools["read_file"]
    root = "/projects/mcp-tool-calling-agent"

    assert "Production-Oriented AI Engineering Agent" in str(await read.ainvoke({"path": f"{root}/README.md"}))

    for name in [".env", ".ENV", ".Env", "app/../.env"]:
        # The server reports errors as text, not exceptions. Reduce to a bool
        # so a failure can never print the file's contents in the report.
        hidden = "ENOENT" in str(await read.ainvoke({"path": f"{root}/{name}"}))
        assert hidden, f"{name} is readable inside the container"


# ---------------------------------------------------------------------------
# Phase 7: the Gemini provider is lazily imported inside get_llm, so a
# missing langchain-google-genai install only shows up at request time.
# This catches it in the suite instead. No network: construction only.
# ---------------------------------------------------------------------------


def test_gemini_provider_imports_and_constructs():
    from langchain_google_genai import ChatGoogleGenerativeAI

    from app.agent.llm import get_llm

    settings = Settings(
        llm_provider="gemini", llm_model="gemini-flash-lite-latest",
        llm_api_key="fake-key-for-test", github_pat=None,
        github_toolsets="repos", filesystem_mcp_enabled=False,
    )
    assert isinstance(get_llm(settings), ChatGoogleGenerativeAI)
