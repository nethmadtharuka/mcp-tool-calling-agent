import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { cx } from "../lib/format";

/** Expand/collapse with a height transition (grid-rows 0fr -> 1fr). */
export function Disclosure({
  label,
  children,
  defaultOpen = false,
  className,
  buttonClassName,
}: {
  label: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  buttonClassName?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={className}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
        className={cx("flex w-full items-center gap-3 text-left text-[15px] text-white/90 hover:text-white", buttonClassName)}
      >
        <ChevronRight aria-hidden className={cx("size-4 text-ink-300 transition-transform duration-200", open && "rotate-90")} />
        {label}
      </button>
      <div id={id} className={cx("grid transition-[grid-template-rows] duration-200", open ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden" inert={!open}>
          {children}
        </div>
      </div>
    </div>
  );
}
