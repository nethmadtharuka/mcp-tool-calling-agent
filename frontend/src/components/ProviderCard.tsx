import { ChevronDown, Info } from "lucide-react";
import { useCallback, useId, useRef, useState } from "react";
import { useDismiss } from "../hooks/useDismiss";
import { cx } from "../lib/format";
import { PROVIDERS } from "../lib/providers";
import { Card, ConceptTag, Eyebrow } from "./ui";


/**
 * The design shows a provider dropdown, marked "Concept": the provider is
 * chosen on the server, and the API neither reports nor changes it. The
 * menu lists what the server supports; nothing in it is selectable.
 */
export function ProviderCard() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const close = useCallback(() => setOpen(false), []);
  useDismiss(ref, open, close);

  return (
    <Card className="p-5">
      <Eyebrow>LLM provider</Eyebrow>
      <p className="mt-3 mb-2 text-[13px] text-white/90">Provider</p>
      <div ref={ref} className="relative">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={menuId}
          onClick={() => setOpen((o) => !o)}
          className={cx(
            "flex h-[38px] w-full items-center justify-between rounded-lg border bg-ink-950/40 px-3.5 text-left text-[15px] text-white transition-colors",
            open ? "border-lime/70" : "border-ink-700 hover:border-ink-500",
          )}
        >
          <span className="truncate">
            Set on server <span className="text-ink-500">·</span> <span className="font-mono text-[13px] text-ink-300">LLM_PROVIDER</span>
          </span>
          <ChevronDown aria-hidden className={cx("size-4 shrink-0 text-ink-300 transition-transform duration-150", open && "rotate-180")} />
        </button>

        {open && (
          <ul
            id={menuId}
            role="listbox"
            aria-label="Supported providers (read-only)"
            className="absolute inset-x-0 top-[calc(100%+6px)] z-20 space-y-1 rounded-xl border border-ink-700 bg-ink-850 p-1.5 shadow-[0_16px_40px_-12px_rgb(0_0_0/0.8)] animate-pop"
          >
            {PROVIDERS.map((p) => (
              <li key={p.id} role="option" aria-selected={false} aria-disabled title={p.env} className="rounded-lg px-3 py-2">
                <span className="block text-[15px] text-white/90">{p.name}</span>
                <span className="block font-mono text-xs text-ink-500">{p.detail}</span>
              </li>
            ))}
            <li className="flex items-center gap-2 border-t border-ink-700 px-3 pt-2 pb-1 text-xs text-ink-300">
              <Info aria-hidden className="size-3.5 shrink-0 text-ink-300" />
              The active provider isn't reported by the API.
            </li>
          </ul>
        )}
      </div>
      <div className="mt-3 flex items-start justify-between gap-3">
        <p className="text-[13px] leading-relaxed text-ink-500">
          The provider is set on the server (LLM_PROVIDER). Switching it from this screen is a concept.
        </p>
        <ConceptTag />
      </div>
    </Card>
  );
}
