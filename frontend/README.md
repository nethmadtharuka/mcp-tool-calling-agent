# MCP Agent — frontend

React 19 + TypeScript (strict) + Vite + Tailwind CSS v4 + React Router.
It implements the UI/UX design in `../design/` against the backend's real
API: `GET /health` and `POST /api/agent/run`.

```bash
npm ci
npm run dev        # http://localhost:5173 (proxies /api and /health to 127.0.0.1:8000)
npm run lint       # ESLint
npm run typecheck  # tsc -b
npm test           # Vitest + Testing Library
npm run build      # production bundle in dist/
```

## Structure

```text
src/
├── api/client.ts         the only place that calls fetch; maps HTTP errors to typed ApiErrors
├── lib/runs.ts           run store: starts runs, persists history to localStorage
├── lib/health.ts         one shared GET /health poller (30 s)
├── lib/{format,mcp,providers}.ts   helpers and static facts from the backend's source
├── hooks/                useSyncExternalStore bindings, timers, popover dismissal
├── components/           design-system pieces (ui.tsx, status pills, cards, disclosure)
├── layouts/AppLayout.tsx sidebar, top bar, mobile drawer
├── pages/                one file per route
├── routes.tsx            route table
└── config.ts             VITE_API_BASE_URL and limits that mirror the backend
```

## Environment

See `.env.example`. `VITE_*` values are compiled into the public bundle,
so never put secrets in them.

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend URL for production builds. Empty = same origin. |
| `VITE_DEV_PROXY_TARGET` | Backend for the dev/preview proxy (default `http://127.0.0.1:8000`). |

## Deploying to Vercel (later)

Root Directory `frontend`, framework Vite (see `vercel.json`, which also
sets the SPA fallback). Set `VITE_API_BASE_URL`, and set
`CORS_ALLOW_ORIGINS=<the Vercel origin>` on the backend.
