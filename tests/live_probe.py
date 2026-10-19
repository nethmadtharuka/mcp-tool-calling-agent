"""Runs INSIDE the agent container or pod - piped to `python -` by
tests/test_live_docker.py and tests/test_live_k8s.py - so it uses the
agent's own code, config and network path to the real MCP servers.

Prints one JSON object of booleans and counts on the last line: never
file contents or secret values. No LLM is called: a scripted fake drives
the real graph, so no API cost.
"""

import asyncio
import dataclasses
import json
import logging

from langchain_core.messages import AIMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

import app.agent.graph as graph
import app.agent.mcp_tools as mcp_tools
import app.agent.nodes as nodes
from app.core.config import get_settings

logging.disable(logging.CRITICAL)

ROOT = "/projects/mcp-tool-calling-agent"
FS_WRITE = {"write_file", "edit_file", "move_file", "create_directory"}
GH_WRITE_WORDS = ("create", "update", "delete", "merge", "push", "add_", "fork",
                  "write", "edit", "assign", "dismiss", "request_copilot")
# How the filesystem server reports a path it won't or can't read.
DENIED = ("ENOENT", "Access denied", "Parent directory does not exist", "outside allowed")


def denied(result) -> bool:
    text = str(result)
    return any(d in text for d in DENIED) and "LLM_API_KEY" not in text


class ScriptedLLM:
    """Requests one planned tool call per turn, then answers. Keeps tool
    results in memory only."""

    def __init__(self, plan):
        self.plan, self.results, self.bound = plan, [], set()

    def bind_tools(self, tools):
        self.bound = {t.name for t in tools}
        return self

    async def ainvoke(self, messages):
        self.results = [m.content for m in messages if m.type == "tool"]
        if len(self.results) < len(self.plan):
            name, args = self.plan[len(self.results)]
            return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{len(self.results)}"}])
        return AIMessage(content="done")


class AlwaysCallsToolLLM:
    def __init__(self):
        self.turns = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.turns += 1
        return AIMessage(content="", tool_calls=[{"name": "get_project_info", "args": {}, "id": f"c{self.turns}"}])


async def main():
    settings = get_settings()
    out = {"github_enabled": settings.github_mcp_enabled}

    # Discovery exactly as the agent does it (allowlist applied).
    names = {t.name for t in await mcp_tools.get_mcp_tools(settings)}
    out["discovered"] = len(names)
    out["fs_read_tools_present"] = "read_file" in names or "read_text_file" in names
    out["fs_write_tools_offered"] = sorted(names & FS_WRITE)

    # Raw filesystem client, bypassing the allowlist, to test the server itself.
    client = MultiServerMCPClient(mcp_tools._filesystem_server_config(settings))
    fs = {t.name: t for t in await client.get_tools(server_name="filesystem")}
    read = fs.get("read_text_file") or fs["read_file"]
    out["readme_readable"] = "Production-Oriented" in str(await read.ainvoke({"path": f"{ROOT}/README.md"}))
    out["secret_paths_denied"] = {
        p: denied(await read.ainvoke({"path": p if p.startswith("/") else f"{ROOT}/{p}"}))
        for p in [".env", ".ENV", ".Env", "app/../.env", "ENV~1", "../.env", ".git/config",
                  ".venv/pyvenv.cfg", "/proc/self/environ", "/proc/1/environ"]
    }
    listing = str(await fs["list_directory"].ainvoke({"path": ROOT}))
    out["env_in_listing"] = any(line.split()[-1] in (".env", ".git", ".venv")
                                for line in listing.splitlines() if line.split())
    out["write_file_erofs"] = "EROFS" in str(await fs["write_file"].ainvoke({"path": f"{ROOT}/probe.txt", "content": "x"}))
    out["edit_file_erofs"] = "EROFS" in str(await fs["edit_file"].ainvoke(
        {"path": f"{ROOT}/run.py", "edits": [{"oldText": "uvicorn", "newText": "x"}]}))

    # GitHub: --read-only must hold even when the client asks for writes.
    if settings.github_mcp_enabled:
        cfg = mcp_tools._github_server_config(settings)
        cfg["github"]["headers"].update({"X-MCP-Readonly": "false", "X-MCP-Toolsets": "all"})
        gh = [t.name for t in await MultiServerMCPClient(cfg).get_tools(server_name="github")]
        out["github_tools_readonly_false"] = len(gh)
        out["github_write_tools_readonly_false"] = [n for n in gh if any(w in n for w in GH_WRITE_WORDS)]

    # The real graph + tool_node + MCP servers, multi-step, scripted LLM.
    plan = [
        ("list_allowed_directories", {}),
        ("read_file", {"path": f"{ROOT}/README.md"}),
        ("read_file", {"path": f"{ROOT}/.env"}),
        ("write_file", {"path": f"{ROOT}/x.txt", "content": "x"}),
    ]
    if settings.github_mcp_enabled:
        plan.append(("search_repositories", {"query": "repo:github/github-mcp-server"}))
    llm = ScriptedLLM(plan)
    nodes.get_llm = lambda s: llm
    answer = await graph.run_agent("multi-step across the MCP servers")
    r = llm.results
    out["graph_answered"] = answer == "done"
    out["graph_write_tools_bound"] = sorted(llm.bound & FS_WRITE)
    out["graph_list_dirs_ok"] = ROOT in r[0]
    out["graph_read_readme_ok"] = "Production-Oriented" in r[1]
    out["graph_read_env_denied"] = denied(r[2])
    out["graph_write_refused"] = r[3] == "Error: unknown tool 'write_file'"
    if settings.github_mcp_enabled:
        out["graph_github_search_ok"] = "github-mcp-server" in r[4] and not r[4].startswith("Error")

    forever = AlwaysCallsToolLLM()
    nodes.get_llm = lambda s: forever
    stopped = await graph.run_agent("loop")
    out["step_limit_stopped"] = f"limit of {graph.MAX_TOOL_STEPS} tool steps" in stopped
    out["step_limit_turns"] = forever.turns
    out["max_tool_steps"] = graph.MAX_TOOL_STEPS

    # A dead MCP server must be skipped, not crash discovery (Phase 6).
    mcp_tools._tools_cache = None
    broken = dataclasses.replace(settings, filesystem_mcp_url="http://127.0.0.1:9/mcp")
    try:
        names = {t.name for t in await mcp_tools.get_mcp_tools(broken)}
        out["fs_down_handled"] = not (names & {"read_file", "read_text_file"})
        out["fs_down_not_cached"] = mcp_tools._tools_cache is None
    except Exception as exc:  # noqa: BLE001 - the point is that this mustn't happen
        out["fs_down_handled"] = f"raised {type(exc).__name__}"

    print(json.dumps(out))


asyncio.run(main())
