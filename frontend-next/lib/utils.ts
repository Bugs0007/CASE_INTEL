import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { format, formatDistanceToNow, parseISO } from "date-fns";
import type { ClientContact } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Inline style for a stagger-in fade at list index `i` -- delay is capped
 * so long lists don't leave the last rows waiting seconds to appear. */
export function staggerDelay(i: number, stepMs = 35, maxSteps = 10) {
  return { animationDelay: `${Math.min(i, maxSteps) * stepMs}ms` };
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

/** hearing_date is always midnight UTC -- eCourts only ever provides a
 * DATE for a hearing, never a time (Hearing.hearing_date is a
 * DateTimeField for historical/DB reasons and serializes with a "Z" UTC
 * suffix, but every row's time-of-day component is 00:00:00). Two
 * distinct problems follow from formatting it the normal (formatDate/
 * formatDateTime, i.e. parseISO + local-timezone format()) way:
 *
 *   1. A time component gets rendered at all -- fabricating one that
 *      looks like real data (00:00 UTC always renders as 5:30 AM in
 *      IST) when there never was one.
 *   2. Because the string carries a real UTC "Z" marker, parseISO()
 *      creates a Date representing that exact UTC instant, and format()
 *      then converts it to whatever timezone the CODE HAPPENS TO RUN IN
 *      (the browser's for a client render, the server process's for
 *      Next.js SSR -- these can differ) before reading off the
 *      calendar date. For any viewer/server west of UTC by enough to
 *      cross a day boundary, that can silently shift the displayed DAY,
 *      not just fabricate a time.
 *
 * Both are the same root mistake: treating a calendar date as if it
 * were a real moment in time and round-tripping it through a timezone.
 * This extracts the year/month/day directly from the stored string
 * instead -- no Date-to-UTC-instant parsing, no local-timezone
 * conversion, so the calendar date it displays can never depend on
 * where the code happens to be running. No formatStr parameter, on
 * purpose: always date-only, so a time-bearing override (the mistake
 * that caused this bug the first time -- see needs-attention.tsx's git
 * history) can't be reintroduced here. */
export function formatHearingDate(dateString: string | null | undefined): string {
  if (!dateString) return "";
  try {
    const [year, month, day] = dateString.slice(0, 10).split("-").map(Number);
    if (!year || !month || !day) return "";
    return format(new Date(year, month - 1, day), "MMM d, yyyy");
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

/** The `download/` endpoint returns a storage-relative URL on local disk
 * (e.g. "/media/documents/foo.pdf", same-origin to the Django backend --
 * NOT the Next.js frontend) or an absolute presigned S3 URL in production
 * (USE_S3=true). Absolute URLs are used as-is; relative ones are resolved
 * against the API host (API_BASE_URL minus its trailing "/api"), since
 * opening them relative to the frontend's own origin would 404. */
export function resolveFileUrl(url: string): string {
  if (/^https?:\/\//i.test(url)) return url;
  const apiBase =
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
  const backendOrigin = apiBase.replace(/\/api\/?$/, "");
  return `${backendOrigin}${url.startsWith("/") ? "" : "/"}${url}`;
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

/** The contact to lead with when showing "who's the client" for a case --
 * the designated billing contact, else whichever contact was added first
 * (client_contacts is ordered "-is_billing_contact", "name" by the API, so
 * this is just the first entry), else null when none exist yet (a case
 * fresh from advocate-search/import, before the details form is filled
 * in). */
export function primaryClientContact(contacts: ClientContact[]): ClientContact | null {
  return contacts.find((c) => c.is_billing_contact) ?? contacts[0] ?? null;
}

export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength - 3) + "...";
}

// getStatusColor/getPriorityColor (dead code, unused anywhere in the app)
// were removed during the case-intel-theme reskin -- StatusBadge/
// PriorityBadge in components/ui/badge.tsx are the single source of truth
// for status/priority color now, mapped onto the three ci-chip meanings.
