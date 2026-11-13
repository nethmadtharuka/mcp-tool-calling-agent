import { ChevronDown, Clock, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { RunStatusPill } from "../components/status";
import { Button, Card, IconTile, PageHeader } from "../components/ui";
import { useDismiss } from "../hooks/useDismiss";
import { useRuns } from "../hooks/useStores";
import { cx, formatDuration, formatStarted } from "../lib/format";
import { isFailed, isSucceeded, type Run } from "../lib/runs";

const TABS = [
  { id: "all", label: "All", test: () => true },
  { id: "ok", label: "Succeeded", test: isSucceeded },
  { id: "failed", label: "Failed", test: isFailed },
] as const;

const RANGES = [
  { id: "24h", label: "Last 24 hours", ms: 86_400_000 },
  { id: "7d", label: "Last 7 days", ms: 7 * 86_400_000 },
  { id: "30d", label: "Last 30 days", ms: 30 * 86_400_000 },
  { id: "all", label: "All time", ms: Infinity },
] as const;

type TabId = (typeof TABS)[number]["id"];
type RangeId = (typeof RANGES)[number]["id"];

function RangeMenu({ value, onChange }: { value: RangeId; onChange: (r: RangeId) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);
  const current = RANGES.find((r) => r.id === value) ?? RANGES[1];

  return (
    <div ref={ref} className="relative">
      <Button aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="h-[38px]">
        {current.label}
        <ChevronDown aria-hidden className={cx("size-4 text-ink-300 transition-transform", open && "rotate-180")} />
      </Button>
      {open && (
        <ul role="menu" className="absolute right-0 top-[calc(100%+6px)] z-20 w-48 rounded-xl border border-ink-700 bg-ink-850 p-1.5 shadow-[0_16px_40px_-12px_rgb(0_0_0/0.8)] animate-pop">
          {RANGES.map((r) => (
            <li key={r.id} role="none">
              <button
                role="menuitemradio"
                aria-checked={r.id === value}
                onClick={() => {
                  onChange(r.id);
                  close();
                }}
                className={cx("w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-white/5", r.id === value ? "text-lime" : "text-white/90")}
              >
                {r.label}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const duration = (r: Run) => (r.finishedAt ? formatDuration(r.finishedAt - r.startedAt) : "–");

export function HistoryPage() {
  const runs = useRuns();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [tab, setTab] = useState<TabId>("all");
  const [range, setRange] = useState<RangeId>("7d");
  const search = useRef<HTMLInputElement>(null);
  const [openedAt] = useState(Date.now); // time ranges are relative to page open

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const visible = useMemo(() => {
    const since = openedAt - (RANGES.find((r) => r.id === range)?.ms ?? Infinity);
    const q = query.trim().toLowerCase();
    const test = TABS.find((t) => t.id === tab)?.test ?? (() => true);
    return runs.filter((r) => r.startedAt >= since && test(r) && (!q || r.request.toLowerCase().includes(q) || r.id.includes(q)));
  }, [runs, query, tab, range, openedAt]);

  return (
    <div className="mx-auto max-w-[1180px]">
      <PageHeader
        title="Run History"
        description="Runs started from this browser. The backend doesn’t store runs, so history is kept locally and isn’t shared across devices."
      />

      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="relative flex h-[38px] w-full items-center sm:w-[320px]">
          <span className="sr-only">Search runs</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 size-4 text-ink-300" />
          <input
            ref={search}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search runs"
            className="h-full w-full rounded-lg border border-ink-700 bg-ink-850 pr-16 pl-9 text-[15px] text-white placeholder:text-ink-500 focus:border-lime/70 focus:outline-none"
          />
          <kbd className="pointer-events-none absolute right-2.5 rounded border border-ink-700 px-1.5 py-0.5 font-mono text-[11px] text-ink-300">Ctrl K</kbd>
        </label>

        <div role="tablist" aria-label="Status" className="flex border-b border-ink-700">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cx(
                "-mb-px border-b-2 px-4 pb-2 text-[15px] transition-colors",
                tab === t.id ? "border-lime text-white" : "border-transparent text-ink-300 hover:text-white",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="sm:ml-auto">
          <RangeMenu value={range} onChange={setRange} />
        </div>
      </div>

      {runs.length === 0 ? (
        <Card className="flex flex-col items-center px-6 py-16 text-center">
          <IconTile className="size-12">
            <Clock aria-hidden className="size-5 text-ink-300" strokeWidth={1.8} />
          </IconTile>
          <p className="mt-5 text-lg font-semibold text-white">No runs yet</p>
          <p className="mt-2 text-[15px] text-ink-300">Every run you start from the Workspace is listed here.</p>
          <Link to="/" className="mt-5 inline-flex h-9 items-center rounded-lg bg-lime px-4 text-[15px] font-semibold text-ink-950 hover:bg-[#c6ff3d]">
            Start a run
          </Link>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-left">
            <thead className="hidden border-b border-ink-700 md:table-header-group">
              <tr className="text-[11px] font-medium uppercase tracking-[0.14em] text-ink-300">
                <th scope="col" className="px-5 py-3.5 font-medium">Request</th>
                <th scope="col" className="px-5 py-3.5 font-medium">Duration</th>
                <th scope="col" className="px-5 py-3.5 font-medium">Started</th>
                <th scope="col" className="px-5 py-3.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => navigate(`/execution/${r.id}`)}
                  className="grid cursor-pointer grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-b border-ink-700 px-5 py-4 transition-colors last:border-b-0 hover:bg-white/[0.025] md:table-row md:p-0"
                >
                  <td className="col-span-2 md:max-w-[520px] md:px-5 md:py-4">
                    <Link to={`/execution/${r.id}`} onClick={(e) => e.stopPropagation()} className="line-clamp-2 text-[15px] text-white hover:underline">
                      {r.request}
                    </Link>
                    <p className="mt-1 font-mono text-[13px] text-ink-500">{r.id}</p>
                  </td>
                  <td className="font-mono text-sm text-white/90 md:px-5 md:py-4">{duration(r)}</td>
                  <td className="row-start-3 font-mono text-sm text-ink-300 md:px-5 md:py-4">{formatStarted(r.startedAt)}</td>
                  <td className="row-span-2 row-start-2 col-start-2 self-center md:px-5 md:py-4">
                    <RunStatusPill status={r.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {visible.length === 0 && (
            <div className="px-5 py-12 text-center">
              <p className="text-[15px] text-white">No runs match these filters.</p>
              <Button
                className="mt-4"
                onClick={() => {
                  setQuery("");
                  setTab("all");
                  setRange("all");
                }}
              >
                Clear filters
              </Button>
            </div>
          )}

          <p className="border-t border-ink-700 px-5 py-3.5 font-mono text-[13px] text-ink-500">
            Showing {visible.length} of {runs.length} runs stored in this browser
          </p>
        </Card>
      )}
    </div>
  );
}
