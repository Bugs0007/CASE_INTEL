import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

// Exact semantic badge colors from Design System.dc.html's "Semantic" swatch
// (status & priority badges only, never buttons).
const VARIANT_CLASSES = {
  default: "bg-gray-100 text-[#4b5468]", // Neutral
  success: "bg-[#e9f7f1] text-[#146349]",
  warning: "bg-[#fdf3e0] text-[#92610f]",
  attention: "bg-[#fdf0e4] text-[#9a4a12]",
  critical: "bg-[#f3ecfb] text-[#6b3aa0]",
  info: "bg-[#ebf3fb] text-[#2f6fb0]",
  danger: "bg-[#fdecec] text-[#b32e26]", // Error
} as const;

type BadgeVariant = keyof typeof VARIANT_CLASSES;

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
        "inline-flex items-center font-semibold rounded-full",
        VARIANT_CLASSES[variant],
        {
          "h-[22px] px-2.5 text-xs": size === "sm",
          "h-6 px-3 text-sm": size === "md",
        },
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
