# Production-Oriented AI Engineering Agent

## Current Phase

**Phase 1 — Foundation.** A minimal, working FastAPI + LangGraph + LLM
pipeline. No MCP tools, Docker, Kubernetes, or GCP yet.

## Current Architecture

```text
Client
  ↓
FastAPI          (app/api/routes.py)
  ↓
LangGraph        (app/agent/graph.py: START -> agent -> END)
  ↓
LLM              (app/agent/llm.py: mock or OpenAI, chosen by env var)
  ↓
Response
```

## Future Architecture (not implemented yet)

Later phases will add tool-calling via two MCP servers, and a deployment
path:

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
│   ├── state.py        LangGraph state (AgentState)
│   ├── nodes.py         Agent node: calls the LLM
│   ├── graph.py          Builds and runs the graph
│   └── llm.py             LLM provider abstraction (mock / openai)
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
