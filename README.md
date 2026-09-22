# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 3 — GitHub MCP.** The agent can now discover and call tools from
a separate GitHub MCP server process, in addition to its local Phase 2
tool. Read-only only.

## Current Architecture

```text
Client
  ↓
FastAPI          (app/api/routes.py, async)
  ↓
LangGraph        (app/agent/graph.py: START -> agent -> (tool?) -> END)
  ↓
LLM              (app/agent/llm.py: mock or OpenAI, chosen by env var)
  ↓
local tool (app/agent/tools.py) or GitHub MCP tool (app/agent/mcp_tools.py)
  ↓
Response
```

## Future Architecture (not implemented yet)

```text
Filesystem MCP
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
│   ├── llm.py             LLM provider abstraction (mock / openai)
│   ├── tools.py            The Phase 2 local tool: get_project_info()
│   └── mcp_tools.py         Phase 3: discovers tools from github-mcp-server
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
key. To use a real model, set:

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-...
```

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

## Phase 3 — GitHub MCP

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

Filesystem MCP will be introduced in Phase 4.
