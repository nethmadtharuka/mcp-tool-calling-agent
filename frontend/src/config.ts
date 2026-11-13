/** Backend base URL. Empty = same origin (local dev, through the Vite proxy). */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").trim().replace(/\/+$/, "");

/** Mirrors MAX_TOOL_STEPS in app/agent/graph.py (enforced server-side). */
export const MAX_TOOL_STEPS = 8;

export const HEALTH_POLL_MS = 30_000;

/** Client-side cap. The server's worst case is 8 steps of up to 60 s tools. */
export const RUN_TIMEOUT_MS = 5 * 60_000;
