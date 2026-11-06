"use client";

import { useCallback, useEffect, useState } from "react";

const PREFIX = "ci:open:";

/** An open/closed flag that is remembered per `key` in localStorage -- for a
 * collapsible section whose state should survive navigating away and back.
 * Starts at `defaultOpen` (so the server and first client render agree) and
 * switches to the remembered value on mount. */
export function usePersistedOpen(key: string, defaultOpen: boolean): [boolean, (next?: boolean) => void] {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(PREFIX + key);
      if (stored === "1") setOpen(true);
      else if (stored === "0") setOpen(false);
    } catch {
      /* storage unavailable: keep the default */
    }
  }, [key]);

  const set = useCallback(
    (next?: boolean) => {
      setOpen((current) => {
        const value = next ?? !current;
        try {
          window.localStorage.setItem(PREFIX + key, value ? "1" : "0");
        } catch {
          /* ignore */
        }
        return value;
      });
    },
    [key],
  );

  return [open, set];
}
