# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 4 — Filesystem MCP.** The agent can now discover and call tools
from two separate MCP servers - GitHub and a filesystem server scoped to
this project directory, both read-only - on top of its local Phase 2
tool. It also supports Google Gemini as an LLM provider alongside OpenAI
and the mock model, so the full tool-calling loop can be tested for
free.

## Current Architecture

```text
Client
  ↓
FastAPI          (app/api/routes.py, async)
  ↓
LangGraph        (app/agent/graph.py: START -> agent -> (tool?) -> END)
  ↓
LLM              (app/agent/llm.py: mock, OpenAI, or Gemini, chosen by env var)
  ↓
local tool (app/agent/tools.py), GitHub MCP tool, or Filesystem MCP tool
(app/agent/mcp_tools.py)
  ↓
Response
```

## Future Architecture (not implemented yet)

```text
Docker
Kubernetes
GCP
```

## Project Structure

```text
app/
├── main.py            FastAPI app
├── api/routes.py       /health and /api/agent/run
├── agent/
│   ├── state.py        LangGraph state (AgentState: messages history)
│   ├── nodes.py         agent_node (calls the LLM) + tool_node (runs tools)
│   ├── graph.py          Builds the graph: agent -> (tool?) -> agent -> END
│   ├── llm.py             LLM provider abstraction (mock / openai / gemini)
│   ├── tools.py            The Phase 2 local tool: get_project_info()
│   └── mcp_tools.py         Discovers tools from github-mcp-server (Phase 3)
│                             and mcp/filesystem (Phase 4)
└── core/config.py      Env-based settings, fails clearly if misconfigured
tests/                 pytest suite (uses the mock LLM, no API key needed)
run.py                 Dev server entrypoint
```

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

The default `.env` uses `LLM_PROVIDER=mock`, so the app runs with no API
key. To use a real model, set one of:

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```

```bash
LLM_PROVIDER=gemini
LLM_MODEL=gemini-flash-lite-latest
LLM_API_KEY=<your Google AI Studio API key>
```

Gemini is a good default for local testing: Google AI Studio issues a
free API key with no billing setup, so the full tool-calling loop can be
exercised end-to-end at no cost. `gemini-flash-lite-latest` is used
because it supports `bind_tools()`/real tool calling and isn't subject to
the very low daily quota some pinned Gemini model versions have on the
free tier.

If `LLM_PROVIDER` is set to anything other than `mock` and `LLM_API_KEY`
is missing, the server returns a clear configuration error instead of a
stack trace.

## Run

```bash
python run.py
```

- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Test

```bash
pytest
```

Tests run against the mock LLM, so no API key or network access is
required.

## Example Request

```bash
curl -X POST http://localhost:8000/api/agent/run \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Hello, what can you do?\"}"
```

```json
{
  "response": "[mock response] You said: Hello, what can you do?"
}
```

## Phase 2 — Tool Calling

### Concepts

- **LLM** - the model that reads text and generates text. On its own it
  can't run code or fetch live data.
- **Tool** - a normal Python function, described to the LLM with a name,
  a description, and an argument schema (here, `get_project_info()`,
  defined with LangChain's `@tool` decorator in `app/agent/tools.py`).
- **Tool calling** - the LLM is shown the tool's schema and, instead of
  answering in plain text, can reply "call this tool with these
  arguments." The LLM never executes anything itself - it only *requests*
  a call. Our code executes the real Python function and hands the
  result back.
- **LangGraph** - the state machine that wires this into a loop: ask the
  LLM, check if it asked for a tool, run the tool if so, ask the LLM
  again with the result, repeat until it answers in plain text.

### Architecture

```text
START
  |
  v
agent (calls the LLM with the full message history)
  |
  +-- no tool_calls -> END (final answer)
  |
  +-- tool_calls present
        |
        v
      tool (executes get_project_info(), wraps result in a ToolMessage)
        |
        v
      agent (LLM sees the tool result, produces the final answer)
        |
        v
      END
```

### The message history

`AgentState.messages` is a list that grows through one request:

1. `HumanMessage("What is this project's name?")`
2. `AIMessage(tool_calls=[{"name": "get_project_info", ...}])` - agent
   decides it needs the tool instead of answering.
3. `ToolMessage("This project is the Production-Oriented AI Engineering
   Agent...")` - the real result of running `get_project_info()`.
4. `AIMessage("This project is called the Production-Oriented AI
   Engineering Agent.")` - the LLM's final answer, written using the
   tool result.

If the LLM doesn't need the tool, the list is just
`[HumanMessage, AIMessage]` and the graph goes straight to `END`.

### Running it

Same as Phase 1: `python run.py`, then `POST /api/agent/run`. Watch the
terminal - `app/agent/nodes.py` logs each step with the stdlib `logging`
module (`Calling LLM...`, `LLM requested tool call(s): [...]`,
`Executing tool '...'`, `Tool '...' result: ...`, or `LLM answered
directly, no tool call requested`).

### Postman

`POST http://localhost:8000/api/agent/run`, `Content-Type: application/json`.

No tool needed:
```json
{ "message": "What is an AI agent?" }
```

Tool needed (watch the server log for the tool-call sequence):
```json
{ "message": "What is this project's name?" }
```

The response shape is unchanged: `{ "response": "..." }`.

### Testing without a paid API

`tests/test_agent.py` includes two fake chat models
(`FakeNoToolLLM`, `FakeToolCallingLLM`) swapped in with `monkeypatch` to
deterministically exercise both branches of the graph. Run with `pytest`.
To verify against a real model, set `LLM_PROVIDER=openai` and a real
`LLM_API_KEY` in `.env`, then use the Postman requests above.

## Phase 3 — GitHub MCP + Gemini LLM support

### What changed vs. Phase 2

Phase 2's tool (`get_project_info`) is a Python function we wrote,
executed in-process. Phase 3 adds tools that come from a *separate
process* - GitHub's official MCP server - discovered at runtime instead
of hand-written:

```text
PHASE 2                                PHASE 3
LLM                                     LLM
 |                                       |
tool_calls detected                     tool_calls detected
 |                                       |
tool_fn.invoke(args)  (in-process)      MCP Client --stdio--> github-mcp-server --HTTPS--> GitHub API
 |                                       |
ToolMessage                             ToolMessage (same shape)
 |                                       |
LLM                                     LLM
```

Both kinds of tool end up bound to the LLM and executed the same way
(`agent_node`/`tool_node` in `app/agent/nodes.py` don't care which is
which) - that's the point of MCP: a standard shape for "here's a tool,"
regardless of where it actually runs.

Because a GitHub MCP call is real network I/O, the whole request path is
now `async`: `app/api/routes.py`'s `run()`, `app/agent/graph.py`'s
`run_agent()`, and both graph nodes.

### Running the GitHub MCP server

Requires Docker Desktop running locally. We don't start it by hand - the
MCP client (`app/agent/mcp_tools.py`) launches
`docker run -i --rm ghcr.io/github/github-mcp-server stdio --read-only`
as a subprocess and talks to it over stdio the first time a GitHub tool
is needed.

`--read-only` is hardcoded in `mcp_tools.py`, not an env var - the agent
cannot create, update, delete, merge, or push anything on GitHub, and
that can't be changed by misconfiguring `.env`.

### Setup

```bash
GITHUB_PERSONAL_ACCESS_TOKEN=<a fine-grained PAT, read-only, scoped to specific repos>
GITHUB_TOOLSETS=repos,issues,pull_requests
```

If `GITHUB_PERSONAL_ACCESS_TOKEN` is unset, GitHub MCP is simply skipped
(logged, not an error) - the agent still works with just the local
Phase 2 tool. This keeps `pytest` and mock-mode runs working with no
Docker and no GitHub account.

### Postman

Same endpoint, `POST http://localhost:8000/api/agent/run`.

Local tool / no GitHub needed (regression check):
```json
{ "message": "What is this project's name?" }
```

GitHub MCP tool:
```json
{ "message": "List the open issues in octocat/Hello-World" }
```

Watch server logs - same log lines as Phase 2
(`Calling LLM...` / `LLM requested tool call(s): [...]` /
`Executing tool '...'` / `Tool '...' result: ...`), because MCP tools
flow through the identical `tool_node` code path.

### Testing without Docker or a real GitHub token

`tests/test_agent.py` adds `FakeGithubMcpTool` + `FakeGithubToolCallingLLM`,
monkeypatched in the same way as Phase 2's fakes, so the "LLM picks an
MCP tool, tool executes, result comes back" loop is proven without
spawning a container or calling GitHub. Run with `pytest`.

### Gemini LLM provider

`LLM_PROVIDER=gemini` (`app/agent/llm.py`) uses LangChain's
`ChatGoogleGenerativeAI`, which supports `.bind_tools()` and real tool
calling the same way `ChatOpenAI` does - `agent_node`/`tool_node` don't
need to know or care which provider is behind `get_llm()`.

One real difference: OpenAI/mock return `AIMessage.content` as a plain
string, but Gemini returns it as a list of content blocks (e.g.
`[{"type": "text", "text": "..."}]`). `run_agent()` in
`app/agent/graph.py` normalizes both shapes into a plain string before
it reaches the FastAPI response model, so `/api/agent/run` always
returns `{ "response": "<string>" }` regardless of provider.

**Verified live** with `LLM_PROVIDER=gemini` /
`LLM_MODEL=gemini-flash-lite-latest`, through the actual FastAPI
endpoint (Postman and curl), Docker Desktop running the real
`github-mcp-server` container, and a real GitHub PAT:

- Gemini correctly requests GitHub MCP tools (e.g. `search_repositories`)
  when a prompt needs one, and answers directly when it doesn't.
- Tool results (real GitHub API data) are fed back to Gemini and used in
  its final answer.
- `/api/agent/run` returns real data end-to-end, e.g. asking for the most
  starred repo in the `torvalds` org correctly returned `torvalds/linux`
  with its live star count.

## Phase 4 — Filesystem MCP

### What changed vs. Phase 3

Same pattern as GitHub MCP, one more entry in the connections dict:
`app/agent/mcp_tools.py` now passes both `github` and `filesystem` server
configs to a single `MultiServerMCPClient`, and `get_mcp_tools()` returns
the combined tool list from whichever servers are enabled.
`agent_node`/`tool_node` need no changes - they already treat "a tool" as
a tool regardless of where it came from.

### Server and mount

Uses the official `mcp/filesystem` image
(`modelcontextprotocol/servers`), launched the same way as
`github-mcp-server`: `app/agent/mcp_tools.py` runs
`docker run -i --rm --mount type=bind,src=<repo root>,dst=/projects/mcp-tool-calling-agent,ro mcp/filesystem /projects/mcp-tool-calling-agent`.

Two things are hardcoded, not env-configurable:

- The mount source is computed from `__file__` at runtime (always this
  repo's own root, wherever it's checked out) - it can never be pointed
  at another directory by editing `.env`.
- The mount uses the Docker `,ro` flag, so writes fail at the OS level
  (`EROFS: read-only file system`) even if a write tool were somehow
  invoked.

### Read-only tool allowlist

Unlike `github-mcp-server`, the filesystem server has no `--read-only`
flag of its own - it always exposes mutating tools
(`write_file`, `edit_file`, `move_file`, `create_directory`). Those are
filtered out in `mcp_tools.py` before the tool list ever reaches
`bind_tools()`, so the LLM can't even see or request them. What's left,
and confirmed exposed by the pulled image:
`read_file`, `read_multiple_files`, `list_directory`, `directory_tree`,
`search_files`, `get_file_info`, `list_allowed_directories`. (The
allowlist also includes the newer
`read_text_file`/`read_media_file`/`list_directory_with_sizes` names in
case a future image update renames `read_file`.)

This is defense in depth on top of the Docker mount above: two
independent layers (LLM never sees the write tools; the mount rejects
writes at the kernel level even if it did) rather than relying on either
alone.

### Setup

```bash
FILESYSTEM_MCP_ENABLED=true
```

Off by default, unlike GitHub MCP (which is gated by whether a PAT is
set) - the filesystem server needs no secret, so it needs an explicit
opt-in instead, keeping `pytest` and default dev runs Docker-free unless
asked for.

### Postman

Same endpoint, `POST http://localhost:8000/api/agent/run`.

```json
{ "message": "Use the filesystem tool to read requirements.txt and list its first 3 lines." }
```

**Verified live**, same way as Phase 3's Gemini + GitHub MCP check:
Gemini called `list_allowed_directories` then `read_file` on this
project's actual `requirements.txt`, and answered using the real file
contents. A direct call to `write_file` (bypassing the app-level
allowlist entirely, to test the mount itself) failed with
`EROFS: read-only file system`, confirming the OS-level enforcement
independent of the Python filtering.

### Testing without Docker

`tests/conftest.py` forces `FILESYSTEM_MCP_ENABLED=false` for every test
run, the same way it forces GitHub MCP off, so `pytest` never spawns
either container.

No new dependencies were needed for this phase - `langchain-mcp-adapters`
already supported multiple servers in one `MultiServerMCPClient`.
