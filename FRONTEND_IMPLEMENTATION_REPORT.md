# Frontend Implementation Report

**Date:** 2026-11-13 · **Branch:** `development` (uncommitted working tree)
**Scope:**
- A React frontend for the MCP Tool-Calling Agent, built from `design/MCP Tool-Calling Agent — UI_UX.pdf` / `.fig`
- GitHub Actions CI for the frontend and the backend
- Preparation for a later Vercel deployment

---

## 1. Summary

| Deliverable | Status |
|---|---|
| Frontend: all 6 navigation destinations plus a 404 page | ✅ Done, connected to the real backend |
| Design fidelity (tokens, layout, components, states) | ✅ Close match on the 4 designed screens; Providers and Settings were not designed and use the same design language |
| Backend integration | ✅ `GET /health` and `POST /api/agent/run`, the only two endpoints that exist |
| Responsive layout (390 px → 1440 px) | ✅ Verified in a real browser, no horizontal overflow |
| Animations, with `prefers-reduced-motion` respected | ✅ CSS only, no animation library |
| CI: backend, frontend, manual live integration | ✅ Written, structurally validated, every step run locally; ⚠️ **not yet run on GitHub** (needs a push) |
| README, env docs, badges | ✅ |
| Vercel readiness | ✅ `vercel.json`, env-based API URL, SPA fallback; nothing deployed |
| Backend changes | One small, opt-in addition: CORS (see §4) plus 2 tests. No API contract changes |

---

## 2. Implemented pages

| Route | Design page | What it does |
|---|---|---|
| `/` Workspace | PDF p.2–5 | <ul><li>Task input with Ctrl/⌘+Enter and "Try an example"</li><li>Live run with an elapsed timer</li><li>Final answer, step-limit notice or error, plus "Edit and retry"</li><li>Provider card and MCP card</li></ul> |
| `/execution/:runId` | p.7–9 | <ul><li>Request, status pill, the HTTP request as the single real timeline step</li><li>Final response, run details (duration and start time are measured; the rest are labelled "not reported")</li><li>Tool-steps meter: shows 8/8 when the server stops the run at the step limit</li></ul> |
| `/execution` | — | Opens the latest run, or shows an empty state |
| `/history` | p.10 | <ul><li>Search, with Ctrl+K to focus</li><li>All / Succeeded / Failed tabs and a time-range menu</li><li>Responsive table; rows open the run</li></ul> |
| `/tools` | p.6 | <ul><li>GitHub and Filesystem server cards: read-only scope, toolsets / read-only allowlist</li><li>"Technical information" and "Connection details" disclosures</li><li>Access policy</li></ul> |
| `/providers` | not designed | The 3 supported providers, their default models, and how to switch on the server |
| `/settings` | not designed | <ul><li>Backend connection: base URL, health, "Check connection"</li><li>Clear local history, with a confirmation that names the run count</li><li>About</li></ul> |
| `*` | — | Not-found page |

The app shell matches the design:
- 264 px sidebar with the brand, NAVIGATE list, and the active item in lime with a glow.
- Backend health card at the bottom of the sidebar.
- Top bar with a mono breadcrumb and an "API healthy" pill.

Below 1024 px the sidebar becomes a drawer, closed with Escape or the backdrop.

---

## 3. Design reference comparison

The source was rendered to PNG from the 10-page PDF:
- p.1: style guide
- p.2–5: Workspace states
- p.6: Tools
- p.7–9: Execution
- p.10: History

The `.fig` archive holds the same 6 screens (canvas 9140×900) and no image assets. The logo and icons were therefore rebuilt: the logo as an inline SVG, the icons with Lucide.

| Element | Design | Implementation |
|---|---|---|
| Palette | `#050505 #0A0A0A #111111 #262626 #737373 #A3A3A3 #FFFFFF #B7FF00` | Same values, as Tailwind `@theme` tokens (`ink-950…ink-300`, `lime`) |
| Type | Inter + JetBrains Mono | Same, self-hosted with `@fontsource` (no external font CDN) |
| Cards / borders | `#111` cards, `#262626` 1 px borders, large radius | `rounded-2xl`, `border-ink-700`, `bg-ink-850` |
| Selected state | "Accent border and a subtle glow… neon used sparingly" | Lime/45 border, lime/16 fill and a glow on the active nav item; glow on the focused composer and running cards |
| Components | Run agent (lime), Review tools (outline), Connected pill, Read-only pill with lock, dashed "Concept" tag | Built as `Button`, `Pill`, `ReadOnlyPill` and `ConceptTag` in `components/ui.tsx` |
| Layout at 1440 | 264 px sidebar; main column about 748 px plus a 340 px right rail | Same (`xl:grid-cols-[1fr_340px]`) |

**Screenshots:** headless Edge at 1440×900, compared with the PDF pages side by side.
- Workspace, Execution, Tools and History match the reference in structure, spacing, typography and colour.
- **Fixed after comparing:** the Workspace icon (`>_`), the subtitle width, the textarea resize handle (it now grows with its content), the provider-menu layout, and an accent-colour class conflict.

**Deliberate deviations.** Each is required because the backend doesn't provide the data. The design itself labels these items "Concept" or "sample data".

| Design shows | Why it can't be real | What the app shows instead |
|---|---|---|
| "Connected" pills for the MCP servers | No endpoint reports MCP status (`/health` ignores the MCP servers) | Neutral **"Not reported"** pill with an explanation on hover |
| GitHub tool chips (`list_commits`…), "Tools discovered: 5" | Tools are discovered inside the server; the API doesn't list them | The default **toolsets** for GitHub, and the **read-only allowlist** from `app/agent/mcp_tools.py` for the filesystem server, each labelled with its source |
| Provider dropdown showing `gemini · flash-lite-latest` | The active provider isn't exposed | "Set on server · LLM_PROVIDER"; the menu lists the supported providers, none selectable, with the design's Concept tag kept |
| Execution timeline with per-tool steps, inputs and outputs | `POST /api/agent/run` returns only `{response}` | One real step (the HTTP request, timed and with its status), the Concept tag, and the design's own note: "Today the API returns only the final response" |
| Run details: Provider, Model, Tool calls | Not returned | "not reported" (duration and start time are real, measured in the browser) |
| Run History "sample data" with Provider and Tools columns | Backend stores nothing | Real runs from this browser (`localStorage`); Provider and Tools columns dropped, Provider filter dropped (no data to filter on) |

---

## 4. Backend integration

**Contract used, read from `app/api/routes.py`:**
- `GET /health` returns `{"status":"ok"}`.
- `POST /api/agent/run` takes `{"message": str ≥1}` and returns `{"response": str}`.
- Errors return `{"detail": str}` (500/502) or a 422 validation list.

**Client:** `frontend/src/api/client.ts`. It is the only module that calls `fetch`, through the single `API_BASE_URL` from `VITE_API_BASE_URL`.

| Outcome | UI |
|---|---|
| 200 | Final response |
| 200 with "Stopped: reached the limit of…" (from `graph.py`) | "Step limit" status; meter shows 8/8 |
| 502 with backend JSON | LLM provider failure, with a hint |
| 500 with backend JSON | Server message shown as returned (e.g. the clear `LLM_API_KEY is required…` config error) |
| 422 | Readable "rejected as invalid" |
| Network error, or 502/503/504 **without** backend JSON | "Can't reach the backend". **This was a bug found during browser testing:** the dev proxy's own 502 had been shown as an LLM failure. Fixed and covered by tests. |
| No response within 5 min | Timeout (the server's worst case is 8 steps of up to 60 s tools) |

**Health:** one shared poller runs every 30 s and feeds the sidebar, top bar and Settings.

**Not presented as working**, because the backend has none of these:
- streaming
- authentication
- run storage
- provider switching
- per-step traces
- MCP status

**Backend change: CORS (opt-in).** A frontend on Vercel runs on a different origin, and without CORS headers the browser blocks every call.
- **Change:** `app/main.py` adds FastAPI's `CORSMiddleware` **only when `CORS_ALLOW_ORIGINS` is set**. It accepts exact origins only, `GET`/`POST` only, the `Content-Type` header only, and never sends credentials.
- **Default:** unset, so behaviour is unchanged.
- **Tests:** `tests/test_cors.py` checks that it's off by default, that only listed origins are allowed, that trailing slashes are normalised, and that no credentials header is sent.
- **Local dev** doesn't need it: Vite proxies `/api` and `/health`.

**Other backend-side edits (no behaviour change):**
- `ruff.toml` pins the lint rules so CI matches local runs.
- An unused `pytest` import was removed from `tests/test_agent.py`.
- `l` was renamed to `line` in `tests/test_k8s.py`.
- `pytest-cov` and `ruff` were added to `requirements-dev.txt`.

MCP security restrictions, Docker and Kubernetes manifests, and the API contract are untouched.

---

## 5. Component architecture

```text
frontend/src/
├── api/client.ts            fetch + typed ApiError mapping (only network boundary)
├── config.ts                API_BASE_URL, MAX_TOOL_STEPS=8, poll/timeout constants
├── lib/runs.ts              run store (start/update/persist; reload → "interrupted")
├── lib/health.ts            shared health poller
├── lib/{format,mcp,providers}.ts
├── hooks/useStores.ts       useSyncExternalStore bindings (no state library)
├── hooks/{useNow,useDismiss}.ts
├── components/ui.tsx        Card, Eyebrow, Pill, ReadOnlyPill, ConceptTag, Button, Logo, PageHeader, KeyValue…
├── components/{status,ProviderCard,McpServersCard,RunOutcome,Disclosure}.tsx
├── layouts/AppLayout.tsx    sidebar, top bar, breadcrumb, mobile drawer, skip link
├── pages/*.tsx              one per route
└── routes.tsx / App.tsx / main.tsx
```

**Run state** lives in a small external store (`useSyncExternalStore`), not in component state. A run keeps going while you navigate away, and the Execution page updates live.

**Dependencies.** Runtime has 6 packages: `react`, `react-dom`, `react-router`, `lucide-react` and the two `@fontsource` font packages. Versions are exact, with `save-exact` set and a lockfile. **Framer Motion was not added**: the design calls for subtle motion only, and CSS covers page entry, popovers, disclosures and status pulses with no runtime cost.

**Strict TypeScript:** `strict`, `noUncheckedIndexedAccess`, and `verbatimModuleSyntax`, with no `any`. ESLint uses `typescript-eslint` strict plus the React Hooks rules; those rules caught 2 impure-render issues and 1 effect issue, all fixed.

**Accessibility:**
- skip link
- visible lime focus rings
- labelled inputs
- `aria-live` on status and result
- `role="alert"` on errors
- ARIA on tabs, menu and listbox
- focus moves to the page on route change
- Escape closes the drawer and popovers
- all motion is disabled under `prefers-reduced-motion`

---

## 6. CI/CD configuration

| Workflow | Trigger | Jobs |
|---|---|---|
| `.github/workflows/backend-ci.yml` | push / PR, except changes only to `frontend/**`, `design/**` or `*.md`; also manual | **test:**<ul><li>`pip install -r requirements-dev.txt`</li><li>`ruff check`</li><li>`pytest` with coverage (XML and JUnit uploaded, coverage % in the job summary)</li></ul>**images:**<ul><li>`docker compose config` for both compose files, using a placeholder `.env` with no secrets</li><li>build the agent, filesystem-mcp and filesystem-mcp-k8s images</li><li>check `/app` contains only `app/` and `requirements.txt`</li><li>check that no `.env` exists in the k8s snapshot image</li></ul> |
| `.github/workflows/frontend-ci.yml` | push / PR touching `frontend/**`; also manual | `npm ci` → ESLint → `tsc -b` → Vitest → production build → guard that fails if the bundle contains `localhost:<port>` or `127.0.0.1` → bundle-size summary → `dist` artifact |
| `.github/workflows/live-integration.yml` | **manual only** | Starts the real Compose stack (mock LLM, no secrets), runs `DOCKER_TESTS=1 pytest tests/test_live_docker.py`, prints logs on failure, always tears down |

**Security:**
- `permissions: contents: read`.
- `persist-credentials: false`.
- **Every action is pinned to a commit SHA**, with a version comment.
- **No secrets are used.** `VITE_API_BASE_URL` is read from a repository *variable*, because it's public build config.
- Concurrency cancels superseded runs.

**Validation performed:**
- All 3 files were parsed and checked: triggers, read-only permissions, timeouts, every step either `uses` or `run`, every `uses` SHA-pinned, no `secrets.` references.
- Every frontend CI step was run locally from a clean `npm ci`, and every backend test step was run locally.
- **Not done:**
  - `actionlint`: downloading its binary was blocked by this session's permission policy.
  - Docker-based steps: Docker Desktop was not running.
  - **No workflow has run on GitHub yet.** Badges show "no status" until the first push.

Vercel deployment is **not** automated, as requested.

---

## 7. Environment configuration

| Variable | Side | Purpose | Secret? |
|---|---|---|---|
| `VITE_API_BASE_URL` | frontend, build time | Backend URL; empty = same origin | No: compiled into the public bundle |
| `VITE_DEV_PROXY_TARGET` | frontend dev/preview server | Proxy target (default `http://127.0.0.1:8000`) | No; never bundled |
| `CORS_ALLOW_ORIGINS` | backend | Allowed frontend origins, comma-separated; unset = CORS off | No |
| `LLM_API_KEY`, `GITHUB_PERSONAL_ACCESS_TOKEN` | backend only | Unchanged | Yes: never reach the frontend |

Documented in `frontend/.env.example`, the root `.env.example` and both READMEs. `frontend/.gitignore` excludes `.env*` (except the example), `node_modules`, `dist` and `.vercel`. Checked: no generated or secret files appear in `git status`.

---

## 8. Test results (all run on 2026-11-13)

| Check | Result |
|---|---|
| Frontend ESLint | ✅ 0 problems |
| Frontend `tsc -b` (strict) | ✅ 0 errors |
| Frontend Vitest | ✅ **29 passed** (3 files): API client error mapping (incl. gateway-vs-backend 502), run store (complete / step-limit / failure / reload → interrupted / corrupt storage), all 8 routes, health pill, full journey (example → Ctrl+Enter → answer → Execution → History), LLM-failure journey |
| Backend `ruff check` | ✅ All checks passed |
| Backend `pytest` | ✅ **44 passed**, 56 skipped (opt-in live Docker/K8s suites); line coverage **98 %** (234 statements, 5 missed) |
| `npm audit` | Runtime dependencies: **0 vulnerabilities**. Dev dependencies: 10 moderate, all from one `minimatch` ReDoS in the ESLint toolchain. The only fix is downgrading ESLint by a major version, and the flaw is reachable only at lint time against this repo's own files, so it was accepted |

**Real browser against the real backend.** Headless Edge drove the production build (`vite preview`) against FastAPI on 127.0.0.1:8000 in mock mode (no paid LLM calls).

| Scenario | Result |
|---|---|
| Health → "API healthy"; run from "Try an example" + Ctrl+Enter | ✅ Real backend answer rendered |
| "View run" → Execution page; **browser refresh on `/execution/run_…`** | ✅ Deep link survives the reload |
| `/tools`, `/history`, `/providers`, `/settings`, unknown URL | ✅ All render |
| Backend stopped | ✅ "API unreachable", and the run fails with "Can't reach the backend" (after the fix above) |
| Backend misconfigured (`LLM_PROVIDER=gemini`, empty key) | ✅ The backend's exact `LLM_API_KEY is required…` message, HTTP 500, "Edit and retry" |
| Console errors, page errors, failed requests, HTTP ≥ 400 | ✅ None, across the full journey |
| Horizontal overflow at 390 px (phone) and 1024 px (tablet) | ✅ 0 px; mobile drawer works |

**Not tested:**
- Tool calls with a real LLM and the real MCP containers: Docker was down, and no paid calls were made.
- Safari and Firefox (Chromium/Edge only).
- A real Vercel deployment.
- Screen-reader output beyond the ARIA structure.

---

## 9. Production build

```
dist/assets/index-*.js    365 kB  (113.5 kB gzip)
dist/assets/index-*.css    56 kB  ( 21.9 kB gzip)
fonts: Inter variable + JetBrains Mono 400/500 (woff2, per-subset)
built in ~0.5 s (Vite 8)
```

The bundle contains no local backend address (checked in CI as well). `vercel.json` provides:
- Vite framework settings
- the SPA rewrite to `index.html`
- immutable caching for hashed `/assets/*`
- `nosniff`, `Referrer-Policy` and `X-Frame-Options: DENY` headers

---

## 10. Remaining limitations

1. **No authentication on the API.** Once the backend is public, anyone with the URL can spend the LLM key and use the GitHub token. Add auth before setting `CORS_ALLOW_ORIGINS` for a public frontend.
2. **The concept features need backend work before they can be real:**
   - a per-step trace in the response, or streaming over SSE
   - a run-storage endpoint
   - an MCP status / tools endpoint
   - a provider-info endpoint

   The UI already has places for each and labels them "Concept" or "not reported".
3. **Run history is per browser** (`localStorage`, capped at 200 runs). A reload during a run loses that answer; the run is marked "Interrupted".
4. **Answers are plain text** (`white-space: pre-wrap`). Markdown from the LLM is shown literally. Adding a Markdown renderer would also need HTML sanitisation.
5. **Cancelling a running request** isn't in the design and wasn't added. The only cap is the 5-minute client timeout.
6. **CI hasn't run on GitHub yet**, and `actionlint` wasn't run (see §6).
7. **Providers and Settings** had no design screens; they follow the design system but weren't checked against a reference.

**Not committed.** All changes are in the working tree on `development`.
