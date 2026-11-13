/** One shared GET /health poller for the sidebar, top bar and settings. */
import { checkHealth } from "../api/client";
import { HEALTH_POLL_MS } from "../config";

export type HealthStatus = "checking" | "healthy" | "unhealthy" | "unreachable";

export interface HealthState {
  status: HealthStatus;
  checkedAt?: number;
}

let state: HealthState = { status: "checking" };
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;
let inFlight: Promise<void> | undefined;

function set(next: HealthState) {
  state = next;
  listeners.forEach((l) => l());
}

export function refreshHealth(): Promise<void> {
  inFlight ??= checkHealth()
    .then(
      (ok) => set({ status: ok ? "healthy" : "unhealthy", checkedAt: Date.now() }),
      () => set({ status: "unreachable", checkedAt: Date.now() }),
    )
    .finally(() => {
      inFlight = undefined;
    });
  return inFlight;
}

export const healthStore = {
  subscribe(listener: () => void) {
    listeners.add(listener);
    if (listeners.size === 1) {
      void refreshHealth();
      timer = setInterval(() => void refreshHealth(), HEALTH_POLL_MS);
    }
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) clearInterval(timer);
    };
  },
  get: () => state,
};
