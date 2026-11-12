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
import { AssistantProvider } from "@/providers/assistant-provider";

const caseRow = { id: 7, title: "Rao vs State", case_number: "OS 12/2026" };

function renderHeader() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AssistantProvider>
        <Header />
      </AssistantProvider>
    </QueryClientProvider>,
  );
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
  mocks.casesList.mockReset().mockResolvedValue([caseRow]);
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

  it("offers Your practice in the scope picker only when the practice flag is on", async () => {
    const user = userEvent.setup();
    mocks.portfolio = false;
    const { unmount } = renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    // No scope yet: the body asks the user to pick, with a case option only.
    expect(screen.getByText("Pick what you want to ask about.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Your practice" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "A case..." })).toBeInTheDocument();
    unmount();

    mocks.portfolio = true;
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(screen.getByRole("button", { name: /Change scope/ }));
    expect(screen.getByRole("button", { name: "Your practice" })).toBeInTheDocument();
  });

  it("picks a case from the searchable chooser", async () => {
    mocks.portfolio = false;
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(screen.getByRole("button", { name: "A case..." }));
    await user.type(screen.getByLabelText("Search your cases"), "zzz");
    expect(screen.getByText("No case matches that search.")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Search your cases"));
    await user.type(screen.getByLabelText("Search your cases"), "rao");
    await user.click(await screen.findByRole("button", { name: /Rao vs State/ }));
    expect(await screen.findByRole("button", { name: /Scope: Rao vs State/ })).toBeInTheDocument();
  });

  it("says the practice assistant is not switched on when the server answers 404, and offers a case", async () => {
    mocks.practiceChat.mockRejectedValue(new APIError(404, { detail: "Not found." }));
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    await user.click(screen.getByRole("button", { name: "Practice overview" }));
    expect(await screen.findByText("The practice assistant is not switched on yet.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask about a case instead" }));
    expect(screen.getByRole("button", { name: "A case..." })).toBeInTheDocument();
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
