/**
 * The backend's whole HTTP surface (app/api/routes.py):
 *   GET  /health          -> {"status": "ok"}
 *   POST /api/agent/run   {"message": str (min 1)} -> {"response": str}
 *   errors                -> {"detail": str} (500, 502) or a 422 validation list
 * Nothing else exists: no streaming, no run storage, no tool listing, no auth.
 */
import { API_BASE_URL, RUN_TIMEOUT_MS } from "../config";

export type ApiErrorKind = "network" | "timeout" | "validation" | "llm" | "server" | "unexpected";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

const url = (path: string) => `${API_BASE_URL}${path}`;

async function request(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const timeout = AbortSignal.timeout(timeoutMs);
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  try {
    return await fetch(url(path), { ...init, signal });
  } catch (err) {
    if (timeout.aborted) {
      throw new ApiError("timeout", `No response from the backend within ${Math.round(timeoutMs / 1000)} s.`);
    }
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError("network", UNREACHABLE);
  }
}

async function detailOf(res: Response): Promise<string | undefined> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === "object" && "detail" in body) {
      const { detail } = body as { detail: unknown };
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return "The request was rejected as invalid.";
    }
  } catch {
    // Non-JSON body (e.g. a proxy error page): fall through to the generic message.
  }
  return undefined;
}

// A proxy or gateway in front of a dead backend (Vite's dev proxy, Vercel,
// nginx...) answers 502/503/504 itself. The backend's own errors always
// carry a JSON "detail", which is how the two are told apart.
const GATEWAY_STATUSES = new Set([502, 503, 504]);
const UNREACHABLE = "Can't reach the backend. Check that it's running and that VITE_API_BASE_URL is correct.";

export async function checkHealth(signal?: AbortSignal): Promise<boolean> {
  const res = await request("/health", { signal }, 10_000);
  if (GATEWAY_STATUSES.has(res.status)) throw new ApiError("network", UNREACHABLE, res.status);
  if (!res.ok) return false;
  const body: unknown = await res.json().catch(() => null);
  return !!body && typeof body === "object" && (body as { status?: unknown }).status === "ok";
}

export async function runAgent(message: string, signal?: AbortSignal): Promise<string> {
  const res = await request(
    "/api/agent/run",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    },
    RUN_TIMEOUT_MS,
  );

  if (res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const response = body && typeof body === "object" ? (body as { response?: unknown }).response : undefined;
    if (typeof response !== "string") throw new ApiError("unexpected", "The backend returned an unexpected response.", res.status);
    return response;
  }

  const detail = await detailOf(res);
  if (detail === undefined && GATEWAY_STATUSES.has(res.status)) throw new ApiError("network", UNREACHABLE, res.status);
  if (res.status === 422) throw new ApiError("validation", detail ?? "The request was rejected as invalid.", 422);
  if (res.status === 502) throw new ApiError("llm", detail ?? "The LLM provider request failed.", 502);
  if (res.status >= 500) throw new ApiError("server", detail ?? "The agent failed with an internal error.", res.status);
  throw new ApiError("unexpected", detail ?? `Unexpected HTTP ${res.status} from the backend.`, res.status);
}
