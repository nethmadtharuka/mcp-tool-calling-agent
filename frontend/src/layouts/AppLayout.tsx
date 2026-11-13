import { Activity, Clock, Cpu, LayoutGrid, Menu, SlidersHorizontal, Terminal, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { HealthPill } from "../components/status";
import { Logo } from "../components/ui";
import { useHealth } from "../hooks/useStores";
import { cx } from "../lib/format";

const NAV: { to: string; label: string; icon: LucideIcon; end?: boolean }[] = [
  { to: "/", label: "Workspace", icon: Terminal, end: true },
  { to: "/execution", label: "Execution", icon: Activity },
  { to: "/history", label: "Run History", icon: Clock },
  { to: "/tools", label: "Connected Tools", icon: LayoutGrid },
  { to: "/providers", label: "Providers", icon: Cpu },
  { to: "/settings", label: "Settings", icon: SlidersHorizontal },
];

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <Logo className="size-[29px]" />
      <div className="leading-tight">
        <p className="text-[17px] font-semibold text-white">MCP Agent</p>
        <p className="font-mono text-xs text-ink-300">Tool-calling</p>
      </div>
    </div>
  );
}

function SidebarBody({ onNavigate }: { onNavigate?: () => void }) {
  const health = useHealth();
  return (
    <>
      <nav aria-label="Main" className="mt-10">
        <p className="mb-2 px-0.5 text-[11px] font-medium uppercase tracking-[0.14em] text-ink-300">Navigate</p>
        <ul className="space-y-1.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <li key={to}>
              <NavLink
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cx(
                    "flex h-[38px] items-center gap-3 rounded-lg border px-3 text-[15px] transition-[background-color,border-color,color,box-shadow] duration-150",
                    isActive
                      ? "border-lime/45 bg-lime/[0.16] text-white shadow-[0_0_16px_-4px_rgb(183_255_0/0.35)]"
                      : "border-transparent text-white/85 hover:bg-white/[0.04] hover:text-white",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon aria-hidden className={cx("size-[18px]", isActive ? "text-lime" : "text-ink-300")} strokeWidth={1.8} />
                    {label}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-auto rounded-xl border border-ink-700 bg-ink-850/60 p-3.5">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[13px] text-white/90">Backend</p>
          <HealthPill status={health.status} />
        </div>
        <p className="mt-2 font-mono text-xs text-ink-300">
          GET /health → {health.status === "healthy" ? "ok" : health.status === "checking" ? "…" : "no answer"}
        </p>
      </div>
    </>
  );
}

function Breadcrumb() {
  const { pathname } = useLocation();
  const parts = pathname === "/" ? ["workspace"] : pathname.split("/").filter(Boolean);
  return (
    <p className="truncate font-mono text-[13px] text-ink-300">
      {parts.map((p, i) => (
        <span key={i}>
          <span className="text-ink-500">/</span> {p}{" "}
        </span>
      ))}
    </p>
  );
}

export function AppLayout() {
  const health = useHealth();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { pathname } = useLocation();
  const menuButton = useRef<HTMLButtonElement>(null);
  const mainRef = useRef<HTMLElement>(null);

  // Route change: move focus to the new page (nav links close the drawer themselves).
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo({ top: 0 });
  }, [pathname]);

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setDrawerOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="min-h-dvh bg-ink-950">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-lime focus:px-3 focus:py-2 focus:text-ink-950">
        Skip to content
      </a>

      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-[264px] flex-col border-r border-ink-700/80 bg-ink-900 px-4 pt-7 pb-4 lg:flex">
        <Brand />
        <SidebarBody />
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button aria-label="Close navigation" className="absolute inset-0 bg-black/70 animate-[enter_160ms_ease-out_both]" onClick={() => setDrawerOpen(false)} />
          <aside className="relative flex h-full w-[min(280px,85vw)] flex-col border-r border-ink-700 bg-ink-900 px-4 pt-5 pb-4 animate-pop">
            <div className="flex items-center justify-between">
              <Brand />
              <button aria-label="Close navigation" className="grid size-9 place-items-center rounded-lg text-ink-300 hover:bg-white/5 hover:text-white" onClick={() => setDrawerOpen(false)} autoFocus>
                <X className="size-5" />
              </button>
            </div>
            <SidebarBody onNavigate={() => setDrawerOpen(false)} />
          </aside>
        </div>
      )}

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-ink-700/80 bg-ink-950/90 px-4 backdrop-blur-sm sm:px-8">
          <button
            ref={menuButton}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            className="-ml-1 grid size-9 place-items-center rounded-lg text-ink-300 hover:bg-white/5 hover:text-white lg:hidden"
            onClick={() => setDrawerOpen(true)}
          >
            <Menu className="size-5" />
          </button>
          <Breadcrumb />
          <div className="ml-auto">
            <HealthPill status={health.status} prefix="API" />
          </div>
        </header>

        <main id="main" ref={mainRef} tabIndex={-1} className="px-4 pt-8 pb-16 outline-none sm:px-8 sm:pt-12">
          <div key={pathname} className="animate-enter">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
