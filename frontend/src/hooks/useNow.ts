import { useEffect, useState } from "react";

/** Current time, re-rendered every `ms` while `active` (for elapsed timers). */
export function useNow(active: boolean, ms = 100): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    const tick = () => setNow(Date.now());
    const t = setInterval(tick, ms);
    return () => clearInterval(t);
  }, [active, ms]);
  return now;
}
