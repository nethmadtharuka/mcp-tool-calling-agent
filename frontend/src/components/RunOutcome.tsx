import { AlertTriangle } from "lucide-react";
import type { ApiErrorKind } from "../api/client";
import type { Run } from "../lib/runs";
import { Eyebrow } from "./ui";

const HINT: Record<ApiErrorKind, string> = {
  network: "Start the backend (python run.py or docker compose up) and check the API status in the top right.",
  timeout: "The agent may still be working on the server. Try a smaller task.",
  validation: "The backend rejected the request body.",
  llm: "The LLM provider call failed (key, quota or network). Details are in the backend logs.",
  server: "Details are in the backend logs.",
  unexpected: "Details are in the backend logs.",
};

/** The final answer, or why there isn't one. */
export function RunOutcome({ run }: { run: Run }) {
  if (run.status === "failed" && run.error) {
    return (
      <div role="alert" className="rounded-xl border border-bad/30 bg-bad/[0.06] p-4">
        <p className="flex items-start gap-2 text-[15px] font-medium text-white">
          <AlertTriangle aria-hidden className="mt-[3px] size-4 shrink-0 text-bad" />
          {run.error.message}
        </p>
        <p className="mt-1.5 pl-6 text-sm text-ink-300">
          {HINT[run.error.kind]}
          {run.error.status && <span className="font-mono text-ink-500"> · HTTP {run.error.status}</span>}
        </p>
      </div>
    );
  }
  if (run.status === "interrupted") {
    return <p className="text-[15px] text-ink-300">The page was reloaded before the answer arrived, so it wasn't recorded.</p>;
  }
  if (run.response === undefined) return null;
  return (
    <div>
      <Eyebrow color={run.status === "stopped" ? "text-bad" : "text-lime"}>
        {run.status === "stopped" ? "Stopped at the step limit" : "Final response"}
      </Eyebrow>
      <p className="mt-3 text-[17px] leading-relaxed break-words whitespace-pre-wrap text-white sm:text-lg">{run.response}</p>
      <p className="mt-3 font-mono text-xs text-ink-500">Returned by POST /api/agent/run as a single response string.</p>
    </div>
  );
}
