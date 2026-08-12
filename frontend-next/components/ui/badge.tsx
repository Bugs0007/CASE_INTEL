import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

// Every status/priority badge in the app resolves to one of the three chip
// meanings case-intel-theme.css defines -- ok (listed/paid/cleared),
// pending (awaiting), alert (failures/destructive) -- plus a neutral "none"
// for states that don't carry urgency at all. Call sites keep their
// original variant names (success/warning/critical/etc) so this map is the
// single place that enforces "status color meaning stays consistent
// everywhere, don't invent new status colors per screen."
const VARIANT_CHIP = {
  default: "none",
  success: "ok",
  warning: "pending",
  attention: "pending",
  critical: "alert",
  info: "none",
  danger: "alert",
} as const;

type BadgeVariant = keyof typeof VARIANT_CHIP;

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: "sm" | "md";
  className?: string;
}

export function Badge({
  children,
  variant = "default",
  size = "sm",
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "ci-chip inline-flex items-center flex-shrink-0",
        `ci-chip--${VARIANT_CHIP[variant]}`,
        size === "md" && "text-[11px] px-3 py-1",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, BadgeVariant> = {
    open: "success",
    active: "success",
    pending: "warning",
    closed: "default",
    archived: "default",
    scheduled: "info",
    completed: "success",
    cancelled: "danger",
    postponed: "warning",
    processing: "info",
    failed: "danger",
  };

  return (
    <Badge variant={variants[status] || "default"}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </Badge>
  );
}

export function PriorityBadge({ priority }: { priority: string }) {
  const variants: Record<string, BadgeVariant> = {
    low: "success",
    medium: "warning",
    high: "attention",
    critical: "critical",
  };

  return (
    <Badge variant={variants[priority] || "default"}>
      {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </Badge>
  );
}
