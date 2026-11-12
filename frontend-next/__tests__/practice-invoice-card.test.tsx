import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({ overview: vi.fn(), chat: vi.fn(), send: vi.fn() }));

vi.mock("@/lib/api/practice", () => ({
  practiceApi: { overview: mocks.overview, chat: mocks.chat },
}));

vi.mock("@/lib/api/billing", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/billing")>();
  return { ...actual, appearanceFeesApi: { ...actual.appearanceFeesApi, send: mocks.send } };
});

import { APIError } from "@/lib/api/client";
import { PracticeChat } from "@/components/assistant/practice-chat";
import { PracticeInvoiceActionCard } from "@/components/dashboard/practice/practice-invoice-action-card";
import {
  blockedActionCard,
  clearActionCard,
  sampleCalendar,
  samplePortfolio,
  sampleTurn,
} from "@/components/dashboard/practice/fixtures";
import type { PracticeTurn } from "@/types/practice";

const cardTurn: PracticeTurn = { ...sampleTurn, intent: "propose_invoice_send", action_card: clearActionCard };
const sendResult = { recipient: "rao@example.com", detail: "", missing_env_vars: [], required_env_vars: [], fee: {} };

function renderContainer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PracticeChat conversationId={null} onConversationChange={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.overview.mockReset().mockResolvedValue({ portfolio: samplePortfolio, calendar: sampleCalendar });
  mocks.chat.mockReset().mockResolvedValue(cardTurn);
  mocks.send.mockReset();
});

describe("PracticeInvoiceActionCard", () => {
  it("has no send control with blockers", () => {
    render(<PracticeInvoiceActionCard card={blockedActionCard} onConfirm={vi.fn()} onDismiss={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Send invoice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
    expect(screen.getByText(blockedActionCard.blockers[0])).toBeInTheDocument();
  });

  it("rendering alone calls nothing", () => {
    const onConfirm = vi.fn();
    render(<PracticeInvoiceActionCard card={clearActionCard} onConfirm={onConfirm} onDismiss={vi.fn()} />);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("click then confirm calls onConfirm once with the fee id of the card", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<PracticeInvoiceActionCard card={clearActionCard} onConfirm={onConfirm} onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText("Send invoice INV-0007 to rao@example.com?")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith(clearActionCard.fee_id);
  });

  it("cancel sends nothing and goes back to the first step", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<PracticeInvoiceActionCard card={clearActionCard} onConfirm={onConfirm} onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Send invoice" })).toBeInTheDocument();
  });

  it("a double click on Confirm confirms once", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<PracticeInvoiceActionCard card={clearActionCard} onConfirm={onConfirm} onDismiss={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});

describe("invoice card in the Case Bot practice chat", () => {
  async function openCard() {
    const user = userEvent.setup();
    renderContainer();
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    await screen.findByRole("region", { name: "Invoice to send" });
    return user;
  }

  it("a replayed card sends nothing until clicked and confirmed", async () => {
    await openCard();
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("sends through the existing endpoint once, even on a double click", async () => {
    mocks.send.mockResolvedValue({ ...sendResult, sent: true });
    const user = await openCard();
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Invoice sent to rao@example.com.");
    expect(mocks.send).toHaveBeenCalledTimes(1);
    expect(mocks.send).toHaveBeenCalledWith(clearActionCard.fee_id);
    expect(screen.queryByRole("region", { name: "Invoice to send" })).not.toBeInTheDocument();
  });

  it("a logged result says mail is not configured and never claims it was sent", async () => {
    mocks.send.mockResolvedValue({ ...sendResult, sent: false, detail: "x" });
    const user = await openCard();
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Mail is not configured on this server. The send was recorded but no email went out.");
    expect(screen.queryByText(/Invoice sent to/)).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Invoice to send" })).not.toBeInTheDocument();
  });

  it("an error shows the server message and allows another try", async () => {
    mocks.send
      .mockRejectedValueOnce(new APIError(502, { detail: "Could not send the invoice: timeout" }))
      .mockResolvedValueOnce({ ...sendResult, sent: true });
    const user = await openCard();
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText(/Could not send the invoice: timeout/);
    await waitFor(() => expect(screen.getByRole("button", { name: "Confirm" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Invoice sent to rao@example.com.");
    expect(mocks.send).toHaveBeenCalledTimes(2);
  });
});
