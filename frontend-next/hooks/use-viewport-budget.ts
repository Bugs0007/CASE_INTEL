"use client";

import { useEffect, useMemo, useState } from "react";
import { pageBudget, type PageBudget } from "@/lib/case-page-budget";

/** The case page's row budget for the current window (lib/case-page-budget.ts).
 * Follows the window as it is resized. */
export function useViewportBudget(): PageBudget {
  const [size, setSize] = useState(() =>
    typeof window === "undefined"
      ? { width: 1536, height: 864 }
      : { width: window.innerWidth, height: window.innerHeight },
  );

  useEffect(() => {
    const onResize = () => setSize({ width: window.innerWidth, height: window.innerHeight });
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return useMemo(() => pageBudget(size.width, size.height), [size.width, size.height]);
}
