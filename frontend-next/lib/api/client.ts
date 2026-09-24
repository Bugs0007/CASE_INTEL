import { clearToken, getToken } from "@/lib/auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export class APIError extends Error {
  constructor(
    public status: number,
    public data: unknown,
    message?: string,
  ) {
    super(message || `API Error: ${status}`);
    this.name = "APIError";
  }
}

interface RequestConfig extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

/** Send `url` with the CURRENT token, and survive the one 401 that isn't
 * really a sign-out.
 *
 * DRF tokens here don't expire and there is no refresh token: a 401 means
 * the token this request carried was deleted server-side -- a logout (the
 * token is one per USER, so logging out anywhere, e.g. another tab or
 * another person on a shared account, kills it everywhere) or a password
 * change. If another tab has since signed in again, localStorage already
 * holds a newer token: retry once with it instead of throwing the user
 * out. Only when the token that failed is still the stored one is the
 * session really gone -- then it's cleared and the user sent to /login
 * with a way back to where they were.
 *
 * Before this, any 401 wiped the token and hard-redirected mid-click
 * ("one Generate click redirected to /login"). */
async function authedFetch(url: string, init: RequestInit, headers: Record<string, string>): Promise<Response> {
  const sentToken = getToken();
  const withToken = (token: string | null) => ({
    ...init,
    headers: { ...headers, ...(token ? { Authorization: `Token ${token}` } : {}), ...(init.headers as Record<string, string> | undefined) },
  });
  let response = await fetch(url, withToken(sentToken));
  if (response.status === 401) {
    const current = getToken();
    if (current && current !== sentToken) {
      response = await fetch(url, withToken(current));
    }
    if (response.status === 401) signOutIfStillCurrent(current ?? sentToken);
  }
  return response;
}

function signOutIfStillCurrent(failedToken: string | null) {
  if (typeof window === "undefined") return;
  // Another tab may have signed in while this request was in flight.
  if (getToken() !== failedToken) return;
  clearToken();
  const { pathname, search } = window.location;
  if (pathname !== "/login") {
    const next = encodeURIComponent(pathname + search);
    window.location.href = `/login?next=${next}&expired=1`;
  }
}

/** The most useful message in a DRF error body: "detail" if present, else
 * the first field error. Falls back to `fallback`. */
export function apiErrorDetail(error: unknown, fallback: string): string {
  if (error instanceof APIError && error.data && typeof error.data === "object") {
    const body = error.data as Record<string, unknown>;
    if (typeof body.detail === "string" && body.detail) return body.detail;
    for (const value of Object.values(body)) {
      const message = Array.isArray(value) ? value[0] : value;
      if (typeof message === "string" && message) return message;
    }
  }
  return fallback;
}

export async function apiClient<T>(
  endpoint: string,
  { params, ...config }: RequestConfig = {},
): Promise<T> {
  const url = new URL(`${API_BASE_URL}${endpoint}`);

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await authedFetch(url.toString(), config, { "Content-Type": "application/json" });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

/** Like apiClient, but returns the raw response body as a Blob.
 *
 * For endpoints that stream a file rather than JSON (e.g. an order PDF at
 * /orders/<id>/file/). Fetching instead of linking is what lets the
 * `Authorization: Token` header ride along -- a plain <a target="_blank">
 * can't send headers, and those endpoints deliberately have no
 * unauthenticated URL to link to. */
export async function apiBlob(
  endpoint: string,
  { params, ...config }: RequestConfig = {},
): Promise<Blob> {
  const url = new URL(`${API_BASE_URL}${endpoint}`);

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const response = await authedFetch(url.toString(), config, {});

  if (!response.ok) {
    // Errors from these endpoints are still JSON (DRF Response), even
    // though a success is binary.
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  return response.blob();
}

export async function uploadFile<T>(
  endpoint: string,
  formData: FormData,
): Promise<T> {
  // Don't set Content-Type - browser sets it with boundary
  const response = await authedFetch(`${API_BASE_URL}${endpoint}`, { method: "POST", body: formData }, {});

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  return response.json();
}
