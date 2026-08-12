"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import styles from "../walkthrough.module.css";

interface SpotlightProps {
  /** This scene's own key for the element it renders here. */
  id: string;
  /** The tour's currently-highlighted key. Spotlight is on when these match. */
  active: string;
  children: ReactNode;
  className?: string;
}

/** Wraps one piece of a mock scene so the tour can spotlight it -- darkens
 * everything else on the stage via a huge box-shadow and scrolls itself
 * into view when it becomes the active target. Purely local/visual: no
 * network activity, no external state. */
export function Spotlight({ id, active, children, className }: SpotlightProps) {
  const ref = useRef<HTMLDivElement>(null);
  const isActive = id === active;

  useEffect(() => {
    if (isActive) {
      ref.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [isActive]);

  return (
    <div
      ref={ref}
      data-tour={id}
      className={cn(className, isActive && styles.spotlight)}
    >
      {children}
    </div>
  );
}
