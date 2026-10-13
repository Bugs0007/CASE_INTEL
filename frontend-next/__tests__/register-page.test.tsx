import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { RegisterClient } from "@/app/register/register-client";

let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock("@/lib/api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/auth")>()),
  validateInvite: vi.fn(),
  googleLogin: vi.fn(),
  register: vi.fn(),
}));
vi.mock("@/lib/google-auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/google-auth")>()),
  GOOGLE_CLIENT_ID: "test-client-id",
}));
vi.mock("@/components/auth/google-sign-in", () => ({
  GoogleSignInButton: () => <button>Sign up with Google</button>,
  OrDivider: () => <div>or</div>,
}));

import { validateInvite } from "@/lib/api/auth";

beforeEach(() => {
  vi.clearAllMocks();
  search = "";
});

describe("RegisterClient", () => {
  it("without an invite token: only the Google button and the invite-link line", () => {
    render(<RegisterClient />);

    expect(screen.getByRole("button", { name: /sign up with google/i })).toBeInTheDocument();
    expect(
      screen.getByText(/Have an invite link\? Open it to sign up with a username and password\./),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/username/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^password/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create account/i })).not.toBeInTheDocument();
    expect(validateInvite).not.toHaveBeenCalled();
  });

  it("with a valid invite token: the username/password form appears alongside Google", async () => {
    search = "token=abc123";
    vi.mocked(validateInvite).mockResolvedValue({ valid: true, reason: null, email: "new@example.com" });

    render(<RegisterClient />);

    expect(await screen.findByLabelText("Username")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign up with google/i })).toBeInTheDocument();
    expect(validateInvite).toHaveBeenCalledWith("abc123");
  });

  it("with a spent invite token: no form, and the reason is shown", async () => {
    search = "token=used-one";
    vi.mocked(validateInvite).mockResolvedValue({ valid: false, reason: "used", email: null });

    render(<RegisterClient />);

    expect(await screen.findByText(/already been used/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Username")).not.toBeInTheDocument();
  });
});
