// app/page.tsx — Case Intel landing page ("Night Board").
// The page itself lives in app/_landing/ (a private folder, not a route).
// Server component so the landing page can carry its own metadata; the
// login→dashboard switch (getToken) lives client-side in _landing/ui/bits.tsx.

import type { Metadata } from "next";
import NightBoard from "./_landing/night-board";
import "./landing.css";

export const metadata: Metadata = {
  title: "Case Intel · Tonight's cause list, already read",
  description:
    "Case management for advocates practising before Indian courts: state-wide advocate search, order summaries that become tasks, cause lists from the Telangana High Court, most other High Courts and the District Courts read every evening and morning, and a case-file assistant that cites its sources. Sign up with Google.",
};

export default function Page() {
  return <NightBoard />;
}
