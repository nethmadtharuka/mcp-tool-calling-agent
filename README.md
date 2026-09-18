# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 2 — Tool calling fundamentals.** The agent can now decide, on its
own, whether it needs a local Python tool before answering. No MCP yet.

## Current Architecture

```text
Client
  ↓
FastAPI          (app/api/routes.py)
  ↓
LangGraph        (app/agent/graph.py: START -> agent -> (tool?) -> END)
  ↓
LLM              (app/agent/llm.py: mock or OpenAI, chosen by env var)
  ↓
Response
```

## Future Architecture (not implemented yet)

MCP will be introduced in Phase 3. Later phases will add a second MCP
server and a deployment path:

```text
GitHub MCP
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
│   └── tools.py            The one Phase 2 tool: get_project_info()
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

MCP (GitHub and Filesystem tool access over the Model Context Protocol)
will be introduced in Phase 3.
