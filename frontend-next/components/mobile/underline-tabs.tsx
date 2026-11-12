"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface UnderlineTab<K extends string> {
  key: K;
  label: ReactNode;
}

/** A row of tabs with an underline that glides between them (a transform:
 * translateX + scaleX), for the sticky strip under the phone's top bar.
 * Scrolls sideways inside itself if the tabs do not fit. */
export function UnderlineTabs<K extends string>({
  label,
  tabs,
  active,
  onChange,
}: {
  /** Accessible name of the tab list. */
  label: string;
  tabs: UnderlineTab<K>[];
  active: K;
  onChange: (key: K) => void;
}) {
  const refs = useRef<Partial<Record<string, HTMLButtonElement>>>({});
  const [mark, setMark] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const el = refs.current[active];
    if (el) setMark({ left: el.offsetLeft, width: el.offsetWidth });
  }, [active, tabs.length]);

  return (
    <div role="tablist" aria-label={label} className="ci-hscroll relative h-full items-stretch !gap-0 px-2">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          ref={(el) => {
            refs.current[tab.key] = el ?? undefined;
          }}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "flex h-full items-center gap-1.5 px-3.5 text-[13.5px] font-semibold transition-colors",
            active === tab.key ? "text-gray-900" : "text-gray-500",
          )}
        >
          {tab.label}
        </button>
      ))}
      {mark && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-0 left-0 h-[3px] w-[100px] origin-left bg-[var(--ci-ink)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
          style={{ transform: `translateX(${mark.left}px) scaleX(${mark.width / 100})` }}
        />
      )}
    </div>
  );
}
