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

function authHeader(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Token ${token}` } : {};
}

function handleUnauthorized(status: number) {
  if (status === 401 && typeof window !== "undefined") {
    clearToken();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
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

  const response = await fetch(url.toString(), {
    ...config,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...config.headers,
    },
  });

  if (!response.ok) {
    handleUnauthorized(response.status);
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

  const response = await fetch(url.toString(), {
    ...config,
    headers: {
      ...authHeader(),
      ...config.headers,
    },
  });

  if (!response.ok) {
    handleUnauthorized(response.status);
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
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    body: formData,
    // Don't set Content-Type - browser sets it with boundary
    headers: {
      ...authHeader(),
    },
  });

  if (!response.ok) {
    handleUnauthorized(response.status);
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  return response.json();
}
