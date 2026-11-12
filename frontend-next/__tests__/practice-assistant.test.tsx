import { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  PracticeAssistantPanel,
  type PracticeAssistantPanelProps,
  type PracticeMessage,
} from "@/components/dashboard/practice/practice-assistant-panel";
import { PracticeInvoiceActionCard } from "@/components/dashboard/practice/practice-invoice-action-card";
import { PracticeSection } from "@/components/dashboard/practice/practice-section";
import {
  FIXTURE_DAY,
  FIXTURE_WEEK_START,
  blockedActionCard,
  clearActionCard,
  sampleCalendar,
  samplePortfolio,
  sampleTurn,
} from "@/components/dashboard/practice/fixtures";
import type { PracticeTurn } from "@/types/practice";

function panelProps(overrides: Partial<PracticeAssistantPanelProps> = {}): PracticeAssistantPanelProps {
  return {
    messages: [],
    pending: false,
    error: false,
    onRetry: vi.fn(),
    draft: "",
    onDraftChange: vi.fn(),
    onSend: vi.fn(),
    onChooseCase: vi.fn(),
    onConfirmInvoice: vi.fn(),
    onDismissAction: vi.fn(),
    ...overrides,
  };
}

const answer = (turn: Partial<PracticeTurn> = {}): PracticeMessage => ({
  role: "assistant",
  id: "a1",
  turn: { ...sampleTurn, ...turn },
});

describe("PracticeAssistantPanel", () => {
  it("has the title and the four suggested questions, which send on click", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<PracticeAssistantPanel {...panelProps({ onSend })} />);
    expect(screen.getByText("Ask about your practice")).toBeInTheDocument();
    const chips = within(screen.getByRole("list", { name: "Suggested questions" })).getAllByRole("button");
    expect(chips.map((chip) => chip.textContent)).toEqual([
      "Practice overview",
      "This week's calendar",
      "Open deadlines",
      "Cases with no next date",
    ]);
    await user.click(chips[2]);
    expect(onSend).toHaveBeenCalledWith("What deadlines are open?");
  });

  it("shows an externally set draft and sends only on Send", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    const onDraftChange = vi.fn();
    render(<PracticeAssistantPanel {...panelProps({ draft: "What is on Thursday 12 November?", onSend, onDraftChange })} />);
    expect(screen.getByLabelText("Your question")).toHaveValue("What is on Thursday 12 November?");
    expect(onSend).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("What is on Thursday 12 November?");
    expect(onDraftChange).toHaveBeenCalledWith("");
  });

  it("renders source chips with hrefs from the route map, never from text", () => {
    render(
      <PracticeAssistantPanel
        {...panelProps({ messages: [answer({ answer: "See https://evil.example/steal for details." })] })}
      />,
    );
    const sources = within(screen.getByRole("list", { name: "Sources" }));
    expect(sources.getByRole("link", { name: "Rao vs State" })).toHaveAttribute("href", "/cases/7");
    expect(sources.getByRole("link", { name: "Hearing on 11 Nov" })).toHaveAttribute("href", "/cases/7");
    expect(sources.getByRole("link", { name: "INV-0007" })).toHaveAttribute("href", "/billing");
    expect(screen.queryByRole("link", { name: /evil/ })).not.toBeInTheDocument();
  });

  it("treats partial and needs_clarification differently and shows the as-of line", () => {
    const { rerender } = render(<PracticeAssistantPanel {...panelProps({ messages: [answer({ status: "partial" })] })} />);
    expect(screen.getByText(/could not be checked, so it may be incomplete/)).toBeInTheDocument();
    expect(screen.getByText("As of 3:05 pm")).toBeInTheDocument();
    rerender(<PracticeAssistantPanel {...panelProps({ messages: [answer({ status: "needs_clarification" })] })} />);
    expect(screen.getByText(/need a little more detail/)).toBeInTheDocument();
  });

  it("lets the advocate choose a verified case", async () => {
    const user = userEvent.setup();
    const onChooseCase = vi.fn();
    render(
      <PracticeAssistantPanel
        {...panelProps({
          onChooseCase,
          messages: [
            answer({
              status: "needs_clarification",
              case_candidates: [
                { id: 7, title: "Rao vs State", case_number: "WP/1/2026", court: "Telangana High Court" },
                { id: 8, title: "Rao vs Rao", case_number: null, court: null },
              ],
            }),
          ],
        })}
      />,
    );
    const choose = within(screen.getByRole("group", { name: "Choose a case" }));
    expect(choose.getByText("WP/1/2026 · Telangana High Court")).toBeInTheDocument();
    await user.click(choose.getByRole("button", { name: /Rao vs Rao/ }));
    expect(onChooseCase).toHaveBeenCalledWith(8);
  });

  it("has pending and error-with-retry states, announces answers politely", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(<PracticeAssistantPanel {...panelProps({ pending: true })} />);
    expect(screen.getByRole("status")).toHaveTextContent("Looking through your records.");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();

    rerender(<PracticeAssistantPanel {...panelProps({ error: true, onRetry, messages: [answer()] })} />);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  });

  it("renders the invoice card in a turn that carries one", async () => {
    const user = userEvent.setup();
    const onConfirmInvoice = vi.fn();
    const onDismissAction = vi.fn();
    render(
      <PracticeAssistantPanel
        {...panelProps({
          onConfirmInvoice,
          onDismissAction,
          messages: [answer({ intent: "propose_invoice_send", action_card: clearActionCard })],
        })}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    expect(onConfirmInvoice).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirmInvoice).toHaveBeenCalledWith(31);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismissAction).toHaveBeenCalledWith("a1");
  });
});

describe("PracticeInvoiceActionCard", () => {
  it("shows the invoice, amount, recipient and case", () => {
    render(<PracticeInvoiceActionCard card={clearActionCard} caseTitle="Rao vs State" onConfirm={() => {}} onDismiss={() => {}} />);
    expect(screen.getByText("INV-0007")).toBeInTheDocument();
    expect(screen.getByText("15000.00")).toBeInTheDocument();
    expect(screen.getByText("A. Rao, rao@example.com")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Rao vs State" })).toHaveAttribute("href", "/cases/7");
  });

  it("has no send button at all while blocked, and lists the blockers", () => {
    render(<PracticeInvoiceActionCard card={blockedActionCard} onConfirm={() => {}} onDismiss={() => {}} />);
    expect(screen.queryByRole("button", { name: "Send invoice" })).not.toBeInTheDocument();
    expect(screen.getByText("The client has no email address on file.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  });

  it("calls onConfirm with the fee id when clear", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(<PracticeInvoiceActionCard card={clearActionCard} onConfirm={onConfirm} onDismiss={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Send invoice" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    expect(onConfirm).toHaveBeenCalledWith(31);
  });
});

describe("PracticeSection", () => {
  function Section({ assistantError }: { assistantError: boolean }) {
    const [day, setDay] = useState(FIXTURE_DAY);
    return (
      <PracticeSection
        calendar={{
          calendar: sampleCalendar,
          loading: false,
          error: false,
          onRetry: () => {},
          weekStart: FIXTURE_WEEK_START,
          onWeekChange: () => {},
          selectedDay: day,
          onSelectDay: setDay,
          onAskAboutDay: () => {},
        }}
        portfolio={{ snapshot: samplePortfolio, loading: false, error: false, onRetry: () => {}, onPageChange: () => {} }}
        assistant={panelProps({ error: assistantError })}
      />
    );
  }

  it("keeps the calendar and summary when the assistant fails", () => {
    render(<Section assistantError />);
    expect(screen.getByRole("alert")).toHaveTextContent("That question could not be answered.");
    expect(screen.getByText("This week")).toBeInTheDocument();
    expect(screen.getByText("Mediation sitting")).toBeInTheDocument();
    expect(screen.getByText("Your cases")).toBeInTheDocument();
    expect(screen.getByText("Ask about your practice")).toBeInTheDocument();
  });
});
