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
      ...config.headers,
    },
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export async function uploadFile<T>(
  endpoint: string,
  formData: FormData,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    method: "POST",
    body: formData,
    // Don't set Content-Type - browser sets it with boundary
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, data);
  }

  return response.json();
}
