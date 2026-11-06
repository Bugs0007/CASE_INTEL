import { APIError } from "@/lib/api/client";

/** One readable sentence for a failed request: the server's own `detail`, else
 * the first field error (DRF validation), else `fallback`. */
export function apiErrorText(error: unknown, fallback: string): string {
  if (error instanceof APIError && error.data && typeof error.data === "object") {
    const data = error.data as Record<string, unknown>;
    if (typeof data.detail === "string") return data.detail;
    for (const value of Object.values(data)) {
      if (Array.isArray(value) && typeof value[0] === "string") return value[0];
      if (typeof value === "string") return value;
    }
  }
  return fallback;
}
