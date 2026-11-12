import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  chat: vi.fn(),
  send: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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
import { PracticeChat } from "@/components/assistant/practice-chat";
import { addDaysToKey, todayDayKey, weekStartOf } from "@/components/dashboard/practice/format";
import {
  clearActionCard,
  sampleCalendar,
  samplePortfolio,
  sampleTurn,
} from "@/components/dashboard/practice/fixtures";
import { AssistantProvider, useAssistant, type AssistantAsk } from "@/providers/assistant-provider";
import type { PracticeOverview, PracticeTurn } from "@/types/practice";

const overview: PracticeOverview = { portfolio: samplePortfolio, calendar: sampleCalendar };

/** Shows what the container asked the Case Bot to do. */
function Probe() {
  const { open, scope, ask } = useAssistant();
  return (
    <output aria-label="Case Bot state">
      {JSON.stringify({ open, scope, question: ask?.question ?? null, day: ask?.selectedDay ?? null, send: ask?.send ?? null })}
    </output>
  );
}

function probeState() {
  return JSON.parse(screen.getByLabelText("Case Bot state").textContent ?? "{}");
}

function renderContainer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AssistantProvider>
        <PracticeContainer />
        <Probe />
      </AssistantProvider>
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

  it("has no inline chat: no message box, chips or Send button on the dashboard", async () => {
    renderContainer();
    await screen.findByText("This week");
    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Suggested questions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).not.toBeInTheDocument();
    expect(screen.queryByRole("log")).not.toBeInTheDocument();
  });

  it("the ask bar opens the Case Bot in practice scope with the question to send", async () => {
    const user = userEvent.setup();
    renderContainer();
    expect(probeState().open).toBe(false);
    await user.type(screen.getByLabelText("Ask about your practice"), "Which cases are listed tomorrow?");
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(probeState()).toMatchObject({
      open: true,
      scope: { kind: "practice" },
      question: "Which cases are listed tomorrow?",
      send: true,
    });
    // The dashboard itself sent nothing: the Case Bot does that when it opens.
    expect(mocks.chat).not.toHaveBeenCalled();
  });

  it("Ask about this day opens the Case Bot with the day question and the day", async () => {
    const user = userEvent.setup();
    renderContainer();
    await user.click(await screen.findByRole("button", { name: "Ask about this day" }));
    const state = probeState();
    expect(state).toMatchObject({ open: true, scope: { kind: "practice" }, day: todayDayKey(), send: true });
    expect(state.question).toMatch(/^What is on .+\?$/);
    expect(mocks.chat).not.toHaveBeenCalled();
  });

  it("shows an overview failure on the calendar and cases only, and keeps the ask bar", async () => {
    mocks.overview.mockRejectedValue(new APIError(500, null));
    renderContainer();
    await screen.findByText("The calendar could not be loaded.", {}, { timeout: 4000 });
    expect(screen.getByText("Your cases could not be loaded.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask about your practice")).toBeInTheDocument();
  });

  it("renders nothing, and no error, when the server has the assistant switched off", async () => {
    mocks.overview.mockRejectedValue(new APIError(404, null));
    renderContainer();
    await waitFor(() => expect(mocks.overview).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByRole("region", { name: "Your practice" })).not.toBeInTheDocument(), {
      timeout: 4000,
    });
    expect(screen.queryByLabelText("Ask about your practice")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

/** The practice conversation itself now lives in the Case Bot: the same
 * behaviours the dashboard chat had, exercised through PracticeChat. */
describe("PracticeChat (Case Bot practice conversation)", () => {
  function renderChat(props: { ask?: AssistantAsk | null; onAskConsumed?: (id: number) => void } = {}) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <PracticeChat conversationId={null} onConversationChange={() => {}} {...props} />
      </QueryClientProvider>,
    );
  }

  const askOf = (over: Partial<AssistantAsk> = {}): AssistantAsk => ({
    id: 1,
    scope: { kind: "practice" },
    question: "What is on Wednesday 11 November?",
    send: true,
    ...over,
  });

  it("sends a handed-in question once as the first message, with its day, then not again", async () => {
    const user = userEvent.setup();
    const onAskConsumed = vi.fn();
    renderChat({ ask: askOf({ selectedDay: "2026-11-11" }), onAskConsumed });
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(1));
    expect(mocks.chat.mock.calls[0][0]).toMatchObject({ query: "What is on Wednesday 11 November?", selected_day: "2026-11-11" });
    expect(mocks.chat.mock.calls[0][0].conversation_id).toBeUndefined();
    expect(onAskConsumed).toHaveBeenCalledWith(1);
    await screen.findByText(sampleTurn.answer);

    await user.click(screen.getByRole("button", { name: "Open deadlines" }));
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(2));
    const second = mocks.chat.mock.calls[1][0];
    expect(second.selected_day).toBeUndefined();
    expect(second.conversation_id).toBe(sampleTurn.conversation_id);
    expect(second.client_request_id).not.toBe(mocks.chat.mock.calls[0][0].client_request_id);
  });

  it("does not send a question that is only meant to be prefilled", async () => {
    renderChat({ ask: askOf({ send: false }) });
    await screen.findByRole("button", { name: "Practice overview" });
    expect(mocks.chat).not.toHaveBeenCalled();
  });

  it("reuses the same client_request_id when a failed send is retried", async () => {
    const user = userEvent.setup();
    mocks.chat.mockRejectedValueOnce(new APIError(500, null)).mockResolvedValueOnce(sampleTurn);
    renderChat();
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    await screen.findByText("That question could not be answered.");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(mocks.chat).toHaveBeenCalledTimes(2));
    expect(mocks.chat.mock.calls[1][0]).toEqual(mocks.chat.mock.calls[0][0]);
    await screen.findByText(sampleTurn.answer);
    // The retry did not add a second copy of the question.
    expect(screen.getAllByText("Give me an overview of my practice.")).toHaveLength(1);
  });

  describe("invoice card", () => {
    async function openCard() {
      const user = userEvent.setup();
      mocks.chat.mockResolvedValue(cardTurn);
      renderChat();
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
