import { Activity, ArrowRight, RotateCcw } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { McpServersCard } from "../components/McpServersCard";
import { ProviderCard } from "../components/ProviderCard";
import { RunOutcome } from "../components/RunOutcome";
import { RunStatusPill } from "../components/status";
import { Button, Card, IconTile, PageHeader, Pill } from "../components/ui";
import { MAX_TOOL_STEPS } from "../config";
import { useRun } from "../hooks/useStores";
import { useNow } from "../hooks/useNow";
import { cx, formatDuration } from "../lib/format";
import { runStore, type Run } from "../lib/runs";

export const EXAMPLE_PROMPT =
  "Read /projects/mcp-tool-calling-agent/requirements.txt, then get the latest release of langchain-ai/langchain-mcp-adapters and tell me whether our pinned version is the latest.";

// Kept across in-app navigation (not reloads), so leaving the page
// mid-run and coming back still shows that run.
let workspaceRunId: string | undefined;

function StatusText({ run, now }: { run: Run | undefined; now: number }) {
  if (!run) return <>Ready. Each request may use up to {MAX_TOOL_STEPS} tool steps; the run stops with a notice if the limit is reached.</>;
  const elapsed = formatDuration((run.finishedAt ?? now) - run.startedAt);
  switch (run.status) {
    case "running":
      return (
        <>
          Working… <span className="font-mono text-white">{elapsed}</span>. The agent may call several tools on the server; the API returns only the final answer.
        </>
      );
    case "completed":
      return <>Finished in <span className="font-mono text-white">{elapsed}</span>.</>;
    case "stopped":
      return <>Stopped after <span className="font-mono text-white">{elapsed}</span>: the agent reached the {MAX_TOOL_STEPS}-step limit without a final answer.</>;
    case "failed":
      return <>Failed after <span className="font-mono text-white">{elapsed}</span>.</>;
    case "interrupted":
      return <>Interrupted by a page reload.</>;
  }
}

export function WorkspacePage() {
  const [message, setMessage] = useState("");
  const [runId, setRunId] = useState(workspaceRunId);
  const run = useRun(runId);
  const running = run?.status === "running";
  const now = useNow(running);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const canRun = message.trim().length > 0 && !running;

  function start(e?: FormEvent) {
    e?.preventDefault();
    if (!canRun) return;
    const id = runStore.start(message.trim());
    workspaceRunId = id;
    setRunId(id);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) start();
  }

  function tryExample() {
    setMessage(EXAMPLE_PROMPT);
    textarea.current?.focus();
  }

  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader
        title="Agent Workspace"
        description="Describe a task in plain language. The agent chooses MCP tools, runs them read-only and returns one answer."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-6">
          <form onSubmit={start} aria-label="Agent request">
            <div
              className={cx(
                "rounded-2xl border bg-ink-850 transition-[border-color,box-shadow] duration-200",
                "border-ink-700 focus-within:border-lime/70 focus-within:shadow-glow",
              )}
            >
              <label htmlFor="agent-message" className="sr-only">
                Task for the agent
              </label>
              <textarea
                id="agent-message"
                ref={textarea}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyDown={onKeyDown}
                rows={4}
                placeholder="Describe what you want the agent to do..."
                className="block field-sizing-content min-h-[132px] max-h-[50vh] w-full resize-none rounded-t-2xl bg-transparent px-5 pt-5 pb-3 text-[17px] leading-relaxed text-white placeholder:text-ink-500 focus:outline-none"
              />
              <div className="flex items-center justify-between gap-3 border-t border-ink-700 px-4 py-3">
                <p className="font-mono text-xs text-ink-500">
                  <kbd className="font-mono">Ctrl</kbd> + <kbd className="font-mono">Enter</kbd> to run
                </p>
                <Button type="submit" variant="primary" disabled={!canRun}>
                  {running ? "Running…" : "Run agent"}
                </Button>
              </div>
            </div>
          </form>

          <Card className="p-5" glow={running}>
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">Execution status</h2>
              {run ? <RunStatusPill status={run.status} /> : <Pill tone="neutral">Idle</Pill>}
            </div>
            <p aria-live="polite" className="mt-2.5 text-[15px] leading-relaxed text-ink-300">
              <StatusText run={run} now={now} />
            </p>
            {run && !running && (
              <Link to={`/execution/${run.id}`} className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-lime hover:underline">
                View run {run.id} <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            )}
          </Card>

          <Card className="p-5">
            <h2 className="text-lg font-semibold text-white">Result</h2>
            <div className="mt-4" aria-live="polite" aria-busy={running}>
              {!run ? (
                <div className="flex flex-col items-center rounded-xl border border-dashed border-ink-700 px-6 py-14 text-center">
                  <IconTile className="size-12">
                    <Activity aria-hidden className="size-5 text-ink-300" strokeWidth={1.8} />
                  </IconTile>
                  <p className="mt-5 text-lg font-semibold text-white">No result yet</p>
                  <p className="mt-2 text-[15px] text-ink-300">The agent’s final answer appears here after a run.</p>
                  <Button className="mt-5" onClick={tryExample}>
                    Try an example
                  </Button>
                </div>
              ) : running ? (
                <div className="space-y-3 rounded-xl border border-dashed border-ink-700 p-5" aria-label="Waiting for the agent">
                  {[92, 78, 55].map((w) => (
                    <div key={w} className="h-3.5 animate-pulse rounded bg-ink-700/70" style={{ width: `${w}%` }} />
                  ))}
                </div>
              ) : (
                <div className="space-y-4">
                  <RunOutcome run={run} />
                  {run.status !== "completed" && (
                    <Button
                      onClick={() => {
                        setMessage(run.request);
                        textarea.current?.focus();
                      }}
                    >
                      <RotateCcw aria-hidden className="size-4" /> Edit and retry
                    </Button>
                  )}
                </div>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <ProviderCard />
          <McpServersCard />
        </div>
      </div>
    </div>
  );
}
