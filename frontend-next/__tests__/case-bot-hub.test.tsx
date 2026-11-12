import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  pathname: "/dashboard",
  push: vi.fn(),
  replace: vi.fn(),
  portfolio: true,
  list: vi.fn(),
  getMessages: vi.fn(),
  send: vi.fn(),
  practiceChat: vi.fn(),
  casesList: vi.fn(),
  caseGet: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useRouter: () => ({ push: mocks.push, replace: mocks.replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/feature-flags", () => ({
  WALKTHROUGH_ENABLED: false,
  CASE_DRAFTING_ENABLED: false,
  get PORTFOLIO_BOT_ENABLED() {
    return mocks.portfolio;
  },
}));

vi.mock("@/providers/dialog-provider", () => ({
  useDialogs: () => ({
    openSearch: vi.fn(),
    openShortcuts: vi.fn(),
    openNewCaseChooser: vi.fn(),
    openUploadDocument: vi.fn(),
  }),
}));

vi.mock("@/lib/api/chat", () => ({
  chatApi: { send: mocks.send },
  conversationsApi: {
    list: mocks.list,
    getMessages: mocks.getMessages,
    delete: vi.fn(),
    export: vi.fn(),
  },
}));

vi.mock("@/lib/api/practice", () => ({
  practiceApi: { chat: mocks.practiceChat, overview: vi.fn() },
}));

vi.mock("@/lib/api/cases", () => ({
  casesApi: { list: mocks.casesList, get: mocks.caseGet },
}));

import { APIError } from "@/lib/api/client";
import { Header } from "@/components/layout/header";
import { AssistantProvider, useAssistant } from "@/providers/assistant-provider";
import { addDaysToKey, todayDayKey } from "@/components/dashboard/practice/format";

const caseRow = {
  id: 7,
  title: "Rao vs State",
  case_number: "OS 12/2026",
  client_name: "Venkat Rao",
  opposing_party: null,
  next_hearing_date: null,
};
const soonRow = {
  id: 8,
  title: "Mehta vs Union",
  case_number: "WP 99/2026",
  client_name: "Asha Mehta",
  opposing_party: "Union of India",
  next_hearing_date: addDaysToKey(todayDayKey(), 2),
};
const lastRow = {
  id: 9,
  title: "Zed Holdings vs Bank",
  case_number: "CC 5/2025",
  client_name: null,
  opposing_party: null,
  next_hearing_date: null,
};
const allCases = [caseRow, soonRow, lastRow];

const zedChat = {
  id: 61,
  case_id: 9,
  case_title: "Zed Holdings vs Bank",
  scope: "case",
  title: "Loan terms",
  started_at: "2026-11-01T10:00:00Z",
  last_message_at: "2026-11-02T10:00:00Z",
};

function practiceTurn(over: Record<string, unknown>) {
  return {
    conversation_id: 3,
    user_message_id: 1,
    assistant_message_id: 2,
    answer: "",
    intent: "calendar",
    status: "answer",
    sources: [],
    summary: null,
    case_candidates: [],
    action_card: null,
    as_of: "2026-11-11T09:35:00Z",
    ...over,
  };
}

/** A stand-in for the dashboard: asks the Case Bot something from outside it. */
function AskFromOutside() {
  const { openWith } = useAssistant();
  return (
    <button
      type="button"
      onClick={() =>
        openWith({ scope: { kind: "practice" }, question: "What is on Wednesday 11 November?", selectedDay: "2026-11-11" })
      }
    >
      Ask from dashboard
    </button>
  );
}

function tree() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <AssistantProvider>
        <Header />
        <AskFromOutside />
      </AssistantProvider>
    </QueryClientProvider>
  );
}

function renderHeader() {
  const view = render(tree());
  // The same tree again, so a changed mocks.pathname reaches the provider.
  return { ...view, repath: () => view.rerender(tree()) };
}

beforeEach(() => {
  // jsdom has no scrollIntoView; the chat panel scrolls to the newest message.
  Element.prototype.scrollIntoView = vi.fn();
  mocks.pathname = "/dashboard";
  mocks.portfolio = true;
  mocks.push.mockReset();
  mocks.replace.mockReset();
  mocks.list.mockReset().mockResolvedValue([]);
  mocks.getMessages.mockReset().mockResolvedValue([]);
  mocks.send.mockReset();
  mocks.practiceChat.mockReset();
  mocks.casesList.mockReset().mockResolvedValue(allCases);
  mocks.caseGet.mockReset().mockResolvedValue({ ...caseRow });
});

describe("Case Bot header button and popover", () => {
  it("opens the popover from the header and closes on Escape with focus back on the button", async () => {
    const user = userEvent.setup();
    renderHeader();
    const button = screen.getByRole("button", { name: "Case Bot" });
    expect(screen.queryByRole("dialog", { name: "Case Bot" })).not.toBeInTheDocument();

    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Case Bot" });
    expect(within(dialog).getByRole("button", { name: /Scope: Your practice/ })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Case Bot" })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("defaults to the case on a case page and loads that case's chats", async () => {
    mocks.pathname = "/cases/7";
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const dialog = screen.getByRole("dialog", { name: "Case Bot" });
    expect(await within(dialog).findByRole("button", { name: /Scope: Rao vs State/ })).toBeInTheDocument();
    await waitFor(() => expect(mocks.list).toHaveBeenCalledWith(7));
  });

  it("offers Your practice in the chooser only when the practice flag is on", async () => {
    const user = userEvent.setup();
    mocks.portfolio = false;
    const { unmount } = renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    // No scope yet: the body asks the user to pick, and the chooser lists cases only.
    expect(screen.getByText("Pick what you want to ask about.")).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Your practice" })).not.toBeInTheDocument();
    expect(await screen.findByRole("option", { name: /Rao vs State/ })).toBeInTheDocument();
    unmount();

    mocks.portfolio = true;
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(screen.getByRole("button", { name: /Change scope/ }));
    const options = await screen.findAllByRole("option");
    expect(options[0]).toHaveAccessibleName("Your practice");
  });

  it("shows the scope as a chip with its case number and a Change action", async () => {
    mocks.pathname = "/cases/7";
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const chip = within(screen.getByRole("dialog", { name: "Case Bot" })).getByRole("group", { name: "Chat scope" });
    expect(await within(chip).findByText("OS 12/2026")).toBeInTheDocument();
    expect(within(chip).getByText("Rao vs State")).toBeInTheDocument();
    expect(within(chip).getByRole("button", { name: /Change scope/ })).toHaveTextContent("Change");
  });

  it("picks a case from the searchable chooser, matching title, case number and party", async () => {
    mocks.portfolio = false;
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const search = await screen.findByLabelText("Search your cases");
    await user.type(search, "zzz");
    expect(screen.getByText("No case matches that search.")).toBeInTheDocument();

    // By case number.
    await user.clear(search);
    await user.type(search, "wp 99");
    expect((await screen.findAllByRole("option", { name: /Mehta vs Union/ })).length).toBeGreaterThan(0);
    expect(screen.queryByRole("option", { name: /Rao vs State/ })).not.toBeInTheDocument();

    // By party name.
    await user.clear(search);
    await user.type(search, "venkat");
    await user.click(await screen.findByRole("option", { name: /Rao vs State/ }));
    expect(await screen.findByRole("button", { name: /Scope: Rao vs State/ })).toBeInTheDocument();
  });

  it("orders the chooser: this page's case, recent, hearing soon, then all cases A to Z", async () => {
    mocks.pathname = "/cases/7";
    mocks.list.mockResolvedValue([zedChat]);
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(await screen.findByRole("button", { name: /Change scope/ }));
    const listbox = await screen.findByRole("listbox", { name: "Choose what to ask about" });
    await waitFor(() =>
      expect(within(listbox).getAllByRole("group").map((group) => group.getAttribute("aria-label"))).toEqual([
        "This page's case",
        "Recent",
        "Hearing soon",
        "All cases",
      ]),
    );
    const group = (name: string) => within(within(listbox).getByRole("group", { name }));
    expect(group("This page's case").getByRole("option")).toHaveTextContent("Rao vs State");
    expect(group("Recent").getByRole("option")).toHaveTextContent("Zed Holdings vs Bank");
    expect(group("Hearing soon").getByRole("option")).toHaveTextContent("Mehta vs Union");
    expect(group("All cases").getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Mehta vs UnionWP 99/2026",
      "Rao vs StateOS 12/2026",
      "Zed Holdings vs BankCC 5/2025",
    ]);
    // The case number sits under the title.
    expect(group("Recent").getByText("CC 5/2025")).toBeInTheDocument();
  });

  it("moves through the chooser with the arrow keys and picks with Enter", async () => {
    mocks.portfolio = false;
    mocks.list.mockResolvedValue([zedChat]);
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const search = await screen.findByLabelText("Search your cases");
    await waitFor(() =>
      expect(screen.getAllByRole("option", { selected: true })[0]).toHaveTextContent("Zed Holdings vs Bank"),
    );
    await user.type(search, "{ArrowDown}");
    expect(screen.getAllByRole("option", { selected: true })[0]).toHaveTextContent("Mehta vs Union");
    await user.type(search, "{Enter}");
    expect(await screen.findByRole("button", { name: /Scope: Mehta vs Union/ })).toBeInTheDocument();
  });

  it("starts on this page's case when the remembered chat was another case, and offers a way back", async () => {
    mocks.portfolio = false;
    const user = userEvent.setup();
    const { repath } = renderHeader();
    // On the dashboard, pick Zed Holdings.
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(await screen.findByRole("option", { name: /Zed Holdings/ }));
    expect(await screen.findByRole("button", { name: /Scope: Zed Holdings vs Bank/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");

    // Navigate to Rao's page: the popover must not silently keep Zed.
    mocks.pathname = "/cases/7";
    repath();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const dialog = screen.getByRole("dialog", { name: "Case Bot" });
    expect(await within(dialog).findByRole("button", { name: /Scope: Rao vs State/ })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Back to Zed Holdings vs Bank" }));
    expect(await within(dialog).findByRole("button", { name: /Scope: Zed Holdings vs Bank/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: /^Back to/ })).not.toBeInTheDocument();
  });

  it("does not offer a way back when the popover opens on the case it already had", async () => {
    mocks.pathname = "/cases/7";
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await screen.findByRole("button", { name: /Scope: Rao vs State/ });
    expect(screen.queryByRole("button", { name: /^Back to/ })).not.toBeInTheDocument();
  });

  it("opens in practice scope and sends a question handed in from outside, as a new chat", async () => {
    mocks.practiceChat.mockResolvedValue(practiceTurn({ conversation_id: 3, answer: "One hearing on Wednesday." }));
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Ask from dashboard" }));
    const dialog = await screen.findByRole("dialog", { name: "Case Bot" });
    expect(within(dialog).getByRole("button", { name: /Scope: Your practice/ })).toBeInTheDocument();
    await within(dialog).findByText("One hearing on Wednesday.");
    expect(mocks.practiceChat).toHaveBeenCalledTimes(1);
    expect(mocks.practiceChat.mock.calls[0][0]).toMatchObject({
      query: "What is on Wednesday 11 November?",
      selected_day: "2026-11-11",
    });
    expect(mocks.practiceChat.mock.calls[0][0].conversation_id).toBeUndefined();

    // Asking again starts another new chat, not a continuation of the first.
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Ask from dashboard" }));
    await waitFor(() => expect(mocks.practiceChat).toHaveBeenCalledTimes(2));
    expect(mocks.practiceChat.mock.calls[1][0].conversation_id).toBeUndefined();
  });

  it("Ask in this case opens a case chat with the question typed but not sent", async () => {
    mocks.practiceChat.mockResolvedValue(
      practiceTurn({
        conversation_id: 4,
        answer: "Which case do you mean?",
        status: "needs_clarification",
        case_candidates: [{ id: 7, title: "Rao vs State", case_number: "OS 12/2026", court: null }],
      }),
    );
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(await screen.findByRole("button", { name: "Practice overview" }));
    await user.click(await screen.findByRole("button", { name: "Ask in this case: Rao vs State" }));

    expect(await screen.findByRole("button", { name: /Scope: Rao vs State/ })).toBeInTheDocument();
    const box = (await screen.findByPlaceholderText(/Ask a question to begin/)) as HTMLTextAreaElement;
    await waitFor(() => expect(box.value).toBe("Give me an overview of my practice."));
    expect(mocks.send).not.toHaveBeenCalled();
  });

  it("says the practice assistant is not switched on when the server answers 404, and offers a case", async () => {
    mocks.practiceChat.mockRejectedValue(new APIError(404, { detail: "Not found." }));
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    expect(await screen.findByText("The practice assistant is not switched on yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask about a case instead" }));
    expect(await screen.findByLabelText("Search your cases")).toBeInTheDocument();
  });

  it("Expand opens the full page on the current chat", async () => {
    mocks.pathname = "/cases/7";
    mocks.list.mockResolvedValue([
      { id: 41, case_id: 7, case_title: "Rao vs State", scope: "case", title: "Hearing dates", started_at: "2026-11-01T10:00:00Z", last_message_at: "2026-11-01T10:05:00Z" },
    ]);
    mocks.getMessages.mockResolvedValue([]);
    mocks.send.mockResolvedValue({
      answer: "Next hearing is on 3 December.",
      confidence: 0.9,
      query_type: "x",
      requires_clarification: false,
      clarification_question: null,
      message_id: 90,
      conversation_id: 41,
      citations: [],
    });
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const dialog = screen.getByRole("dialog", { name: "Case Bot" });
    // The panel starts a new chat; sending creates conversation 41, which the
    // popover remembers.
    await user.type(await within(dialog).findByPlaceholderText(/Ask a question to begin/), "When is the hearing?");
    await user.click(within(dialog).getAllByRole("button").find((b) => b.querySelector("svg.lucide-send"))!);
    await within(dialog).findByText("Next hearing is on 3 December.");

    await user.click(screen.getByRole("button", { name: "Expand" }));
    expect(mocks.push).toHaveBeenCalledWith("/assistant?c=41");
    expect(screen.queryByRole("dialog", { name: "Case Bot" })).not.toBeInTheDocument();
  });

  it("remembers the open chat when the popover is closed and opened again", async () => {
    mocks.pathname = "/cases/7";
    mocks.list.mockResolvedValue([
      { id: 41, case_id: 7, case_title: "Rao vs State", scope: "case", title: "Hearing dates", started_at: "2026-11-01T10:00:00Z", last_message_at: null },
    ]);
    mocks.send.mockResolvedValue({
      answer: "Done.",
      confidence: 0.9,
      query_type: "x",
      requires_clarification: false,
      clarification_question: null,
      message_id: 91,
      conversation_id: 41,
      citations: [],
    });
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    const dialog = screen.getByRole("dialog", { name: "Case Bot" });
    await user.type(await within(dialog).findByPlaceholderText(/Ask a question to begin/), "Hi");
    await user.click(within(dialog).getAllByRole("button").find((b) => b.querySelector("svg.lucide-send"))!);
    await within(dialog).findByText("Done.");

    await user.click(screen.getByRole("button", { name: "Close Case Bot" }));
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await waitFor(() => expect(mocks.getMessages).toHaveBeenCalledWith(41));
  });
});
