import { useEffect, useState } from "react";

/** The current time in ms, refreshed every second while `active` -- for a
 * live "elapsed" readout. Idle (no timer) when not active. */
export function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}
