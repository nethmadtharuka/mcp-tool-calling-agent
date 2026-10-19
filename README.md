# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 8 — Kubernetes.** The same three services run on Kubernetes,
with network isolation enforced on a local kind + Calico cluster (see
[Phase 8](#phase-8--kubernetes)). Phase 7 runs them with Docker Compose,
as separate containers talking streamable HTTP (see [Docker](#docker)).

Before that, **Phase 6 — Basic Hardening**: the agent chains several tool calls per
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
local tool (app/agent/tools.py), or over streamable HTTP
(app/agent/mcp_tools.py) to the github-mcp or filesystem-mcp container
  ↓
Response
```

## Future Architecture (not implemented yet)

```text
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
├── test_live_docker.py  opt-in (DOCKER_TESTS=1): the running compose stack
├── test_live_k8s.py     opt-in (K8S_TESTS=1): the running Kubernetes deployment
└── live_probe.py        run inside the agent container/pod by both
run.py                 Dev server entrypoint
requirements.txt       Runtime dependencies, pinned (installed in the image)
requirements-dev.txt   Runtime + test dependencies, pinned
Dockerfile             Agent image (Phase 7)
.dockerignore          Allowlist: only app/ and requirements.txt enter the build
docker-compose.yml     Agent + github-mcp + filesystem-mcp (Phase 7b)
docker-compose.dev.yml Dev override: also publishes the MCP ports on 127.0.0.1
filesystem-mcp/        mcp/filesystem fronted by supergateway (stdio -> HTTP);
                       Dockerfile.k8s bakes in a read-only project snapshot
k8s/                   Kubernetes manifests (Phase 8); kind/ = local cluster
                       config, optional/ = opt-in real-LLM egress policy
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
`requirements-dev.txt` adds `pytest`, `pytest-asyncio`, `httpx` and
`pyyaml` (for the compose and Kubernetes manifest tests).

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

Phase 7b runs the agent and both MCP servers with Docker Compose, each in
its own container, talking MCP over streamable HTTP:

```bash
cp .env.example .env          # set LLM_* and GITHUB_PERSONAL_ACCESS_TOKEN
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

```text
host 127.0.0.1:8000 -> agent --egress-------> github-mcp -> api.github.com
                           \--mcp-internal--> filesystem-mcp (no internet)
```

| Service | Image | Notes |
|---|---|---|
| `agent` | built from `Dockerfile` | the only service with a published port (`127.0.0.1:8000`) and the only one that gets `.env` |
| `github-mcp` | `ghcr.io/github/github-mcp-server` v2.0.2, pinned by digest | `http --read-only`; holds no token, the agent sends it per request |
| `filesystem-mcp` | built from `filesystem-mcp/Dockerfile` | `mcp/filesystem` (stdio only) fronted by `supergateway` 4.1.0 |

- **MCP URLs**: the agent reads `GITHUB_MCP_URL` and `FILESYSTEM_MCP_URL`,
  defaulting to the compose service names. They come from the environment
  only, never from LLM output.
- **GitHub auth**: the agent sends `Authorization: Bearer <PAT>`,
  `X-MCP-Readonly: true` and `X-MCP-Toolsets: $GITHUB_TOOLSETS` on every
  request. The server is started with `--read-only`, which no header can
  undo. `GITHUB_TOOLSETS` can only narrow the server's default toolsets
  (`context, copilot, issues, pull_requests, repos, users`); anything else,
  e.g. `actions`, silently yields no tools.
- **Filesystem sessions**: supergateway runs in stateful mode, one
  `mcp/filesystem` child process per MCP session. A session left open by a
  client that died is reaped after `--sessionTimeout` (60 s).
- **Filesystem mounts**: listed one by one in `docker-compose.yml`, all
  `:ro`. `.env` is never mounted, so reading it (or `.ENV`, `.Env`) returns
  `ENOENT`, and writes return `EROFS`. `.git` and `.venv` aren't mounted
  either. The agent's read-only tool allowlist in `mcp_tools.py` still
  applies on top.
- **Hardening, every service**: non-root (`agent` uid 10001, `github-mcp`
  65532, `filesystem-mcp` 1000), `read_only` rootfs, `cap_drop: ALL`,
  `no-new-privileges`. MCP services also get `restart: unless-stopped`
  and a 256 MB memory limit, and no published ports or `env_file`.
- **Health checks**: `agent` checks `GET /health`; `filesystem-mcp` checks
  supergateway's `/healthz` (answers without opening an MCP session), and
  the agent starts only once it's healthy. `github-mcp` has none: its
  image is distroless (only the server binary, no shell or HTTP client),
  so there's no command a health check could run. The agent waits only
  for it to start and retries discovery if it isn't ready yet (Phase 6).
- **Networks**: `mcp-internal` is `internal: true` (no internet), shared by
  the agent and `filesystem-mcp`. `egress` is shared by the agent (for the
  LLM API) and `github-mcp`.
- **Secrets**: `.dockerignore` is an allowlist, so `.env`, `.git` and
  `.venv` never reach the agent's build context. `.env` values passed via
  `env_file` are visible to anyone who can run `docker inspect`.
- **One server down**: stop either MCP container and the agent logs it as
  unavailable and answers with the remaining tools (Phase 6).

### Dev: reaching the MCP servers from the host

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

This also publishes `github-mcp` on `127.0.0.1:8082` and `filesystem-mcp`
on `127.0.0.1:8001`. To run the agent on the host (`python run.py`)
against them, set `GITHUB_MCP_URL=http://127.0.0.1:8082/` and
`FILESYSTEM_MCP_URL=http://127.0.0.1:8001/mcp`.

### Updating pinned versions

Every image and package is pinned so rebuilds are identical. To update one,
pull the new tag and read its digest:

```bash
docker pull <image>:<tag>
docker image inspect <image>:<tag> --format '{{index .RepoDigests 0}}'
```

| What | Pinned in |
|---|---|
| `python:3.13-slim` | `Dockerfile` |
| `ghcr.io/github/github-mcp-server` | `docker-compose.yml` (also update the `# vX.Y.Z` comment) |
| `mcp/filesystem` | `filesystem-mcp/Dockerfile` |
| `supergateway` (npm, `npm view supergateway version`) | `filesystem-mcp/Dockerfile` |

Replace the old `sha256:...` (or version), then
`docker compose up -d --build` and run the checks in [Test](#test). Also
check that the new github-mcp-server still lists no write tools under
`--read-only`, and that the filesystem server's tool names are still
covered by `_FILESYSTEM_READONLY_TOOLS` in `app/agent/mcp_tools.py`.

## Test

```bash
pytest
```

**Unit and static tests** (always run): the mock LLM and fake tools/MCP
servers, so no API key, Docker, or network access is needed. They also
parse the deployment files: `docker-compose.yml` (no `.env` in any mount,
every mount `:ro`, no MCP ports, no `env_file`, read-only rootfs) and
everything under `k8s/` (hardening, Secret wiring, NetworkPolicies; see
`tests/test_k8s.py`).

**Live tests** (opt-in, real containers, nothing mocked). They skip
unless asked for, and fail with the missing prerequisite when asked for
but not runnable. Neither makes a paid LLM call: the agent request is
skipped unless the agent runs `LLM_PROVIDER=mock`, and the multi-step
checks drive the real graph with a scripted fake LLM.

```bash
# Production compose stack (not the dev override: it publishes MCP ports on purpose)
docker compose up -d --build
DOCKER_TESTS=1 pytest tests/test_live_docker.py -v

# Kubernetes (default context kind-mcp-agent; see Phase 8)
K8S_TESTS=1 pytest tests/test_live_k8s.py -v
K8S_TESTS=1 K8S_CONTEXT=docker-desktop pytest tests/test_live_k8s.py -v
```

Both run `tests/live_probe.py` *inside* the agent container or pod, so
it uses the agent's own config and network path. It reports only
booleans and counts, never file contents or secret values, and checks:
- **Filesystem MCP:** tools are discovered and the write tools are
  filtered out. `README.md` is readable. `.env` (and `.ENV`, `.Env`,
  `app/../.env`, `ENV~1`, `../.env`), `.git`, `.venv` and
  `/proc/*/environ` are denied. `write_file` and `edit_file` fail with
  `EROFS`.
- **The real graph** chains several MCP tool calls; `write_file` is never
  offered and is refused if requested; the 8-step limit holds.
- **A dead MCP server** is skipped, not cached.
- **With a GitHub token,** `X-MCP-Readonly: false` still yields no write
  tools, and a real GitHub tool call works.

On top of the probe:

| | `test_live_docker.py` | `test_live_k8s.py` |
|---|---|---|
| Config / readiness | `compose config` valid; agent and filesystem-mcp healthy | all Deployments available |
| Exposure | only the agent published, on `127.0.0.1:8000` | `/health` and a mock `/api/agent/run` through a port-forward the test starts and stops |
| Hardening at runtime | users, read-only rootfs, `cap_drop`, `no-new-privileges` | same, plus no service-account token and `restricted` Pod Security |
| Secrets | `/app` holds only `app/` and `requirements.txt`; `.env` values absent from image history and compose logs | Secret has only the two keys and no `last-applied` annotation; only the agent gets it; values match `.env` (compared as hashes) |
| Other | supergateway leaves no child processes after the sessions close | NetworkPolicy: 6 allowed paths, 29 blocked paths, plus controls proving each blocked target is reachable without the policy |

The NetworkPolicy tests need the policies applied on a cluster that
enforces them (kind + Calico). On `docker-desktop` they're skipped as
"not enforced"; and if the policies are applied there anyway, the
blocked-path tests fail, because nothing is actually blocked.

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
tool_fn.invoke(args)  (in-process)      MCP Client --HTTP--> github-mcp-server --HTTPS--> GitHub API
 |                                       |
ToolMessage                             ToolMessage (same shape)
 |                                       |
LLM                                     LLM
```

(Phase 3 first reached the server over stdio, by spawning a container per
session. Since Phase 7b it's its own long-running container, reached over
streamable HTTP; see [Docker](#docker).)

Both kinds of tool end up bound to the LLM and executed the same way
(`agent_node`/`tool_node` in `app/agent/nodes.py` don't care which is
which) - that's the point of MCP: a standard shape for "here's a tool,"
regardless of where it actually runs.

Because a GitHub MCP call is real network I/O, the whole request path is
now `async`: `app/api/routes.py`'s `run()`, `app/agent/graph.py`'s
`run_agent()`, and both graph nodes.

### Running the GitHub MCP server

It runs as its own service: `github-mcp` in `docker-compose.yml`, or
`k8s/github-mcp.yaml` on Kubernetes, started as
`github-mcp-server http --read-only`. `app/agent/mcp_tools.py` connects to
it over streamable HTTP at `GITHUB_MCP_URL` (default
`http://github-mcp:8082/`, the service name) and sends the PAT per request
in the `Authorization` header, so the server itself holds no token.

`--read-only` is set on the server's command line in those two files,
not in `.env`. The agent can't create, update, delete, merge or push
anything on GitHub. No request header can lift it either: the live
tests check that `X-MCP-Readonly: false` still yields no write tools.

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
MCP tool, tool executes, result comes back" loop is proven without a
running server or calling GitHub. Run with `pytest`. The real server is
covered by the opt-in live tests (see [Test](#test)).

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
(`modelcontextprotocol/servers`). It only speaks stdio, so `supergateway`
fronts it with streamable HTTP (`filesystem-mcp/Dockerfile`), and
`app/agent/mcp_tools.py` connects at `FILESYSTEM_MCP_URL` (default
`http://filesystem-mcp:8000/mcp`). The server sees only
`/projects/mcp-tool-calling-agent`:

- **Compose**: that directory is built from bind mounts listed one by one
  in `docker-compose.yml`, every one `:ro`, and `.env` is never one of
  them (see Phase 6, `.env` protection).
- **Kubernetes**: there's no host disk to mount, so
  `filesystem-mcp/Dockerfile.k8s` bakes a read-only snapshot in, built
  from an allowlist that never includes `.env` (see Phase 8, 8d).

Neither is configurable from `.env`: what's visible is fixed in those
files, and writes fail at the OS level (`EROFS: read-only file system`)
even if a write tool were somehow invoked.

(Phase 4 first ran the server per session with `docker run -i` over stdio;
Phase 7b moved it to its own container over HTTP.)

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
run, the same way it forces GitHub MCP off, so plain `pytest` never tries
to reach either server. The real server is covered by the opt-in live
tests (see [Test](#test)).

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
the root as a single directory, `docker-compose.yml` bind-mounts the
project's entries one by one (all `:ro`) and never `.env`, so the file
**does not exist inside the container** - no tool call, path trick, or
prompt can reach it. (Kubernetes gets the same guarantee from the
allowlist that builds its snapshot image; see Phase 8, 8d.)

A single root mount with an empty file mounted over `.env` was tested
and rejected: on a Windows host the bind mount is case-insensitive, so
`.ENV` / `.Env` still opened the real file. With per-entry mounts, the
container's `/projects/mcp-tool-calling-agent` directory is a plain
Linux directory, and `.env`, `.ENV`, `.Env`, `app/../.env` and the
Windows short name `ENV~1` all fail with `ENOENT` (verified against the
real container). `.env.example` (placeholders only) stays readable.

Limitation: the mount list is fixed, so a new top-level file or folder
is invisible to the filesystem server until it's added to
`docker-compose.yml` (and to `filesystem-mcp/Dockerfile.k8s.dockerignore`
for Kubernetes). That is deliberate: nothing becomes readable by accident.

### Read-only protections

- GitHub MCP: `--read-only` is on the server's command line in
  `docker-compose.yml` and `k8s/github-mcp.yaml`, not configurable by env
  var or request header.
- Filesystem MCP: every Compose mount is `:ro` (Kubernetes: a root-owned
  snapshot on a read-only root filesystem), and the hardcoded tool
  allowlist in `app/agent/mcp_tools.py` keeps `write_file`, `edit_file`,
  `move_file` and `create_directory` away from the LLM.
- Neither can be changed by editing `.env`.

### Testing

All Phase 6 tests use fake LLMs, fake tools, and a fake MCP client - no
API key, Docker, or network. They cover: LLM failure (`LLMError` and a
clean `502`), unexpected errors (clean `500` without internal details),
missing API key and unsupported provider, a crashing MCP tool, a tool
timeout, invalid tool arguments, a malformed tool call, one MCP server
down while the other still works (with the PAT absent from the logs),
the read-only allowlist and `,ro` mounts, and `.env` being excluded from
the filesystem mounts. The opt-in live tests repeat the `.env`,
read-only, dead-server and step-limit checks against the real containers
(see [Test](#test)).

## Phase 8 — Kubernetes

Runs on Docker Desktop's built-in Kubernetes (Settings -> Kubernetes ->
Enable, Kubeadm; context `docker-desktop`). Docker Compose keeps working
alongside it.

**This cluster does not enforce NetworkPolicy** (verified: a deny-all
policy is accepted but blocks nothing). Network isolation (8f) therefore
runs on a second, local kind + Calico cluster; on `docker-desktop`,
don't rely on in-cluster network isolation.

### 8b — namespace, config, secrets

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
python k8s/create_secret.py        # re-run after changing a key in .env
```

- `k8s/namespace.yaml`: namespace `mcp-agent` with `restricted` Pod
  Security - the cluster rejects pods that run as root, keep
  capabilities or allow privilege escalation.
- `k8s/configmap.yaml`: non-secret settings. `LLM_PROVIDER=mock`, so
  cluster runs make no paid LLM calls. MCP URLs aren't set: the
  `config.py` defaults are the Service names.
- `k8s/create_secret.py`: Secret `agent-secrets` with only
  `LLM_API_KEY` and `GITHUB_PERSONAL_ACCESS_TOKEN` from `.env`, piped to
  kubectl on stdin (never in arguments, history or a file). Uses
  server-side apply so the values aren't also stored in an annotation.
  Kubernetes Secrets are base64, not encrypted: anyone with
  `kubectl get secret` access in the namespace can read them.

`tests/test_k8s.py` checks these files statically (no cluster needed).

### 8c — github-mcp

```bash
kubectl apply -f k8s/github-mcp.yaml
kubectl -n mcp-agent rollout status deploy/github-mcp
```

Same as the compose service: pinned v2.0.2 digest, `http --read-only`,
no token (the agent sends its PAT per request), uid 65532, read-only
rootfs, no capabilities, 256Mi limit. Added for Kubernetes: no
service-account token, `RuntimeDefault` seccomp, and TCP readiness and
liveness probes on 8082 (the server has no documented health endpoint).
The `github-mcp` ClusterIP Service gives it the in-cluster name
`github-mcp:8082`, which is the default `GITHUB_MCP_URL`; nothing outside
the cluster can reach it.

To talk to it from the host for debugging (localhost only, stop with Ctrl+C):

```bash
kubectl -n mcp-agent port-forward svc/github-mcp 18082:8082
```

`tests/test_k8s.py` checks every Deployment under `k8s/` for the
hardening above, and that every Service is ClusterIP.

### 8d — filesystem-mcp

```bash
docker build -f filesystem-mcp/Dockerfile.k8s -t filesystem-mcp-k8s:0.1.0 .
kubectl apply -f k8s/filesystem-mcp.yaml
kubectl -n mcp-agent rollout status deploy/filesystem-mcp
```

Compose bind-mounts the project live; a cluster can't (the node isn't
your disk), so Kubernetes uses its own image, `filesystem-mcp/Dockerfile.k8s`,
with a **read-only snapshot** of the project baked in.
`filesystem-mcp/Dockerfile` and Compose are unchanged.

- **What goes in**: `Dockerfile.k8s.dockerignore` (BuildKit uses it instead
  of the root `.dockerignore` for this build) is an allowlist of the same
  entries Compose mounts, plus `k8s/`. `.env`, `.git`, `.venv` and
  `build.log` are never in the image, so reading them fails whatever the
  path or case.
- **Read-only twice**: the snapshot is owned by root (the server runs as
  uid 1000) and the root filesystem is read-only. `/tmp` is a 16Mi
  in-memory `emptyDir`.
- **Same base and pins as Compose**: `mcp/filesystem` digest and
  `supergateway@4.1.0`; `tests/test_k8s.py` fails if the two Dockerfiles
  drift apart.
- **One replica, `Recreate` rollouts**: supergateway's `--stateful`
  sessions live in one pod's memory, so two pods must never serve at once.
- **Locally built image**: fixed tag `filesystem-mcp-k8s:0.1.0` and
  `imagePullPolicy: IfNotPresent`. Docker Desktop's cluster shares the
  Docker image store; kind needs `kind load docker-image filesystem-mcp-k8s:0.1.0`.
- **Updating the snapshot**: after editing project files, rebuild with a
  new tag, update it in `k8s/filesystem-mcp.yaml`, and `kubectl apply`.
  (Rebuilding the same tag also works on Docker Desktop, followed by
  `kubectl -n mcp-agent rollout restart deploy/filesystem-mcp`.)

The `filesystem-mcp` ClusterIP Service gives it the in-cluster name
`filesystem-mcp:8000`, matching the default `FILESYSTEM_MCP_URL`
(`http://filesystem-mcp:8000/mcp`). For host debugging:
`kubectl -n mcp-agent port-forward svc/filesystem-mcp 18001:8000`.

### 8e — agent

```bash
docker build -t mcp-agent:0.1.0 .
kubectl apply -f k8s/agent.yaml
kubectl -n mcp-agent rollout status deploy/agent
kubectl -n mcp-agent port-forward svc/agent 8000:8000   # localhost only; Ctrl+C to stop
curl http://127.0.0.1:8000/health
```

(Stop Compose first, or forward to another local port such as
`18000:8000`; Compose already uses 127.0.0.1:8000.)

- **Image**: the same `Dockerfile` and `.dockerignore` as Compose (only
  `app/` and `requirements.txt` go in), built with a fixed tag. No
  Kubernetes-specific Dockerfile is needed. kind: `kind load docker-image mcp-agent:0.1.0`.
- **Config**: `envFrom` the `agent-config` ConfigMap (`LLM_PROVIDER=mock`).
  `LLM_API_KEY` and `GITHUB_PERSONAL_ACCESS_TOKEN` come from the
  `agent-secrets` Secret via `secretKeyRef`, into this pod only. MCP URLs
  aren't set: the `config.py` defaults are the Service names.
- **Hardening**: uid 10001 (the image's `app` user, group from the image),
  read-only root filesystem, 16Mi in-memory `/tmp`, no capabilities, no
  privilege escalation, `RuntimeDefault` seccomp, no service-account
  token, 512Mi limit (~127Mi used).
- **Probes**: HTTP `GET /health` (`app/api/routes.py`). It doesn't check
  the MCP servers on purpose: the agent keeps answering without them (Phase 6).

**Rebuild and roll out after code changes:** bump the tag so the change
is explicit and easy to roll back:

```bash
docker build -t mcp-agent:0.1.1 .
kubectl -n mcp-agent set image deploy/agent agent=mcp-agent:0.1.1
kubectl -n mcp-agent rollout status deploy/agent
# then update the tag in k8s/agent.yaml so the file matches the cluster
kubectl -n mcp-agent rollout undo deploy/agent   # if it goes wrong
```

With `LLM_PROVIDER=mock` the LLM never calls a tool, so a request only
proves MCP *discovery* (the log shows `Discovered 29 MCP tool(s)`). To use a
real model, set `LLM_PROVIDER` in `k8s/configmap.yaml`, `kubectl apply` it,
then `kubectl -n mcp-agent rollout restart deploy/agent` (env vars are
read at pod start).

**Not enforced on Docker Desktop** (verified): any pod can reach the
MCP servers and the agent, and filesystem-mcp can reach the internet.
Compose blocks both. This is what 8f fixes, on a cluster that enforces
NetworkPolicy. The agent already can't use the Kubernetes API: without
a service-account token it gets `403`.

### 8f — network isolation (kind + Calico)

Docker Desktop's cluster accepts NetworkPolicy but ignores it, so the
isolation runs on a second, local **kind** cluster with **Calico**, which
enforces it. Both clusters live side by side as kubectl contexts:
`docker-desktop` and `kind-mcp-agent`. Always pass `--context`.

Pinned: kind v0.33.0, node image `kindest/node:v1.34.11@sha256:44e2…`
(in `k8s/kind/cluster.yaml`), Calico v3.32.2.

**Create the cluster** (one time):

```bash
winget install --id Kubernetes.kind --version 0.33.0 --exact
kind create cluster --config k8s/kind/cluster.yaml
kubectl config use-context docker-desktop   # kind switches the default context; switch it back
K="--context kind-mcp-agent"
kubectl $K create -f https://raw.githubusercontent.com/projectcalico/calico/v3.32.2/manifests/calico.yaml
kubectl $K -n kube-system rollout status ds/calico-node
```

`create`, not `apply`: Calico's CRDs are too big for `apply`'s annotation.

**Load the local images and deploy** (the manifests are unchanged from 8b–8e):

```bash
docker build -t mcp-agent:0.1.0 .
docker build -f filesystem-mcp/Dockerfile.k8s -t filesystem-mcp-k8s:0.1.0 .
kind load docker-image mcp-agent:0.1.0 filesystem-mcp-k8s:0.1.0 --name mcp-agent
kubectl $K apply -f k8s/namespace.yaml -f k8s/configmap.yaml
python k8s/create_secret.py $K
kubectl $K apply -f k8s/github-mcp.yaml -f k8s/filesystem-mcp.yaml -f k8s/agent.yaml
kubectl $K apply -f k8s/network-policies.yaml
kubectl $K -n mcp-agent port-forward svc/agent 18000:8000
```

After a code change, rebuild with a new tag, `kind load` it, then
`kubectl $K -n mcp-agent set image ...` (see 8e). kind can't see your
Docker images until they're loaded.

**Policies** (`k8s/network-policies.yaml`):

| Pod | Ingress | Egress |
|---|---|---|
| all | denied by default | denied by default |
| `agent` | none (see below) | `github-mcp:8082`, `filesystem-mcp:8000`, DNS |
| `github-mcp` | `agent` only, port 8082 | GitHub API IP ranges, port 443 only; DNS |
| `filesystem-mcp` | `agent` only, port 8000 | **none, not even DNS** |

- **No pod can reach the Kubernetes API, the kubelet or kube-system**
  except CoreDNS on port 53. Other namespaces can't reach any pod here.
- **The agent has no ingress rule.** `kubectl port-forward` enters the
  pod's own network namespace, and kubelet probes come from the node;
  Calico allows both without a rule. Add a rule only when an Ingress
  controller or another pod must call the agent.
- **filesystem-mcp gets no DNS**: it never needs DNS, and DNS queries can
  carry data out through CoreDNS's upstream resolver.
- **Hostnames can't be matched.** NetworkPolicy and open-source Calico
  match only IPs and labels (Calico's domain rules are Enterprise-only),
  so:
  - **github-mcp** is limited to the IPv4 ranges GitHub publishes for
    its API (`api` in https://api.github.com/meta; this also covers
    `raw.githubusercontent.com`). Those ranges change occasionally. If
    GitHub tools start failing, refresh the list:
    ```bash
    curl -s https://api.github.com/meta | python -c "import json,sys,ipaddress; [print(f'        - ipBlock: {{cidr: {c}}}') for c in json.load(sys.stdin)['api'] if ipaddress.ip_network(c).version==4]"
    ```
    and replace the `ipBlock` lines in `k8s/network-policies.yaml`.
  - **The agent gets no internet** with `LLM_PROVIDER=mock`. For a real
    LLM, also apply `k8s/optional/agent-llm-egress.yaml`: HTTPS (443) to
    any public IP, never to private, cluster, node or link-local
    addresses. LLM APIs sit on large, shared cloud ranges, so pinning
    their IPs would be brittle and barely narrower. Real hostname
    filtering needs an egress proxy with a domain allowlist.
- **Identity is the `app` label.** Anyone who can create pods in
  `mcp-agent` can create one labelled `app=agent` and get its access.
  Keep pod-creation rights in this namespace to yourself.

**Verified on kind** (2026-10-19): a deny-all policy actually blocked
traffic that worked before it was applied. With the real policies, the
allowed paths work and 31 denied paths are blocked, each checked by IP
against a target shown reachable from an unrestricted pod. The full
`/api/agent/run` flow and real GitHub and filesystem tool calls work.
`tests/test_k8s.py` checks the policies statically: default deny exists,
no allow-all rules, `0.0.0.0/0` only in the optional LLM file, and every
workload has its own ingress and egress policy.

**Delete the kind cluster** (removes only the kind cluster and its context;
Docker Desktop's cluster and Compose are untouched):

```bash
kind delete cluster --name mcp-agent
```
