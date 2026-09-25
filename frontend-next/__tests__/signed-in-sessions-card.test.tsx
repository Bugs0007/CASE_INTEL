import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SignedInSessionsCard, describeDevice } from "@/components/settings/signed-in-sessions-card";
import type { AuthSessionRow } from "@/lib/api/auth";

vi.mock("@/lib/api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/auth")>()),
  authSessionsApi: { list: vi.fn(), revoke: vi.fn(), revokeOthers: vi.fn() },
}));
vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { authSessionsApi } from "@/lib/api/auth";

const CHROME_WIN = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36";
const SAFARI_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";

function row(overrides: Partial<AuthSessionRow>): AuthSessionRow {
  return {
    id: 1, source: "login", source_display: "Signed in", user_agent: CHROME_WIN, ip_address: "10.0.0.1",
    created_at: new Date().toISOString(), last_used_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(), current: false, ...overrides,
  };
}

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SignedInSessionsCard />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("SignedInSessionsCard", () => {
  it("names devices and marks this one, which can't be signed out from here", async () => {
    vi.mocked(authSessionsApi.list).mockResolvedValue([
      row({ id: 1, current: true }),
      row({ id: 2, user_agent: SAFARI_IOS }),
    ]);
    renderCard();

    expect(await screen.findByText("This device")).toBeInTheDocument();
    expect(screen.getByText("Safari on iOS")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /^sign out (?!all)/i })).toHaveLength(1);
  });

  it("signs one other device out", async () => {
    const user = userEvent.setup();
    vi.mocked(authSessionsApi.list).mockResolvedValue([row({ id: 1, current: true }), row({ id: 2, user_agent: SAFARI_IOS })]);
    vi.mocked(authSessionsApi.revoke).mockResolvedValue(undefined);
    renderCard();

    await user.click(await screen.findByRole("button", { name: "Sign out Safari on iOS" }));

    await waitFor(() => expect(authSessionsApi.revoke).toHaveBeenCalledWith(2));
  });

  it("signs every other device out at once", async () => {
    const user = userEvent.setup();
    vi.mocked(authSessionsApi.list).mockResolvedValue([row({ id: 1, current: true }), row({ id: 2 }), row({ id: 3 })]);
    vi.mocked(authSessionsApi.revokeOthers).mockResolvedValue({ revoked: 2 });
    renderCard();

    await user.click(await screen.findByRole("button", { name: /sign out all other devices/i }));

    await waitFor(() => expect(authSessionsApi.revokeOthers).toHaveBeenCalled());
  });

  it("describes common browsers", () => {
    expect(describeDevice(CHROME_WIN)).toBe("Chrome on Windows");
    expect(describeDevice("")).toBe("Unknown device");
  });
});
