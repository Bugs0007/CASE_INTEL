import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClientMessageCard } from "@/components/client-updates/client-message-card";
import type { ClientMessage, SendClientMessageResult } from "@/types";

vi.mock("@/lib/api/clients", () => ({
  clientMessagesApi: { list: vi.fn(), update: vi.fn(), discard: vi.fn(), send: vi.fn() },
  clientsApi: {},
  billingPortfolioApi: {},
  sentMessagesApi: {},
  docTemplatesApi: {},
  refreshAllApi: {},
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { clientMessagesApi } from "@/lib/api/clients";
import { showToast } from "@/components/ui/toaster";

function makeMessage(overrides: Partial<ClientMessage> = {}): ClientMessage {
  return {
    id: 5,
    case: 3,
    case_title: "OS/10/2026 Rao vs Reddy",
    case_number: "OS/10/2026",
    kind: "case_update",
    kind_display: "Case update",
    status: "draft",
    status_display: "Draft",
    subject: "Update on your matter",
    body: "Dear Client One,\n\nThe matter was heard on 01 September 2026.",
    recipients: [{ contact_id: 9, name: "Client One", email: "one@example.com" }],
    eligible_recipients: [{ contact_id: 9, name: "Client One", email: "one@example.com" }],
    edited_by_user: false,
    reminder_number: null,
    fee: null,
    invoice_number: null,
    hearing: null,
    hearing_date: null,
    court_order: null,
    sent_at: null,
    discard_reason: "",
    created_at: "2026-09-02T00:00:00Z",
    updated_at: "2026-09-02T00:00:00Z",
    ...overrides,
  };
}

function sendResult(overrides: Partial<SendClientMessageResult> = {}): SendClientMessageResult {
  return {
    sent: true,
    recipients: ["one@example.com"],
    detail: "Sent to one@example.com.",
    missing_env_vars: [],
    required_env_vars: [],
    message: makeMessage({ status: "sent" }),
    ...overrides,
  };
}

function renderCard(message: ClientMessage) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ClientMessageCard message={message} defaultOpen />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe("ClientMessageCard", () => {
  it("reports a real delivery as sent", async () => {
    const user = userEvent.setup();
    vi.mocked(clientMessagesApi.send).mockResolvedValue(sendResult());
    renderCard(makeMessage());

    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() => expect(clientMessagesApi.send).toHaveBeenCalledWith(5));
    expect(showToast.success).toHaveBeenCalledWith("Update sent", "Emailed to one@example.com.");
    expect(showToast.warning).not.toHaveBeenCalled();
  });

  it("reports a logged-only send distinctly, naming the missing settings", async () => {
    const user = userEvent.setup();
    vi.mocked(clientMessagesApi.send).mockResolvedValue(
      sendResult({
        sent: false,
        detail: "Email is not configured on this server, so the message was logged instead of sent.",
        missing_env_vars: ["RESEND_API_KEY"],
        message: makeMessage({ status: "logged" }),
      }),
    );
    renderCard(makeMessage());

    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() =>
      expect(showToast.warning).toHaveBeenCalledWith(
        "Update logged, not emailed",
        expect.stringContaining("Missing: RESEND_API_KEY."),
      ),
    );
    expect(showToast.success).not.toHaveBeenCalled();
  });

  it("names a payment reminder as a reminder", async () => {
    const user = userEvent.setup();
    vi.mocked(clientMessagesApi.send).mockResolvedValue(sendResult({ sent: false, missing_env_vars: [] }));
    renderCard(makeMessage({ kind: "payment_reminder", kind_display: "Payment reminder" }));

    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() =>
      expect(showToast.warning).toHaveBeenCalledWith("Reminder logged, not emailed", expect.any(String)),
    );
  });

  it("saves edits before sending", async () => {
    const user = userEvent.setup();
    vi.mocked(clientMessagesApi.update).mockResolvedValue(makeMessage({ body: "Edited" }));
    vi.mocked(clientMessagesApi.send).mockResolvedValue(sendResult());
    renderCard(makeMessage());

    const body = screen.getByLabelText(/message/i);
    await user.clear(body);
    await user.type(body, "Edited");
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    await waitFor(() =>
      expect(clientMessagesApi.update).toHaveBeenCalledWith(5, expect.objectContaining({ body: "Edited" })),
    );
    expect(clientMessagesApi.send).toHaveBeenCalledWith(5);
  });

  it("refuses to send with no recipient ticked", async () => {
    const user = userEvent.setup();
    renderCard(makeMessage());

    await user.click(screen.getByRole("checkbox", { name: /client one/i }));
    await user.click(screen.getByRole("button", { name: /^send$/i }));

    expect(clientMessagesApi.send).not.toHaveBeenCalled();
    expect(showToast.error).toHaveBeenCalledWith("No recipients", expect.any(String));
  });

  it("shows a logged message as never delivered", () => {
    renderCard(makeMessage({ status: "logged", status_display: "Logged only (email not configured)", eligible_recipients: [] }));
    expect(screen.getByText("Logged, not emailed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^send$/i })).not.toBeInTheDocument();
  });
});
