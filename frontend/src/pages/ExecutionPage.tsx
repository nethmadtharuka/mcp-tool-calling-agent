import { Activity, Check, Play, X } from "lucide-react";
import { Link, Navigate, useParams } from "react-router";
import { RunOutcome } from "../components/RunOutcome";
import { RunStatusPill } from "../components/status";
import { Card, ConceptTag, Eyebrow, IconTile, KeyValue, PageHeader } from "../components/ui";
import { MAX_TOOL_STEPS } from "../config";
import { useNow } from "../hooks/useNow";
import { useRun, useRuns } from "../hooks/useStores";
import { cx, formatDuration, formatStarted } from "../lib/format";
import type { Run } from "../lib/runs";

const NOT_REPORTED = <span className="text-ink-500">not reported</span>;

/** /execution: open the latest run, or explain there is none. */
export function ExecutionIndexPage() {
  const runs = useRuns();
  const latest = runs[0];
  if (latest) return <Navigate to={`/execution/${latest.id}`} replace />;
  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader title="Execution" description="Follow a run from request to final answer." />
      <EmptyRun title="No runs yet" body="Start a run from the Workspace and it opens here." />
    </div>
  );
}

function EmptyRun({ title, body }: { title: string; body: string }) {
  return (
    <Card className="flex flex-col items-center px-6 py-16 text-center">
      <IconTile className="size-12">
        <Activity aria-hidden className="size-5 text-ink-300" strokeWidth={1.8} />
      </IconTile>
      <p className="mt-5 text-lg font-semibold text-white">{title}</p>
      <p className="mt-2 max-w-md text-[15px] text-ink-300">{body}</p>
      <Link to="/" className="mt-5 inline-flex h-9 items-center rounded-lg bg-lime px-4 text-[15px] font-semibold text-ink-950 hover:bg-[#c6ff3d]">
        Open Workspace
      </Link>
    </Card>
  );
}

function StepIcon({ status }: { status: Run["status"] }) {
  const base = "grid size-[23px] place-items-center rounded-full border";
  if (status === "running") return <span className={cx(base, "border-lime text-lime")}><Play aria-hidden className="size-2.5 fill-none" strokeWidth={2.6} /></span>;
  if (status === "completed") return <span className={cx(base, "border-ok text-ok")}><Check aria-hidden className="size-3" strokeWidth={2.6} /></span>;
  return <span className={cx(base, "border-bad text-bad")}><X aria-hidden className="size-3" strokeWidth={2.6} /></span>;
}

function ToolSteps({ run }: { run: Run }) {
  // The only step count the API reveals: hitting the limit means all 8 ran.
  const used = run.status === "stopped" ? MAX_TOOL_STEPS : undefined;
  return (
    <Card className="px-5 py-4">
      <div className="flex items-center justify-between">
        <Eyebrow>Tool steps</Eyebrow>
        <p className="font-mono text-sm text-white">
          {used ?? "–"} / {MAX_TOOL_STEPS}
        </p>
      </div>
      <div className="mt-3 grid grid-cols-8 gap-1.5" aria-hidden>
        {Array.from({ length: MAX_TOOL_STEPS }, (_, i) => (
          <span key={i} className={cx("h-1 rounded-full", used && i < used ? "bg-bad" : "bg-ink-700")} />
        ))}
      </div>
      <p className="mt-3 text-xs text-ink-500">
        {used ? "Limit reached: the server stopped the run." : "Limit enforced on the server; steps used aren't reported."}
      </p>
    </Card>
  );
}

export function ExecutionPage() {
  const { runId } = useParams();
  const run = useRun(runId);
  const now = useNow(run?.status === "running");

  if (!run) {
    return (
      <div className="mx-auto max-w-[1180px]">
        <PageHeader title={`Run ${runId ?? ""}`} />
        <EmptyRun title="Run not found" body="Runs are stored only in the browser that started them, and this one isn't here (another browser, or history was cleared)." />
      </div>
    );
  }

  const running = run.status === "running";
  const duration = formatDuration((run.finishedAt ?? now) - run.startedAt);

  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader title={`Run ${run.id}`} extra={<RunStatusPill status={run.status} />} />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-6">
          <Card className="px-5 py-4">
            <Eyebrow>Request</Eyebrow>
            <p className="mt-2 text-[15px] leading-relaxed break-words whitespace-pre-wrap text-white">{run.request}</p>
          </Card>

          <section aria-labelledby="timeline-heading">
            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 id="timeline-heading" className="text-lg font-semibold text-white">
                Execution timeline
              </h2>
              <ConceptTag title="Per-step tool traces are a design concept: the API returns only the final response." />
            </div>
            <ol className="relative">
              <li className="grid grid-cols-[23px_minmax(0,1fr)] gap-4">
                <div className="flex flex-col items-center pt-[13px]">
                  <StepIcon status={run.status} />
                  <span aria-hidden className="mt-1 w-px flex-1 bg-ink-700" />
                </div>
                <Card className="mb-3 flex items-center gap-4 px-5 py-4" glow={running}>
                  <div className="min-w-0 flex-1">
                    <Eyebrow>Agent request · FastAPI</Eyebrow>
                    <p className="mt-1.5 truncate font-mono text-[15px] text-white">POST /api/agent/run</p>
                  </div>
                  <span className="font-mono text-sm text-ink-500">{duration}</span>
                  <RunStatusPill status={run.status} />
                </Card>
              </li>
            </ol>
            <p className="ml-[39px] text-sm text-ink-500">
              Tool calls between request and answer happen inside the server’s LangGraph loop and aren’t returned by the API.
            </p>
          </section>

          {!running && (
            <Card className="p-5 animate-enter">
              <RunOutcome run={run} />
            </Card>
          )}

          {!running && run.status !== "completed" && (
            <Link to="/" className="inline-flex h-9 items-center rounded-lg border border-ink-700 px-4 text-[15px] font-medium text-white transition-colors hover:border-ink-500 hover:bg-ink-850">
              Back to Workspace
            </Link>
          )}
        </div>

        <aside className="space-y-6">
          <Card className="px-5 py-4">
            <Eyebrow className="mb-1">Run details</Eyebrow>
            <dl>
              <KeyValue label="Provider" value={NOT_REPORTED} />
              <KeyValue label="Model" value={NOT_REPORTED} />
              <KeyValue label="Duration" value={running ? <span className="text-ink-300">{duration}</span> : duration} />
              <KeyValue label="Tool calls" value={NOT_REPORTED} />
              <KeyValue label="Started" value={formatStarted(run.startedAt)} />
            </dl>
          </Card>
          <ToolSteps run={run} />
          <Card className="p-5">
            <ConceptTag />
            <p className="mt-3 text-[13px] leading-relaxed text-ink-300">
              Today the API returns only the final response. Per-step input and output are a design concept for a future run trace.
            </p>
          </Card>
        </aside>
      </div>
    </div>
  );
}
