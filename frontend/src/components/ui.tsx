import { Lock } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cx } from "../lib/format";

export function Card({ className, children, glow }: { className?: string; children: ReactNode; glow?: boolean }) {
  return (
    <section
      className={cx(
        "rounded-2xl border bg-ink-850 transition-[border-color,box-shadow] duration-200",
        glow ? "border-lime/60 shadow-glow" : "border-ink-700",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function Eyebrow({ children, className, color = "text-ink-300" }: { children: ReactNode; className?: string; color?: string }) {
  return <p className={cx("text-[11px] font-medium uppercase tracking-[0.14em]", color, className)}>{children}</p>;
}

type Tone = "ok" | "lime" | "bad" | "neutral";

const toneClass: Record<Tone, string> = {
  ok: "bg-ok/10 text-ok",
  lime: "bg-lime/10 text-lime",
  bad: "bg-bad/10 text-bad",
  neutral: "border border-ink-700 bg-ink-850 text-ink-300",
};
const dotClass: Record<Tone, string> = { ok: "bg-ok", lime: "bg-lime", bad: "bg-bad", neutral: "bg-ink-500" };

export function Pill({ tone, children, pulse, title }: { tone: Tone; children: ReactNode; pulse?: boolean; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[13px] leading-none whitespace-nowrap", toneClass[tone])}>
      <span aria-hidden className={cx("size-1.5 rounded-full", dotClass[tone], pulse && "animate-pulse-dot")} />
      {children}
    </span>
  );
}

export function ReadOnlyPill() {
  return (
    <span className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-ink-700 px-2.5 text-[13px] text-white">
      <Lock aria-hidden className="size-3.5 text-lime" strokeWidth={2.4} />
      Read-only
    </span>
  );
}

/** Marks UI the backend can't back yet, as the design does. */
export function ConceptTag({ title }: { title?: string }) {
  return (
    <span
      title={title ?? "Design concept: not supported by the backend API yet"}
      className="inline-flex h-7 shrink-0 items-center rounded-full border border-dashed border-ink-500/70 px-3 text-[13px] text-ink-300"
    >
      Concept
    </span>
  );
}

type Variant = "primary" | "outline" | "ghost";

const variantClass: Record<Variant, string> = {
  primary:
    "bg-lime text-ink-950 font-semibold hover:bg-[#c6ff3d] disabled:bg-ink-850 disabled:text-ink-500 disabled:border disabled:border-ink-700",
  outline: "border border-ink-700 bg-ink-950/40 text-white font-medium hover:border-ink-500 hover:bg-ink-850",
  ghost: "text-white/90 font-medium hover:text-white hover:bg-white/5",
};

export function Button({ variant = "outline", className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...props}
      className={cx(
        "inline-flex h-9 items-center justify-center gap-2 rounded-lg px-4 text-[15px] transition-colors duration-150 disabled:cursor-not-allowed",
        variantClass[variant],
        className,
      )}
    />
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cx("grid place-items-center rounded-lg bg-lime", className)}>
      <svg viewBox="0 0 16 16" className="size-1/2" fill="none" stroke="#050505" strokeWidth="1.8" strokeLinejoin="round">
        <path d="M5.5 3.8v8.4L12 8z" />
      </svg>
    </span>
  );
}

export function IconTile({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("grid shrink-0 place-items-center rounded-xl border border-ink-700 bg-ink-900 text-white", className)}>{children}</span>
  );
}

export function PageHeader({ title, description, extra }: { title: ReactNode; description?: ReactNode; extra?: ReactNode }) {
  return (
    <header className="mb-6 sm:mb-7">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-white sm:text-4xl">{title}</h1>
        {extra}
      </div>
      {description && <p className="mt-2 text-[15px] text-ink-300">{description}</p>}
    </header>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="text-[15px] text-ink-300">{label}</dt>
      <dd className="text-right font-mono text-sm text-white">{value}</dd>
    </div>
  );
}
