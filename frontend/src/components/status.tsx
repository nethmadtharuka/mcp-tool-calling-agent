import type { HealthStatus } from "../lib/health";
import type { RunStatus } from "../lib/runs";
import { Pill } from "./ui";

const runPill: Record<RunStatus, { tone: "ok" | "lime" | "bad" | "neutral"; label: string }> = {
  running: { tone: "lime", label: "Running" },
  completed: { tone: "ok", label: "Completed" },
  stopped: { tone: "bad", label: "Step limit" },
  failed: { tone: "bad", label: "Failed" },
  interrupted: { tone: "neutral", label: "Interrupted" },
};

export function RunStatusPill({ status }: { status: RunStatus }) {
  const { tone, label } = runPill[status];
  return (
    <Pill tone={tone} pulse={status === "running"}>
      {label}
    </Pill>
  );
}

const healthPill: Record<HealthStatus, { tone: "ok" | "bad" | "neutral"; label: string }> = {
  checking: { tone: "neutral", label: "Checking" },
  healthy: { tone: "ok", label: "Healthy" },
  unhealthy: { tone: "bad", label: "Unhealthy" },
  unreachable: { tone: "bad", label: "Unreachable" },
};

export function HealthPill({ status, prefix }: { status: HealthStatus; prefix?: string }) {
  const { tone, label } = healthPill[status];
  return (
    <Pill tone={tone} pulse={status === "checking"}>
      {prefix ? `${prefix} ${label.toLowerCase()}` : label}
    </Pill>
  );
}
