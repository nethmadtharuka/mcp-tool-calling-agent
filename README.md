# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 6 — Basic Hardening.** The agent chains several tool calls per
request (Phase 5) across its local Phase 2 tool and two read-only MCP
servers - GitHub and a filesystem server scoped to this project
directory, with `.env` hidden from it. LLM, MCP, tool and configuration
failures now end in a controlled response or a clean HTTP error instead
of a crash, and secrets are kept out of logs and API errors. Supported
LLM providers: Google Gemini, OpenAI, and the mock model.

## Current Architecture

```text
Client
  ↓
FastAPI          (app/api/routes.py, async)
  ↓
LangGraph        (app/agent/graph.py: agent <-> tool loop, max 8 tool steps)
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
Docker Compose   (Phase 7b: MCP servers as separate containers over HTTP)
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
│   ├── graph.py          Builds the graph: agent <-> tool loop, step limit
│   ├── llm.py             LLM provider abstraction (mock / openai / gemini)
│   ├── tools.py            The Phase 2 local tool: get_project_info()
│   └── mcp_tools.py         Discovers tools from github-mcp-server (Phase 3)
│                             and mcp/filesystem (Phase 4); one failing
│                             server doesn't take down the others (Phase 6)
└── core/config.py      Env-based settings, fails clearly if misconfigured
tests/                 pytest suite (uses the mock LLM, no API key needed)
run.py                 Dev server entrypoint
requirements.txt       Runtime dependencies, pinned (installed in the image)
requirements-dev.txt   Runtime + test dependencies, pinned
Dockerfile             Agent image (Phase 7)
.dockerignore          Allowlist: only app/ and requirements.txt enter the build
```

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements-dev.txt   # runtime + test dependencies
cp .env.example .env
```

All dependency versions are pinned. `requirements.txt` holds only what
the app needs at runtime (and is all the Docker image installs);
`requirements-dev.txt` adds `pytest`, `pytest-asyncio` and `httpx`.

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

## Docker

Phase 7a containerizes the agent itself. MCP servers are not wired up
inside the container yet (that's Phase 7b), so run it with
`LLM_PROVIDER=mock` or a real LLM, without MCP.

```bash
docker build -t mcp-tool-calling-agent .

docker run --rm --name agent   -p 127.0.0.1:8000:8000   --read-only --tmpfs /tmp   --cap-drop ALL --security-opt no-new-privileges   -e LLM_PROVIDER=mock   mcp-tool-calling-agent
```

Then `curl http://127.0.0.1:8000/health`. `docker ps` shows the
container's health check status.

- **Port**: published on `127.0.0.1` only, so it isn't reachable from
  other machines on your network. Inside the container uvicorn binds
  `0.0.0.0`, which is required for Docker port publishing to work.
- **Non-root**: the app runs as user `app` (uid 10001). The code is owned
  by root, so the app can't modify it.
- **Read-only**: `--read-only` makes the container's root filesystem
  read-only; `--tmpfs /tmp` gives it an in-memory scratch directory.
- **No secrets in the image**: `.dockerignore` is an allowlist (only
  `app/` and `requirements.txt` are sent to the build), so `.env`, `.git`
  and `.venv` never reach the build context. Configuration comes from
  environment variables at runtime.
- **Real LLM**: pass `--env-file .env` instead of `-e LLM_PROVIDER=mock`.
  Until Phase 7b, the container has no way to start the MCP servers: if
  `.env` sets `GITHUB_PERSONAL_ACCESS_TOKEN` or
  `FILESYSTEM_MCP_ENABLED=true`, they are logged as unavailable and
  skipped (Phase 6 failure isolation), and the agent answers without them.
  Values passed with `--env-file` are visible to anyone who can run
  `docker inspect` on this machine.
- **Base image**: `python:3.13-slim`, pinned by digest in the
  `Dockerfile`. To update it, pull the new tag and replace the digest.

## Test

```bash
pytest
```

Tests run against the mock LLM and fake tools/MCP servers, so no API
key, Docker, or network access is required.

One opt-in test starts the real `mcp/filesystem` container and checks
that `README.md` is readable while `.env` is not (requires Docker):

```bash
DOCKER_TESTS=1 pytest -k real_filesystem_mcp
```

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
`Executing tool '...'`, `Tool '...' returned N chars`, or `LLM answered
directly, no tool call requested`). Since Phase 6 only the *length* of a
tool result is logged, never its content - see Phase 6 below.

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
`Executing tool '...'` / `Tool '...' returned N chars`), because MCP tools
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
`docker run -i --rm --mount type=bind,src=<repo root>/<entry>,dst=/projects/mcp-tool-calling-agent/<entry>,ro ... mcp/filesystem /projects/mcp-tool-calling-agent`,
with one `--mount` per top-level entry of the repo, except `.env`
(see Phase 6 - `.env` protection).

Two things are hardcoded, not env-configurable:

- The mount sources are computed from `__file__` at runtime (always this
  repo's own root, wherever it's checked out) - they can never be pointed
  at another directory by editing `.env`.
- Every mount uses the Docker `,ro` flag, so writes fail at the OS level
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

## Phase 5 — Multi-step Agent

### What changed vs. Phase 4

The `tool -> agent` edge in `app/agent/graph.py` already looped, so the
LLM can call a tool, read the result, call another tool, and so on
before answering - e.g. `list_directory`, then `read_file` on what it
found, then a GitHub tool, all in one request. Each tool result is
appended to the message history, so every LLM turn sees everything
gathered so far.

```text
START -> agent -> (tool_calls?) -> tool -> agent -> (tool_calls?) -> tool -> ... -> agent -> END
```

### Multiple MCP servers in one run

Tools from the local Phase 2 tool, GitHub MCP and Filesystem MCP are
bound to the LLM together, so a single request can mix them freely
(e.g. read `README.md` from the filesystem server, then look up the repo
on GitHub). `tool_node` doesn't care which server a tool came from.

### Step limit: `MAX_TOOL_STEPS = 8`

A model that never stops requesting tools would otherwise loop forever.
`app/agent/graph.py` caps a request at **8 agent -> tool round trips**
(LangGraph `recursion_limit = 2 * MAX_TOOL_STEPS + 1`: two nodes per
round trip plus the final answering turn). When the cap is hit,
`GraphRecursionError` is caught and the API returns a normal `200`
response:

```json
{ "response": "Stopped: reached the limit of 8 tool steps without a final answer." }
```

The limit is a hardcoded constant, not an env var.

### Testing

`tests/test_agent.py` uses a scripted fake LLM and fake MCP tools to
prove: two sequential tool calls where each turn sees the previous
result; tools from two different MCP servers in one request; and an LLM
that always requests a tool being stopped after exactly 8 round trips.

## Phase 6 — Basic Hardening

### Error handling

| Failure | Behavior |
|---|---|
| Missing `LLM_API_KEY` / unsupported `LLM_PROVIDER` | `500` with a clear configuration message (no secret in it) |
| LLM provider call fails (network, auth, quota, model error) | `agent_node` raises `LLMError`; API returns `502` with a generic message, full traceback in the server log |
| Any other unexpected error | `500` with a generic message, full traceback in the server log |
| An MCP server is unavailable (Docker down, image missing, handshake fails or takes > 60s) | Logged as a warning and skipped; the agent keeps working with the remaining tools |
| A tool raises (bad arguments, MCP tool failure, unexpected exception) | Error text is returned to the LLM as the tool result, so it can recover or explain |
| A tool takes longer than 60s | Cancelled; `Error: tool '...' timed out after 60s` is returned to the LLM |
| Malformed tool call (provider couldn't parse the arguments) | Reported back to the LLM as an error tool result so it can retry; still counts toward `MAX_TOOL_STEPS` |
| Unknown tool name | `Error: unknown tool '...'` returned to the LLM |

API errors never include raw exception text, which could carry internal
details; that only goes to the server log. The success response shape is
unchanged: `{ "response": "..." }`.

MCP discovery results are cached only when every enabled server
succeeded, so a server that was down is retried on later calls instead
of staying missing until restart.

### Safe logging

Logged: each LLM call, requested tool names, tool execution, tool
failures/timeouts, malformed tool calls, unavailable MCP servers, LLM
failures, and the step limit being reached.

Never logged: `LLM_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN`, or tool
result *contents* - only their length (`Tool '...' returned N chars`).
Tool results can be file contents read via Filesystem MCP, so logging
them could copy file data into server logs.

### `.env` protection

`.env` holds the LLM API key and GitHub PAT, and it lives in the project
root - which is exactly what Filesystem MCP exposes. Instead of mounting
the root as a single directory, `app/agent/mcp_tools.py` now bind-mounts
each top-level entry separately (all `,ro`) and skips `.env`, so the
file **does not exist inside the container** - no tool call, path trick,
or prompt can reach it.

A single root mount with an empty file mounted over `.env` was tested
and rejected: on a Windows host the bind mount is case-insensitive, so
`.ENV` / `.Env` still opened the real file. With per-entry mounts, the
container's `/projects/mcp-tool-calling-agent` directory is a plain
Linux directory, and `.env`, `.ENV`, `.Env`, `app/../.env` and the
Windows short name `ENV~1` all fail with `ENOENT` (verified against the
real container). `.env.example` (placeholders only) stays readable.

Limitation: the list of top-level entries is read when the tools are
first discovered, so a top-level file added later is visible to the
filesystem server only after an app restart.

### Read-only protections (unchanged)

- GitHub MCP: `--read-only` is hardcoded in `app/agent/mcp_tools.py`,
  not configurable by env var.
- Filesystem MCP: every Docker mount is `,ro`, and the hardcoded tool
  allowlist keeps `write_file`, `edit_file`, `move_file` and
  `create_directory` away from the LLM.
- Neither can be changed by editing `.env`.

### Testing

All Phase 6 tests use fake LLMs, fake tools, and a fake MCP client - no
API key, Docker, or network. They cover: LLM failure (`LLMError` and a
clean `502`), unexpected errors (clean `500` without internal details),
missing API key and unsupported provider, a crashing MCP tool, a tool
timeout, invalid tool arguments, a malformed tool call, one MCP server
down while the other still works (with the PAT absent from the logs),
the read-only allowlist and `,ro` mounts, and `.env` being excluded from
the filesystem mounts. The opt-in `DOCKER_TESTS=1` test repeats the
`.env` check against the real container.
