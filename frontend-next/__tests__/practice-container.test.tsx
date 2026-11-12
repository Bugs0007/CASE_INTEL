import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  chat: vi.fn(),
  send: vi.fn(),
}));

vi.mock("@/lib/api/practice", () => ({
  practiceApi: { overview: mocks.overview, chat: mocks.chat },
}));

vi.mock("@/lib/api/billing", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/billing")>();
  return { ...actual, appearanceFeesApi: { ...actual.appearanceFeesApi, send: mocks.send } };
});

import { APIError } from "@/lib/api/client";
import { PracticeContainer } from "@/components/dashboard/practice/practice-container";
import { addDaysToKey, todayDayKey, weekStartOf } from "@/components/dashboard/practice/format";
import {
  clearActionCard,
  sampleCalendar,
  samplePortfolio,
  sampleTurn,
} from "@/components/dashboard/practice/fixtures";
import type { PracticeOverview, PracticeTurn } from "@/types/practice";

const overview: PracticeOverview = { portfolio: samplePortfolio, calendar: sampleCalendar };

function renderContainer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PracticeContainer />
    </QueryClientProvider>,
  );
}

const cardTurn: PracticeTurn = {
  ...sampleTurn,
  intent: "propose_invoice_send",
  action_card: clearActionCard,
};

beforeEach(() => {
  mocks.overview.mockReset().mockResolvedValue(overview);
  mocks.chat.mockReset().mockResolvedValue(sampleTurn);
  mocks.send.mockReset();
});

afterEach(() => vi.restoreAllMocks());

describe("PracticeContainer", () => {
  it("refetches the overview with the new from and to when the week changes", async () => {
    const user = userEvent.setup();
    renderContainer();
    const start = weekStartOf(todayDayKey());
    await waitFor(() =>
      expect(mocks.overview).toHaveBeenCalledWith({ from: start, to: addDaysToKey(start, 6), casePage: 1 }),
    );

    await user.click(screen.getByRole("button", { name: "Next week" }));
    const next = addDaysToKey(start, 7);
    await waitFor(() =>
      expect(mocks.overview).toHaveBeenLastCalledWith({ from: next, to: addDaysToKey(next, 6), casePage: 1 }),
    );
  });

  it("Ask about this day fills the input and sends nothing", async () => {
    const user = userEvent.setup();
    renderContainer();
    await user.click(screen.getByRole("button", { name: "Ask about this day" }));
    expect((screen.getByLabelText("Your question") as HTMLInputElement).value).toMatch(/^What is on .+\?$/);
    expect(mocks.chat).not.toHaveBeenCalled();
  });

  it("sends the asked day with the next message, then not again", async () => {
    const user = userEvent.setup();
    renderContainer();
    await user.click(screen.getByRole("button", { name: "Ask about this day" }));
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(1));
    expect(mocks.chat.mock.calls[0][0]).toMatchObject({ selected_day: todayDayKey() });
    expect(mocks.chat.mock.calls[0][0].conversation_id).toBeUndefined();

    await user.click(screen.getByRole("button", { name: "Open deadlines" }));
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(2));
    const second = mocks.chat.mock.calls[1][0];
    expect(second.selected_day).toBeUndefined();
    expect(second.conversation_id).toBe(sampleTurn.conversation_id);
    expect(second.client_request_id).not.toBe(mocks.chat.mock.calls[0][0].client_request_id);
  });

  it("reuses the same client_request_id when a failed send is retried", async () => {
    const user = userEvent.setup();
    mocks.chat.mockRejectedValueOnce(new APIError(500, null)).mockResolvedValueOnce(sampleTurn);
    renderContainer();
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    await screen.findByText("That question could not be answered.");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(2));
    expect(mocks.chat.mock.calls[1][0]).toEqual(mocks.chat.mock.calls[0][0]);
    await screen.findByText(sampleTurn.answer);
    // The retry did not add a second copy of the question.
    expect(screen.getAllByText("Give me an overview of my practice.")).toHaveLength(1);
  });

  it("keeps the calendar visible when the chat fails", async () => {
    const user = userEvent.setup();
    mocks.chat.mockRejectedValue(new APIError(500, null));
    renderContainer();
    await waitFor(() => expect(mocks.overview).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    await screen.findByText("That question could not be answered.");
    expect(screen.getByRole("region", { name: /^Agenda for/ })).toBeInTheDocument();
    expect(screen.queryByText("The calendar could not be loaded.")).not.toBeInTheDocument();
  });

  it("shows an overview failure on the calendar only, not on the assistant", async () => {
    mocks.overview.mockRejectedValue(new APIError(500, null));
    renderContainer();
    await screen.findByText("The calendar could not be loaded.", {}, { timeout: 4000 });
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
    expect(screen.queryByText("That question could not be answered.")).not.toBeInTheDocument();
  });

  it("renders nothing, and no error, when the server has the assistant switched off", async () => {
    mocks.overview.mockRejectedValue(new APIError(404, null));
    const { container } = renderContainer();
    await waitFor(() => expect(mocks.overview).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement(), { timeout: 4000 });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  describe("invoice card", () => {
    async function openCard() {
      const user = userEvent.setup();
      mocks.chat.mockResolvedValue(cardTurn);
      renderContainer();
      await user.click(screen.getByRole("button", { name: "Practice overview" }));
      await screen.findByRole("region", { name: "Invoice to send" });
      return user;
    }

    const feeResult = { recipient: "rao@example.com", detail: "", missing_env_vars: [], required_env_vars: [], fee: {} };

    async function sendOnce(user: ReturnType<typeof userEvent.setup>) {
      await user.click(screen.getByRole("button", { name: "Send invoice" }));
      await user.click(screen.getByRole("button", { name: "Confirm" }));
    }

    it("confirm calls the existing send once and says it was sent", async () => {
      mocks.send.mockResolvedValue({ ...feeResult, sent: true });
      const user = await openCard();
      await sendOnce(user);
      await screen.findByText("Invoice sent to rao@example.com.");
      expect(mocks.send).toHaveBeenCalledTimes(1);
      expect(mocks.send).toHaveBeenCalledWith(clearActionCard.fee_id);
      expect(screen.queryByRole("region", { name: "Invoice to send" })).not.toBeInTheDocument();
    });

    it("says logged, not sent, when the server only logged it", async () => {
      mocks.send.mockResolvedValue({ ...feeResult, sent: false, detail: "Mail is not set up on the server." });
      const user = await openCard();
      await sendOnce(user);
      const line = await screen.findByText(/Mail is not configured on this server/);
      expect(line).toHaveTextContent("Mail is not configured on this server. The send was recorded but no email went out.");
      expect(screen.queryByText(/Invoice sent to/)).not.toBeInTheDocument();
    });

    it("disables the button while sending, and keeps the card with the error on failure", async () => {
      let reject: (error: unknown) => void = () => {};
      mocks.send.mockReturnValue(new Promise((_, r) => (reject = r)));
      const user = await openCard();
      await sendOnce(user);
      await waitFor(() => expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled());

      reject(new APIError(409, { detail: "Generate the invoice first." }));
      const alert = await screen.findByText("Invoice INV-0007 was not sent. Generate the invoice first.");
      expect(alert).toBeInTheDocument();
      const card = screen.getByRole("region", { name: "Invoice to send" });
      expect(within(card).getByRole("button", { name: "Confirm" })).toBeEnabled();
      expect(mocks.send).toHaveBeenCalledTimes(1);
    });
  });
});
