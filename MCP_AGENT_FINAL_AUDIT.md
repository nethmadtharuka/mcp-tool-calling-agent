# MCP Tool-Calling Agent — Final Audit

**Audit date:** 2026-11-13
**Branch audited:** `development` @ `9e04acf` ("add figma design"), which has the same content as GitHub's `main` (`1baf4f6`, merge of PR #10)
**Method:** Read-only. Every source, test, Docker, Compose and Kubernetes file was read. The default test suite was run, and line coverage was measured with the stdlib `trace` module (output kept outside the repo). No project files were changed except for creating this report.

---

## 1. Executive summary

The backend is real, coherent and unusually well hardened for a portfolio project. A FastAPI + LangGraph agent calls tools in a loop. It supports mock, OpenAI and Gemini models. Its tools come from two **read-only** MCP servers (the official GitHub server and the filesystem server), each running in its own container and reached over streamable HTTP. The stack runs on Docker Compose and on Kubernetes. On Kubernetes, NetworkPolicy isolation is enforced (kind + Calico), and opt-in live tests exist for both Compose and Kubernetes.

**Phases 1–8 (agent → MCP → multi-step → hardening → Docker → Kubernetes) are complete.** The code matches the README's claims, and the claims are backed by tests.

Not started: Google Cloud deployment, any frontend code (only a Figma design exists), API authentication, CI, and observability beyond plain logging.

GitHub's `main` branch is up to date: `development` was merged through PRs #9 and #10, so the public repo shows all of Phases 1–8. Only the local `main` branch on the development machine is stale; `git pull` on `main` fixes that.

| | |
|---|---|
| **Overall completion (all 18 audited areas)** | **≈ 68 %** |
| **Completion of Phases 1–8 as planned in the README** | **≈ 100 %** |
| **Showcase decision** | **Ready to show as a backend / AI-infrastructure project once the 3 remaining P0 items in §11 are done (about 1 day).** Do not present it as a deployed cloud product or a full-stack app yet. |

---

## 2. Phase-by-phase completion status

The phase plan comes from the README and the commit history. No separate planning document exists in the repo.

| Phase | Scope | Commit(s) | Status | Evidence |
|---|---|---|---|---|
| 1 | FastAPI + LangGraph foundation, mock LLM | `f2c742e` | ✅ Complete | `app/main.py`, `app/api/routes.py`, `app/agent/graph.py` |
| 2 | Tool-calling fundamentals (local `@tool`) | `53d05f0` | ✅ Complete, tested | `app/agent/tools.py`; `test_tool_call_required` |
| 3 | GitHub MCP + Gemini provider | `0b722d4`, `51d4a1b` | ✅ Complete, tested with fakes; live test is opt-in | `mcp_tools.py`, `llm.py`; `test_mcp_tool_call_required`, `test_gemini_provider_imports_and_constructs` |
| 4 | Filesystem MCP (read-only) | `9626ec7` | ✅ Complete, tested | read-only allowlist in `mcp_tools.py:32`; `test_readonly_protections_intact` |
| 5 | Multi-step agent + step limit | `cd64cc5` | ✅ Complete, tested | `MAX_TOOL_STEPS = 8` in `graph.py:26`; `test_step_limit_stops_infinite_tool_loop` |
| 6 | Hardening (errors, safe logging, `.env` protection) | `16c1340` | ✅ Complete, tested | `routes.py`, `nodes.py`; 12 Phase 6 tests |
| 7a | Containerised agent | `48589f1` | ✅ Complete | `Dockerfile`, allowlist `.dockerignore` |
| 7b | MCP servers as separate containers, Compose | `6dd2836` | ✅ Complete; static tests pass, live tests opt-in | `docker-compose.yml`, `filesystem-mcp/Dockerfile` |
| 8 | Kubernetes with enforced network isolation | `2675b12`, `5e3bdf3` | ✅ Complete; static tests pass, live tests opt-in | `k8s/*.yaml`, `tests/test_k8s.py`, `tests/test_live_k8s.py` |
| — | UI/UX design | `9e04acf` | 🟡 Design only | `design/*.fig` committed; the PDF export is untracked |
| (9) | Google Cloud deployment | — | ❌ Not started | README lists "GCP" under "Future Architecture (not implemented yet)" |
| (10) | Frontend implementation | — | ❌ Not started | No frontend code anywhere |

---

## 3. Implemented architecture

```text
Client ──HTTP──> FastAPI (app/api/routes.py)
                   POST /api/agent/run   GET /health   /docs (auto-generated)
                     │
                     ▼
                 LangGraph (app/agent/graph.py)
                   START → agent ──tool_calls?──► tool ──► agent … → END
                   hard cap: 8 round trips (recursion_limit = 17)
                     │                      │
                     ▼                      ▼
             LLM (app/agent/llm.py)     tool_node (app/agent/nodes.py)
             mock | OpenAI | Gemini      local @tool  +  MCP tools
                                            │
                       ┌────────────────────┴─────────────────────┐
                       ▼ streamable HTTP                           ▼ streamable HTTP
            github-mcp-server v2.0.2 (--read-only)      mcp/filesystem + supergateway
            PAT sent per request, server holds none      per-file :ro mounts, no .env,
            egress: api.github.com only (k8s)            write tools filtered; no egress
```

- **Size:** 363 non-blank, non-comment lines of app code; 943 of tests. The test code is 2.6× the size of the app code.
- **Dependencies:** 9 runtime packages pinned to exact versions. Images are pinned by digest.
- **Deployment targets:** Docker Compose (`docker-compose.yml` plus a dev override) and Kubernetes. Kubernetes was verified on `docker-desktop` and on `kind-mcp-agent` with Calico.

---

## 4. Verified functionality

Legend: **T** = covered by the default test suite (passes today). **L** = covered only by an opt-in live test (not run during this audit). **S** = static manifest test. **D** = claimed in the README as manually verified, but not re-executed. **✗** = untested.

| # | Area | Implementation | Verification |
|---|---|---|---|
| 1 | Project structure | Clean split: `api/`, `agent/`, `core/`. Small, readable modules | — |
| 2 | FastAPI + LangGraph | Async end-to-end; conditional edge; `add_messages` reducer | T |
| 3a | Mock model | `MockChatModel`. Echoes the input and never calls tools | T |
| 3b | Gemini | `ChatGoogleGenerativeAI`. Construction is tested; list-of-blocks output is normalised by `_as_text` | Construction T. **The `_as_text` list branch is ✗ (never executed)**. Live use D |
| 3c | OpenAI | `ChatOpenAI` | **✗: the branch is never executed by any test** |
| 4 | GitHub MCP | Streamable HTTP, Bearer PAT, `X-MCP-Readonly`, server-side `--read-only` | Fake T. Real call L (needs PAT). Live D |
| 5 | Filesystem MCP | Allowlist of 10 read tools; `.env` absent from mounts and from the k8s snapshot | Allowlist T. `.env` denial, case tricks and `EROFS` are L |
| 6 | Multi-step / sequential tools | Loop through the `tool → agent` edge; each turn sees all earlier results | T (scripted LLM, 2 steps) + L (4–5 steps through the real graph) |
| 7 | Cross-MCP calls | Tools from both servers bound together in one request | T (fakes) + L (real filesystem → GitHub) |
| 8 | Container security | Non-root, read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, digest pins, allowlist build contexts | S + L |
| 9a | Tool step limit | 8 round trips, then a graceful 200 response | T + L |
| 9b | Tool timeout | 60 s per tool call | T |
| 9c | Caching | MCP tool **discovery** cached for the process lifetime; partial results are not cached | T (not cached on failure). **The cache-hit path is ✗** |
| 10 | AuthN/AuthZ | **None on the API.** Upstream authZ is solved by read-only MCP servers and a fine-grained PAT | — |
| 11 | Error handling | 422 / 500 / 502 mapping; tool errors fed back to the LLM; malformed and unknown tool calls handled | T (12 tests) |
| 12 | Tests | 42 pass, 56 opt-in skipped | See §5 |
| 13 | Docs | 951-line README; FastAPI `/docs` | — |
| 14 | Kubernetes | Restricted PSA, NetworkPolicies, Secret wiring, probes | S (17 tests) + L (47 tests incl. a 29-path deny matrix) + D |
| 15 | GCP | Nothing | — |
| 16 | Frontend | Figma file + PDF only | — |
| 17 | Observability | stdlib `logging` at INFO. `/health` is liveness only | Safe logging partly T (PAT absent from logs) |
| 18 | Config / secrets | Env-only `Settings`; `.env` gitignored and never committed (checked across full git history: 0 secret-pattern matches); k8s Secret piped through stdin with server-side apply | T + S |

---

## 5. Test coverage and execution results

### Executed during this audit

```
.venv\Scripts\python -m pytest -v
================== 42 passed, 56 skipped, 1 warning in 2.56s ==================
```

| File | Tests | Result |
|---|---|---|
| `tests/test_agent.py` | 24 | 24 passed |
| `tests/test_health.py` | 1 | 1 passed |
| `tests/test_k8s.py` | 17 | 17 passed |
| `tests/test_live_docker.py` | 9 | skipped (needs `DOCKER_TESTS=1` and a running stack) |
| `tests/test_live_k8s.py` | 47 | skipped (needs `K8S_TESTS=1` and a deployed cluster) |

The only warning is a third-party deprecation warning from Starlette's TestClient.

**The live tests could not be run.** The Docker Desktop engine was stopped during the audit. Starting it and bringing the stack up would have changed the environment, which this audit was not allowed to do. Both kube contexts (`docker-desktop`, `kind-mcp-agent`) exist.

### Line coverage (default suite, app code, measured with stdlib `trace`)

All of `app/` except **6 executable lines**, which is roughly 97 % line coverage:

| Never executed | Why it matters |
|---|---|
| `graph.py:62-64`: `_as_text` list branch | This is the **Gemini-specific** output path, and Gemini is the provider configured in the local `.env`. A regression here would only surface in production. |
| `llm.py:56-58`: OpenAI branch | One of the three advertised providers is never constructed in tests. |
| `mcp_tools.py:81`: cache hit | The caching behaviour itself is never asserted. |

### Quality of the tests

**Strong:**
- Fakes are deterministic and assert behaviour, not just return codes. For example, `llm.seen[1]` checks that each turn saw the previous tool result.
- The secret-leak assertions are written so they never print secret values.
- The live tests pair every "blocked" NetworkPolicy check with a control that shows the target is otherwise reachable. That is rare, and it is good practice.

**Gaps:**
- No test makes a real LLM call, not even an opt-in one. Real tool calling with Gemini or OpenAI rests only on the README's manual verification.
- No contract test against the real MCP tool schemas runs in the default suite.
- No load or concurrency test.
- No CI, so "tests pass" is only true on the developer's machine.

---

## 6. Security assessment

### Strengths (above typical portfolio level)

1. **Least privilege for tools.** Both MCP servers are read-only at the server level (`--read-only`, `:ro` mounts, a root-owned snapshot on a read-only rootfs). On top of that, the client side filters which tools exist (a hardcoded allowlist). The LLM never sees a write tool.
2. **Secret isolation.** `.env` is never mounted into or built into the filesystem server. Path tricks are tested live: `.ENV`, `ENV~1`, `../.env`, `/proc/*/environ`. Only the agent gets the Secret. The GitHub MCP server holds no token. The PAT is never logged (tested).
3. **Network isolation.** In Compose, `filesystem-mcp` sits on an `internal` network. In Kubernetes there is default-deny, and `filesystem-mcp` gets no egress at all, not even DNS. `github-mcp` egress is limited to GitHub's IP ranges on port 443. The optional LLM egress policy excludes private and metadata ranges.
4. **Container and pod hardening.** Non-root, read-only rootfs, all capabilities dropped, seccomp `RuntimeDefault`, no service-account token, and the `restricted` Pod Security Admission level.
5. **Clean error surface.** HTTP errors never include exception text.

### Findings

| Sev | Finding | Location |
|---|---|---|
| **High** (for any public deployment) | **No authentication, rate limiting or request-size limit on `POST /api/agent/run`.** Anyone who can reach the port can spend LLM credit and use the owner's GitHub PAT. Today this is mitigated only by exposure: `127.0.0.1` in Compose, ClusterIP plus port-forward in Kubernetes. It is a hard blocker for GCP or a frontend. | `app/api/routes.py:28` |
| Medium | **Prompt injection through tool results.** GitHub issues, PRs and files are attacker-controllable text fed straight to the LLM. The read-only design limits the blast radius, which is good, but nothing marks tool output as untrusted. Data can still flow out through GitHub search query strings. | `nodes.py:99` |
| Medium | **Unbounded tool output.** `read_file` or `directory_tree` results go into the context at full size. This is a cost and DoS vector and can overflow the context window. | `nodes.py:87` |
| Medium | **No overall request timeout.** The worst case is 8 rounds × N parallel calls × 60 s, plus LLM calls with no explicit client timeout. | `graph.py`, `llm.py` |
| Low | Tool exception text (`Error executing '…': {exc}`) goes to the LLM and can be echoed to the client. This partly contradicts the README's statement that API errors never include raw exception text. | `nodes.py:91` |
| Low | Tool **arguments** are logged at INFO and may contain user-supplied content. | `nodes.py:79` |
| Low | Transitive dependencies are not locked. Only the 9 top-level packages are pinned, so a rebuild can pull different sub-dependencies. There is no vulnerability scanning (pip-audit, Trivy). | `requirements.txt` |
| Low | `.env.example` sets `LLM_API_KEY= "Your OpenAI API key here"`. That placeholder is non-empty, so the config check passes and the failure appears later as a 502. | `.env.example` |
| Info | Kubernetes Secrets are base64, not encrypted at rest, on kind and docker-desktop. The README states this. Pod identity is the `app` label, which the README also states. | README 8b / 8f |

---

## 7. Deployment readiness

| Target | Readiness | Notes |
|---|---|---|
| Local dev (`python run.py`) | ✅ Ready | Mock mode needs no key |
| Docker Compose | ✅ Ready | Health checks, hardening, network split. Live suite exists (not run this audit) |
| Kubernetes (local: docker-desktop / kind + Calico) | ✅ Ready | Verified per the README on 2026-10-19 |
| Kubernetes (any managed cluster) | 🟡 Partial | Images are **local only** (`imagePullPolicy: IfNotPresent`, no registry). No Ingress, TLS, HPA or PDB. Secret created from a laptop `.env` |
| **Google Cloud** | ❌ Not ready (0 %) | No Artifact Registry push, Cloud Build, Cloud Run or GKE config, Secret Manager, Workload Identity, IAP or Terraform. Also blocked by the missing API auth |

**Likely GCP path (not implemented):**
- GKE Autopilot with Dataplane V2 enforces NetworkPolicy, so the existing `k8s/` manifests carry over almost unchanged.
- Images go to Artifact Registry.
- Secrets move to Secret Manager through the CSI driver or External Secrets.
- Access goes through IAP or an API key.

Cloud Run with sidecars is possible but would lose the NetworkPolicy story.

---

## 8. Missing functionality

1. **Frontend:** no code. The Figma design (`design/*.fig`, PDF export untracked) is not implemented.
2. **GCP deployment:** nothing.
3. **API authentication and authorisation, plus rate limiting.**
4. **CI pipeline:** no `.github/workflows`. No lint (ruff), type-check (mypy) or image-scan jobs.
5. **Observability:** no structured or JSON logs, request IDs, metrics endpoint, tracing (OpenTelemetry or LangSmith), or token and cost accounting.
6. **Conversation memory and sessions:** each request is single-turn; there is no checkpointer and no thread ID.
7. **Streaming responses** (SSE). A frontend will want these.
8. **Result caching / MCP session reuse:** only discovery is cached. Every MCP tool call opens a new MCP session, and for filesystem-mcp that spawns a new Node child process.
9. **Tool-output truncation and token budgeting.**
10. **Real-LLM integration test** (opt-in), and an OpenAI test.
11. **LICENSE file.**

---

## 9. Technical debt

| Item | Location | Effort |
|---|---|---|
| Local `main` branch is stale (GitHub's `main` is current) | git | 1 min (`git pull`) |
| README is a phase diary: no Phase 1 or Phase 7 headings. "Future Architecture: Kubernetes, GCP" is stale, since Kubernetes is done. It says "29 blocked paths" in one place and "31" in another | `README.md:36-41, 272, 940` | 2–3 h |
| Learning notes left in production code (`#here we are importing the FastAPI class`, a 10-line comment block in `run.py`) and in `.env.example` | `main.py`, `routes.py`, `llm.py`, `run.py`, `.env.example` | 30 min |
| The local tool returns stale text: "currently in Phase 2" | `tools.py:16` | 1 min |
| `.env.example` default `LLM_MODEL=gpt-5.6-luna` doesn't match the README (`gpt-4o-mini`) or the code default | `.env.example` | 1 min |
| `get_settings()` and `get_llm()` are rebuilt on every node call (a new HTTP client per LLM turn) | `nodes.py:26, 40` | 30 min |
| A process-global `_tools_cache` with no key or lock; the cache-hit path is untested | `mcp_tools.py:22` | 30 min |
| No `pyproject.toml`, formatter or linter config | root | 30 min |
| Transitive dependencies unpinned (no lock file) | `requirements.txt` | 30 min |
| Agent container in Compose has no `mem_limit` (the MCP services do) | `docker-compose.yml` | 1 min |
| GitHub IP allowlist will drift (dated 2026-10-19; manual refresh) | `k8s/network-policies.yaml` | ongoing |
| Untracked 7 MB design PDF; a binary `.fig` file in git | `design/` | 5 min |

---

## 10. Final portfolio readiness assessment

| Area | Score | Comment |
|---|---|---|
| Core agent and LangGraph design | 9/10 | Small, correct, well reasoned |
| MCP integration (both servers, cross-server) | 9/10 | Real servers, real transports, read-only by design |
| Security engineering (infra) | 9/10 | The standout. Defence in depth, tested, honestly documented |
| Error handling and reliability | 8/10 | Thorough. Missing: an overall timeout and output limits |
| Testing | 8/10 | Excellent design and live tests. No CI; OpenAI and Gemini paths not fully covered |
| Containers / Kubernetes | 8.5/10 | Production-grade hardening; local images only |
| Documentation | 6/10 | Accurate and deep but long, diary-style, partly stale; no screenshots or demo |
| Observability | 3/10 | Plain logging only |
| API security (authN, rate limits) | 2/10 | Absent |
| Cloud deployment (GCP) | 0/10 | Not started |
| Frontend | 1/10 | Design only |
| **Weighted overall** | **≈ 68 %** | |

**What recruiters will notice (positives):**
- Real MCP over streamable HTTP, not toy stdio.
- Thoughtful threat modelling: the Windows `.ENV` case-insensitivity finding, the `/proc/environ` checks, a NetworkPolicy matrix with control tests.
- Honest docs: "Docker Desktop does not enforce NetworkPolicy."
- A strong ratio of tests to code.
- Clean, minimal code.

**What will hurt today:**
- No live demo, no screenshots or GIF, no frontend.
- No CI badge.
- Leftover tutorial comments read as "learning project".
- The README's opening section is cluttered and partly stale.

**Decision:**
- **SWE / AI-engineering recruiters (backend, platform, AI infra roles): yes, after the P0 items below (about 1 day).** The engineering depth is already above typical portfolio level.
- **Full-stack or "shipped product" framing: not yet.** That needs at least the P1 items: auth, a minimal UI and a cloud deployment with a public URL.

---

## 11. Recommended remaining work (prioritised)

### P0: before showing anyone (about 1 day)
1. ~~Merge `development` → `main`~~: **already done** on GitHub (PRs #9, #10).
2. **Rewrite the README top section:**
   - a 3-sentence pitch
   - an architecture diagram
   - "What this demonstrates" bullets (MCP, LangGraph, defence-in-depth, Kubernetes isolation)
   - a quick start
   - a demo GIF or screenshots of a real Gemini + GitHub + filesystem run

   Move the phase diary to `docs/`. Fix the stale "Future Architecture" section and the 29/31 mismatch.
3. **Strip the tutorial comments.** Fix `tools.py`'s "Phase 2" text and the `.env.example` model and placeholder.
4. **Add GitHub Actions CI** running `pytest` (plus ruff), with a badge in the README. The default suite needs no secrets and takes about 3 s.

### P1: makes it deployable (about 1–2 weeks)
5. **API authentication** (API key header or OAuth/IAP) **plus rate limiting and a maximum message length.**
6. **Truncate tool output and add an overall request timeout.** Label tool results as untrusted in the system prompt.
7. **Tests:** cover the Gemini `_as_text` list branch and the OpenAI construction, and add an opt-in real-LLM smoke test (`LLM_TESTS=1`).
8. **GCP deployment:**
   - push images to Artifact Registry
   - deploy to GKE Autopilot (Dataplane V2 enforces the existing NetworkPolicies)
   - use Secret Manager and Workload Identity
   - put IAP or an Ingress with TLS in front
   - add Cloud Build or a GitHub Actions deploy job

   Publish a demo URL.
9. **Minimal frontend from the Figma design:** a chat view that shows the tool-call trace. This needs SSE streaming or a `steps` field in the response.

### P2: production polish
10. Structured JSON logs with request IDs, OpenTelemetry or LangSmith tracing, token and cost metrics, and a `/metrics` endpoint.
11. MCP session reuse (persistent client sessions) to remove the per-call handshake and process spawn.
12. Conversation memory (LangGraph checkpointer plus a `thread_id`).
13. A dependency lock file, `pip-audit` and Trivy in CI, and a LICENSE.
14. An HPA and PDB for the agent, and an automated refresh of the GitHub IP ranges.

---

### Things this audit could not verify
- **Live Docker and Kubernetes suites (56 tests):** the Docker engine was not running. The results are claimed in the README (Kubernetes verified 2026-10-19) but were not re-executed here.
- **Real Gemini and OpenAI tool calling:** no paid or live LLM calls were made. The README documents manual Gemini verification.
- **The Figma/PDF design contents:** no PDF renderer was available, so the planned frontend scope is unknown beyond the file's existence.

**Overall completion: ≈ 68 %** (Phases 1–8: ≈ 100 %; GCP, frontend, auth, CI and observability make up the rest).
**Verdict:** a strong, credible AI-infrastructure portfolio piece. Do the remaining P0 items (README, comment cleanup, CI), then show it.
