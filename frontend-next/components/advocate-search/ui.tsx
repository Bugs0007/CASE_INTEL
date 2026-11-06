"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { MatchStatus } from "@/types";

// Small pieces shared by the redesigned advocate search screens.

/** A card whose body can shrink and scroll: `min-h-0` all the way down, so the
 * page itself never scrolls. */
export function Panel({
  title,
  icon,
  sub,
  action,
  children,
  className,
  bodyClassName,
  label,
}: {
  title: ReactNode;
  icon?: ReactNode;
  sub?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  label?: string;
}) {
  return (
    <section
      aria-label={label ?? (typeof title === "string" ? title : undefined)}
      className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-surface", className)}
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-gray-200 px-4 py-2.5">
        {icon && <span className="text-gray-700">{icon}</span>}
        <h2 className="whitespace-nowrap font-serif text-[17px] font-bold text-gray-900">{title}</h2>
        {sub && <span className="min-w-0 truncate text-xs text-gray-500">{sub}</span>}
        <span className="flex-1" />
        {action}
      </header>
      <div className={cn("flex min-h-0 flex-1 flex-col gap-3 p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("mb-1.5 block font-mono text-[10.5px] font-medium uppercase tracking-[0.1em] text-gray-500", className)}>
      {children}
    </span>
  );
}

/** A segmented control (Pending / Disposed / Both). */
export function Seg<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex overflow-hidden rounded-md border border-gray-200">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "px-3 py-1.5 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary",
            value === o.value ? "bg-primary text-page" : "text-gray-600 hover:bg-gray-100",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const CHIP: Record<MatchStatus, string> = {
  matched: "bg-status-ok-soft text-status-ok",
  check: "bg-status-pending-soft text-status-pending",
  excluded: "bg-status-alert-soft text-status-alert",
  other: "bg-gray-100 text-gray-600",
};

export function MatchChip({ status, label, className }: { status: MatchStatus; label?: string; className?: string }) {
  const text = label || { matched: "Your name", check: "Check name", excluded: "Hidden (Not me)", other: "Other name" }[status];
  return (
    <span className={cn("inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold", CHIP[status], className)}>
      {text}
    </span>
  );
}

export function Notice({ tone = "info", children, className }: { tone?: "info" | "warn" | "alert"; children: ReactNode; className?: string }) {
  return (
    <div
      role={tone === "alert" ? "alert" : undefined}
      className={cn(
        "flex gap-2 rounded-md border px-3 py-2 text-xs",
        tone === "info" && "border-gray-200 bg-gray-50 text-gray-600",
        tone === "warn" && "border-status-pending bg-status-pending-soft text-status-pending",
        tone === "alert" && "border-status-alert bg-status-alert-soft text-status-alert",
        className,
      )}
    >
      {children}
    </div>
  );
}
