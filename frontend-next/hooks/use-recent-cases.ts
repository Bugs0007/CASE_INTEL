import { useEffect, useState } from "react";
import { getUsername } from "@/lib/auth";
import { RECENT_CASES_EVENT, readRecentCases, type RecentCase } from "@/lib/recent-cases";

/** The sidebar's recent cases for the signed-in user. Read after mount
 * (the server has no localStorage) and kept current when a case page is
 * opened in this tab or the list changes in another one. */
export function useRecentCases(): RecentCase[] {
  const [items, setItems] = useState<RecentCase[]>([]);

  useEffect(() => {
    const read = () => setItems(readRecentCases(getUsername()));
    read();
    window.addEventListener(RECENT_CASES_EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(RECENT_CASES_EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, []);

  return items;
}
