import { RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { HealthPill } from "../components/status";
import { Button, Card, Eyebrow, KeyValue, PageHeader } from "../components/ui";
import { API_BASE_URL } from "../config";
import { useHealth, useRuns } from "../hooks/useStores";
import { formatStarted } from "../lib/format";
import { refreshHealth } from "../lib/health";
import { runStore } from "../lib/runs";

export function SettingsPage() {
  const health = useHealth();
  const runs = useRuns();
  const [checking, setChecking] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const running = runs.some((r) => r.status === "running");

  async function checkNow() {
    setChecking(true);
    await refreshHealth();
    setChecking(false);
  }

  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader title="Settings" description="Connection and data for this browser. Server settings live in the backend’s environment." />

      <div className="max-w-[860px] space-y-6">
        <Card className="p-5">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-white">Backend connection</h2>
            <HealthPill status={health.status} />
          </div>
          <dl className="mt-3 divide-y divide-ink-700/70">
            <KeyValue label="API base URL" value={API_BASE_URL || <span className="text-ink-300">same origin</span>} />
            <KeyValue label="Health endpoint" value="GET /health" />
            <KeyValue label="Last checked" value={health.checkedAt ? formatStarted(health.checkedAt) : "–"} />
          </dl>
          <p className="mt-3 text-[13px] text-ink-500">
            Set with <span className="font-mono">VITE_API_BASE_URL</span> at build time. Checked every 30 s.
          </p>
          <Button className="mt-4" onClick={checkNow} disabled={checking}>
            <RefreshCw aria-hidden className={checking ? "size-4 animate-spin" : "size-4"} />
            {checking ? "Checking…" : "Check connection"}
          </Button>
        </Card>

        <Card className="p-5">
          <h2 className="text-lg font-semibold text-white">Run history</h2>
          <p className="mt-2 text-[15px] text-ink-300">
            {runs.length} {runs.length === 1 ? "run is" : "runs are"} stored in this browser’s local storage. Clearing history can’t be undone.
          </p>
          {confirming ? (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <Button
                className="border-bad/50 text-bad hover:border-bad hover:bg-bad/10"
                onClick={() => {
                  runStore.clear();
                  setConfirming(false);
                }}
              >
                <Trash2 aria-hidden className="size-4" /> Delete {runs.length} {runs.length === 1 ? "run" : "runs"}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                Keep history
              </Button>
            </div>
          ) : (
            <Button className="mt-4" onClick={() => setConfirming(true)} disabled={runs.length === 0 || running} title={running ? "Wait for the current run to finish" : undefined}>
              <Trash2 aria-hidden className="size-4" /> Clear run history
            </Button>
          )}
        </Card>

        <Card className="p-5">
          <Eyebrow>About</Eyebrow>
          <dl className="mt-2 divide-y divide-ink-700/70">
            <KeyValue label="Frontend" value={`v${__APP_VERSION__}`} />
            <KeyValue label="Agent endpoint" value="POST /api/agent/run" />
            <KeyValue label="Authentication" value={<span className="text-ink-300">none (API has none)</span>} />
          </dl>
        </Card>
      </div>
    </div>
  );
}
