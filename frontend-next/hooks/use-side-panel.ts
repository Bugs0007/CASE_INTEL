import { useCallback, useEffect, useState } from "react";

export const SIDE_PANEL_STORAGE_KEY = "case-intel:case-side-panel";

/** Whether the case page's side rail is shown, remembered across visits.
 *
 * Starts open and reads the saved choice after mount (the server has no
 * localStorage); the page does not render the rail until its data arrives,
 * which is after this has run. */
export function useSidePanel() {
  const [open, setOpen] = useState(true);

  useEffect(() => {
    try {
      if (localStorage.getItem(SIDE_PANEL_STORAGE_KEY) === "closed") setOpen(false);
    } catch {
      // Storage can be unavailable (private mode); the panel just stays open.
    }
  }, []);

  const toggle = useCallback(() => {
    setOpen((current) => {
      const next = !current;
      try {
        localStorage.setItem(SIDE_PANEL_STORAGE_KEY, next ? "open" : "closed");
      } catch {
        // Not remembered, still toggles.
      }
      return next;
    });
  }, []);

  return { open, toggle };
}
