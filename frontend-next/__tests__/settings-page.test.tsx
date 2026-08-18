import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SettingsPage from "@/app/(dashboard)/settings/page";
import type { AdvocateProfile } from "@/types";

// This page previously did not exist -- the billing profile could only be
// set via `manage.py setup_demo_account` flags, which isn't viable for a
// real end user. These tests hit the real advocateProfileApi (mocked only
// at the network boundary) to prove a user can actually set it through
// the UI now.
vi.mock("@/lib/api/billing", () => ({
  advocateProfileApi: {
    get: vi.fn(),
    update: vi.fn(),
  },
  appearanceFeesApi: {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    generateInvoice: vi.fn(),
    invoiceFile: vi.fn(),
    send: vi.fn(),
    markPaid: vi.fn(),
  },
  travelBookingsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    file: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

import { advocateProfileApi } from "@/lib/api/billing";
import { showToast } from "@/components/ui/toaster";

function makeProfile(overrides: Partial<AdvocateProfile> = {}): AdvocateProfile {
  return {
    id: 1,
    letterhead_name: "",
    address: "",
    bar_registration_number: "",
    contact_email: "",
    default_fee_amount: "0.00",
    invoice_prefix: "INV",
    last_invoice_sequence: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("SettingsPage", () => {
  it("loads the real advocate profile and pre-fills the form", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(
      makeProfile({ letterhead_name: "S. Bhagath, Advocate", bar_registration_number: "AP/1234/2015" }),
    );

    renderWithClient(<SettingsPage />);

    expect(await screen.findByDisplayValue("S. Bhagath, Advocate")).toBeInTheDocument();
    expect(screen.getByDisplayValue("AP/1234/2015")).toBeInTheDocument();
    expect(advocateProfileApi.get).toHaveBeenCalledTimes(1);
  });

  it("saves letterhead edits against the real advocateProfileApi.update endpoint", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
    vi.mocked(advocateProfileApi.update).mockResolvedValue(
      makeProfile({ letterhead_name: "S. Bhagath, Advocate", bar_registration_number: "AP/1234/2015" }),
    );

    renderWithClient(<SettingsPage />);

    const nameInput = await screen.findByLabelText(/name \/ firm/i);
    await user.type(nameInput, "S. Bhagath, Advocate");
    await user.type(screen.getByLabelText(/bar registration number/i), "AP/1234/2015");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(advocateProfileApi.update).toHaveBeenCalledWith(
        expect.objectContaining({
          letterhead_name: "S. Bhagath, Advocate",
          bar_registration_number: "AP/1234/2015",
        }),
      );
    });
    expect(showToast.success).toHaveBeenCalledWith(
      "Billing profile saved",
      expect.any(String),
    );
  });

  it("loads and pre-fills an existing contact email", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(
      makeProfile({ contact_email: "advocate@example.com" }),
    );

    renderWithClient(<SettingsPage />);

    expect(await screen.findByDisplayValue("advocate@example.com")).toBeInTheDocument();
  });

  it("saves a contact email edit, separate from the account login email", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
    vi.mocked(advocateProfileApi.update).mockResolvedValue(
      makeProfile({ contact_email: "advocate@example.com" }),
    );

    renderWithClient(<SettingsPage />);

    const emailInput = await screen.findByLabelText(/contact email/i);
    await user.type(emailInput, "advocate@example.com");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(advocateProfileApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ contact_email: "advocate@example.com" }),
      );
    });
    expect(showToast.success).toHaveBeenCalledWith(
      "Billing profile saved",
      expect.any(String),
    );
  });

  it("saves cleanly with the contact email left blank", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
    vi.mocked(advocateProfileApi.update).mockResolvedValue(makeProfile());

    renderWithClient(<SettingsPage />);

    await screen.findByLabelText(/contact email/i);
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(advocateProfileApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ contact_email: "" }),
      );
    });
    expect(showToast.error).not.toHaveBeenCalled();
  });

  it("surfaces the server's validation message for a malformed contact email", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(advocateProfileApi.update).mockRejectedValue(
      new APIError(400, { contact_email: ["Enter a valid email address."] }),
    );

    renderWithClient(<SettingsPage />);

    const emailInput = await screen.findByLabelText(/contact email/i);
    await user.type(emailInput, "not-an-email");
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(showToast.error).toHaveBeenCalledWith(
        "Could not save",
        expect.stringContaining("Enter a valid email address."),
      );
    });
  });

  it("warns instead of blocking when a save fails, surfacing the server's message", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(advocateProfileApi.update).mockRejectedValue(
      new APIError(400, { default_fee_amount: ["A valid number is required."] }),
    );

    renderWithClient(<SettingsPage />);

    await screen.findByLabelText(/name \/ firm/i);
    await user.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => {
      expect(showToast.error).toHaveBeenCalledWith(
        "Could not save",
        expect.stringContaining("A valid number is required."),
      );
    });
  });
});
