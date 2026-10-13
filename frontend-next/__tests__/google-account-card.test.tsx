import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GoogleAccountCard } from "@/components/settings/google-account-card";
import type { AuthMe } from "@/lib/api/auth";

vi.mock("@/lib/api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/auth")>()),
  googleAccountApi: { me: vi.fn(), link: vi.fn(), unlink: vi.fn(), setPassword: vi.fn() },
}));
vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
// Google's real button needs the GIS script; stand in a button that "succeeds".
vi.mock("@/components/auth/google-sign-in", () => ({
  GoogleSignInButton: ({ onCredential }: { onCredential: (c: string) => void }) => (
    <button onClick={() => onCredential("fake-credential")}>Continue with Google</button>
  ),
}));

import { googleAccountApi } from "@/lib/api/auth";

function me(overrides: Partial<AuthMe> = {}): AuthMe {
  return {
    id: 1,
    username: "alice",
    email: "alice@example.com",
    has_password: true,
    google_linked: false,
    google_email: null,
    credentials_locked: false,
    ...overrides,
  };
}

beforeEach(() => vi.clearAllMocks());

describe("GoogleAccountCard", () => {
  it("connected: shows the Google email and disconnects", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(googleAccountApi.unlink).mockResolvedValue(undefined);
    render(
      <GoogleAccountCard me={me({ google_linked: true, google_email: "alice@gmail.com" })} onChanged={onChanged} configured />,
    );

    expect(screen.getByText("alice@gmail.com")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /disconnect/i }));

    await waitFor(() => expect(googleAccountApi.unlink).toHaveBeenCalled());
    expect(onChanged).toHaveBeenCalled();
  });

  it("connected without a password: Disconnect is disabled and says why", () => {
    render(
      <GoogleAccountCard
        me={me({ google_linked: true, google_email: "alice@gmail.com", has_password: false })}
        onChanged={vi.fn()}
        configured
      />,
    );

    expect(screen.getByRole("button", { name: /disconnect/i })).toBeDisabled();
    expect(screen.getByText(/set a password first/i)).toBeInTheDocument();
  });

  it("not connected: offers Google and links the credential it returns", async () => {
    const user = userEvent.setup();
    const onChanged = vi.fn();
    vi.mocked(googleAccountApi.link).mockResolvedValue({ google_email: "alice@gmail.com" });
    render(<GoogleAccountCard me={me()} onChanged={onChanged} configured />);

    expect(screen.queryByRole("button", { name: /disconnect/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /continue with google/i }));

    await waitFor(() => expect(googleAccountApi.link).toHaveBeenCalledWith("fake-credential"));
    expect(onChanged).toHaveBeenCalled();
  });

  it("not connected: shows the server's message when the Google account belongs to someone else", async () => {
    const user = userEvent.setup();
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(googleAccountApi.link).mockRejectedValue(
      new APIError(409, {
        code: "google_account_taken",
        detail: "That Google account is connected to a different Case Intel account.",
      }),
    );
    render(<GoogleAccountCard me={me()} onChanged={vi.fn()} configured />);

    await user.click(screen.getByRole("button", { name: /continue with google/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/different Case Intel account/);
  });

  it("locked: the whole card is hidden", () => {
    const { container } = render(
      <GoogleAccountCard me={me({ credentials_locked: true })} onChanged={vi.fn()} configured />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("not configured and not connected: nothing to show", () => {
    const { container } = render(<GoogleAccountCard me={me()} onChanged={vi.fn()} configured={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
