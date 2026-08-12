"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TOUR_STEPS } from "./tour-steps";
import { TourChrome } from "./components/tour-chrome";
import { TourBar } from "./components/tour-bar";
import { DashboardScene } from "./components/dashboard-scene";
import { SearchScene } from "./components/search-scene";
import { CaseDetailScene } from "./components/case-detail-scene";
import { TravelScene } from "./components/travel-scene";
import styles from "./walkthrough.module.css";

/**
 * The whole tour is client-side state over a fixed script (TOUR_STEPS) --
 * there is no data fetching anywhere in this tree. Every scene renders
 * hardcoded mock data from mock-data.ts, and every interactive control in
 * them (the invoice buttons, the search checkboxes, etc) only ever calls a
 * local useState setter. The only real navigation is "Skip tour" / "Exit",
 * which leaves this route entirely for the real, authenticated app.
 */
export function WalkthroughClient() {
  const router = useRouter();
  const [stepIndex, setStepIndex] = useState(0);
  const step = TOUR_STEPS[stepIndex];
  const total = TOUR_STEPS.length;

  const goNext = useCallback(() => {
    setStepIndex((i) => Math.min(i + 1, total - 1));
  }, [total]);
  const goBack = useCallback(() => {
    setStepIndex((i) => Math.max(i - 1, 0));
  }, []);
  const restart = useCallback(() => setStepIndex(0), []);
  const exit = useCallback(() => router.push("/dashboard"), [router]);

  // Arrow-key navigation, purely a UX nicety on top of the same handlers.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "ArrowRight") goNext();
      if (e.key === "ArrowLeft") goBack();
      if (e.key === "Escape") exit();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [goNext, goBack, exit]);

  return (
    <TourChrome>
      <div className={styles.stage}>
        <div key={step.id} className={styles.fadeSwap}>
          {step.scene === "dashboard" && <DashboardScene highlight={step.highlightKey} />}
          {step.scene === "search" && (
            <SearchScene highlight={step.highlightKey} sceneState={step.sceneState} />
          )}
          {step.scene === "case-detail" && <CaseDetailScene highlight={step.highlightKey} />}
          {step.scene === "travel" && <TravelScene highlight={step.highlightKey} />}
        </div>
      </div>

      <TourBar
        step={step}
        index={stepIndex}
        total={total}
        onBack={goBack}
        onNext={goNext}
        onExit={exit}
        onRestart={restart}
      />
    </TourChrome>
  );
}
