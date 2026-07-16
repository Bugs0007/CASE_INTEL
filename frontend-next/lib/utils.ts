import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow, parseISO } from "date-fns";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(
  dateString: string | null | undefined,
  formatStr: string = "MMM d, yyyy",
): string {
  if (!dateString) return "";
  try {
    return format(parseISO(dateString), formatStr);
  } catch {
    return "";
  }
}

export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return "";
  try {
    return format(parseISO(dateString), "MMM d, yyyy h:mm a");
  } catch {
    return "";
  }
}

/** Converts an ISO datetime string to the "yyyy-MM-ddTHH:mm" shape an
 * `<input type="datetime-local">` expects. */
export function toDatetimeLocal(dateString: string | null | undefined): string {
  if (!dateString) return "";
  try {
    return format(parseISO(dateString), "yyyy-MM-dd'T'HH:mm");
  } catch {
    return "";
  }
}

export function formatRelativeTime(
  dateString: string | null | undefined,
): string {
  if (!dateString) return "";
  try {
    return formatDistanceToNow(parseISO(dateString), { addSuffix: true });
  } catch {
    return "";
  }
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

export function getFileIcon(fileType: string | null): string {
  const type = fileType?.toLowerCase() || "";
  if (type.includes("pdf")) return "📄";
  if (type.includes("doc") || type.includes("docx")) return "📝";
  if (type.includes("xls") || type.includes("xlsx")) return "📊";
  if (type.includes("msg") || type.includes("eml")) return "📧";
  if (type.includes("txt")) return "📃";
  return "📎";
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    open: "bg-green-100 text-green-800",
    active: "bg-green-100 text-green-800",
    pending: "bg-yellow-100 text-yellow-800",
    closed: "bg-gray-100 text-gray-800",
    archived: "bg-gray-100 text-gray-600",
    scheduled: "bg-blue-100 text-blue-800",
    completed: "bg-green-100 text-green-800",
    cancelled: "bg-red-100 text-red-800",
    postponed: "bg-orange-100 text-orange-800",
  };
  return colors[status] || "bg-gray-100 text-gray-800";
}

export function getPriorityColor(priority: string): string {
  const colors: Record<string, string> = {
    low: "bg-green-100 text-green-800",
    medium: "bg-yellow-100 text-yellow-800",
    high: "bg-orange-100 text-orange-800",
    critical: "bg-red-100 text-red-800",
  };
  return colors[priority] || "bg-gray-100 text-gray-800";
}
