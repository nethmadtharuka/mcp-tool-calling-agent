/**
 * Runs this browser has sent. The backend stores nothing, so history lives
 * in localStorage: per browser, best effort, never shared.
 */
import { ApiError, runAgent, type ApiErrorKind } from "../api/client";

export type RunStatus = "running" | "completed" | "stopped" | "failed" | "interrupted";

export interface Run {
  id: string;
  request: string;
  status: RunStatus;
  startedAt: number;
  finishedAt?: number;
  response?: string;
  error?: { kind: ApiErrorKind; message: string; status?: number };
}

const STORAGE_KEY = "mcp-agent.runs.v1";
const MAX_RUNS = 200;
// graph.py's exact wording when MAX_TOOL_STEPS is hit (returned as a 200).
const STEP_LIMIT_PREFIX = "Stopped: reached the limit of";

type Listener = () => void;
let runs: Run[] = load();
const listeners = new Set<Listener>();

function load(): Run[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    // A run still "running" was cut off by a reload: its result is lost.
    return (parsed as Run[])
      .filter((r) => r && typeof r.id === "string" && typeof r.request === "string")
      .map((r) => (r.status === "running" ? { ...r, status: "interrupted" as const } : r));
  } catch {
    return [];
  }
}

function commit(next: Run[]) {
  runs = next.slice(0, MAX_RUNS);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(runs));
  } catch {
    // Private mode / quota: history just won't survive a reload.
  }
  listeners.forEach((l) => l());
}

function update(id: string, patch: Partial<Run>) {
  commit(runs.map((r) => (r.id === id ? { ...r, ...patch } : r)));
}

export function newRunId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(3));
  return "run_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export const runStore = {
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getAll: () => runs,
  get: (id: string) => runs.find((r) => r.id === id),
  clear: () => commit([]),

  /** Starts a run and returns its id at once; the result lands in the store. */
  start(message: string): string {
    const id = newRunId();
    commit([{ id, request: message, status: "running", startedAt: Date.now() }, ...runs]);

    runAgent(message).then(
      (response) =>
        update(id, {
          status: response.startsWith(STEP_LIMIT_PREFIX) ? "stopped" : "completed",
          response,
          finishedAt: Date.now(),
        }),
      (err: unknown) => {
        const e = err instanceof ApiError ? err : new ApiError("unexpected", "Something went wrong in the browser.");
        update(id, {
          status: "failed",
          error: { kind: e.kind, message: e.message, status: e.status },
          finishedAt: Date.now(),
        });
      },
    );
    return id;
  },
};

/** For tests: re-read storage as a fresh page load would. */
export function _reloadRunsForTests() {
  runs = load();
  listeners.forEach((l) => l());
}

export const isSucceeded = (r: Run) => r.status === "completed";
export const isFailed = (r: Run) => r.status === "failed" || r.status === "stopped" || r.status === "interrupted";
