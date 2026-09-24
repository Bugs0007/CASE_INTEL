import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiClient, APIError } from "@/lib/api/client";

// The token is one per USER and never expires: a 401 means it was deleted
// (a logout anywhere, a password change). Production bug: one click on
// Generate redirected to /login. A newer token saved by another tab must be
// retried, and only a genuinely dead session may clear it and redirect.

const originalLocation = window.location;

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  window.localStorage.clear();
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { pathname: "/cases/28", search: "?tab=docs", href: "http://localhost/cases/28?tab=docs" },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
});

describe("apiClient on a 401", () => {
  it("retries once with a newer token another tab saved, and keeps the session", async () => {
    window.localStorage.setItem("case_intel_token", "old-token");
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      const auth = (init.headers as Record<string, string>).Authorization;
      if (auth === "Token old-token") {
        // Another tab signed in again while this request was in flight.
        window.localStorage.setItem("case_intel_token", "new-token");
        return jsonResponse(401, { detail: "Invalid token." });
      }
      return jsonResponse(200, { ok: true });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiClient("/cases/28/")).resolves.toEqual({ ok: true });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(window.localStorage.getItem("case_intel_token")).toBe("new-token");
    expect(window.location.href).toBe("http://localhost/cases/28?tab=docs");
  });

  it("clears a dead session and sends the user to /login with a way back", async () => {
    window.localStorage.setItem("case_intel_token", "dead-token");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { detail: "Invalid token." })));

    await expect(apiClient("/doc-templates/")).rejects.toBeInstanceOf(APIError);

    expect(window.localStorage.getItem("case_intel_token")).toBeNull();
    expect(window.location.href).toBe(`/login?next=${encodeURIComponent("/cases/28?tab=docs")}&expired=1`);
  });

  it("leaves other errors alone", async () => {
    window.localStorage.setItem("case_intel_token", "good-token");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(403, { detail: "Nope." })));

    await expect(apiClient("/x/")).rejects.toBeInstanceOf(APIError);

    expect(window.localStorage.getItem("case_intel_token")).toBe("good-token");
    expect(window.location.href).toBe("http://localhost/cases/28?tab=docs");
  });
});
