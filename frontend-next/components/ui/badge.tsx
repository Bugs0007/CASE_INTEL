import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "purple";
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
        "inline-flex items-center font-medium rounded-full",
        {
          "bg-gray-100 text-gray-800": variant === "default",
          "bg-green-100 text-green-800": variant === "success",
          "bg-yellow-100 text-yellow-800": variant === "warning",
          "bg-red-100 text-red-800": variant === "danger",
          "bg-blue-100 text-blue-800": variant === "info",
          "bg-purple-100 text-purple-800": variant === "purple",
        },
        {
          "px-2 py-0.5 text-xs": size === "sm",
          "px-2.5 py-1 text-sm": size === "md",
        },
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const variants: Record<
    string,
    "success" | "warning" | "default" | "danger" | "info"
  > = {
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
  const variants: Record<string, "success" | "warning" | "danger" | "purple"> =
    {
      low: "success",
      medium: "warning",
      high: "danger",
      critical: "purple",
    };

  return (
    <Badge variant={variants[priority] || "default"}>
      {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </Badge>
  );
}
