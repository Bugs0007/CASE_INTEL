import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  search: "",
  push: vi.fn(),
  replace: vi.fn(),
  list: vi.fn(),
  getMessages: vi.fn(),
  send: vi.fn(),
  practiceChat: vi.fn(),
  casesList: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/assistant",
  useRouter: () => ({ push: mocks.push, replace: mocks.replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/lib/feature-flags", () => ({
  WALKTHROUGH_ENABLED: false,
  CASE_DRAFTING_ENABLED: false,
  PORTFOLIO_BOT_ENABLED: true,
}));

vi.mock("@/lib/api/chat", () => ({
  chatApi: { send: mocks.send },
  conversationsApi: { list: mocks.list, getMessages: mocks.getMessages, delete: vi.fn(), export: vi.fn() },
}));

vi.mock("@/lib/api/practice", () => ({
  practiceApi: { chat: mocks.practiceChat, overview: vi.fn() },
}));

vi.mock("@/lib/api/cases", () => ({
  casesApi: { list: mocks.casesList, get: vi.fn().mockResolvedValue({ id: 10, title: "Alpha vs Beta", case_number: "C 1/2026" }) },
}));

const sendFee = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/billing", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/billing")>();
  return { ...actual, appearanceFeesApi: { ...actual.appearanceFeesApi, send: sendFee } };
});

import { AssistantPage } from "@/components/assistant/assistant-page";
import { groupConversations, recentChats } from "@/lib/assistant";
import { AssistantProvider } from "@/providers/assistant-provider";
import { rebuildPracticeMessages } from "@/lib/practice-history";
import type { Conversation, Message } from "@/types/chat";

function chat(over: Partial<Conversation> & { id: number }): Conversation {
  return {
    case_id: null,
    case_title: null,
    scope: "case",
    title: `Chat ${over.id}`,
    started_at: "2026-11-01T10:00:00Z",
    last_message_at: "2026-11-01T10:00:00Z",
    preview: "",
    message_count: 2,
    ...over,
  };
}

const caseChats: Conversation[] = [
  chat({ id: 1, case_id: 10, case_title: "Alpha vs Beta", title: "Limitation", last_message_at: "2026-11-02T10:00:00Z" }),
  chat({ id: 2, case_id: 20, case_title: "Gamma vs Delta", title: "Orders", last_message_at: "2026-11-05T10:00:00Z" }),
  chat({ id: 3, case_id: 10, case_title: "Alpha vs Beta", title: "Evidence", last_message_at: "2026-11-04T10:00:00Z" }),
];
const practiceChats: Conversation[] = [
  chat({ id: 8, scope: "practice", title: "Week ahead", last_message_at: "2026-11-03T10:00:00Z" }),
  chat({ id: 9, scope: "practice", title: "Open deadlines", last_message_at: "2026-11-06T10:00:00Z" }),
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AssistantProvider>
        <AssistantPage />
      </AssistantProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  // jsdom has no scrollIntoView; the chat panel scrolls to the newest message.
  Element.prototype.scrollIntoView = vi.fn();
  mocks.search = "";
  mocks.push.mockReset();
  mocks.replace.mockReset();
  mocks.list.mockReset().mockImplementation((_caseId?: number, scope?: string) =>
    Promise.resolve(scope === "practice" ? practiceChats : [...caseChats]),
  );
  mocks.getMessages.mockReset().mockResolvedValue([]);
  mocks.practiceChat.mockReset();
  mocks.casesList.mockReset().mockResolvedValue([
    { id: 10, title: "Alpha vs Beta", case_number: "OS 12/2026" },
    { id: 20, title: "Gamma vs Delta", case_number: "WP 7/2025" },
  ]);
  sendFee.mockReset();
});

describe("groupConversations", () => {
  it("orders case groups by their latest chat and each group's chats newest first", () => {
    const groups = groupConversations(caseChats, "");
    expect(groups.cases.map((g) => g.title)).toEqual(["Gamma vs Delta", "Alpha vs Beta"]);
    expect(groups.cases[1].chats.map((c) => c.title)).toEqual(["Evidence", "Limitation"]);
  });

  it("keeps all of a case's chats when the case title matches, else only matching chats", () => {
    expect(groupConversations(caseChats, "alpha").cases[0].chats).toHaveLength(2);
    const byChat = groupConversations(caseChats, "evidence");
    expect(byChat.cases).toHaveLength(1);
    expect(byChat.cases[0].chats.map((c) => c.title)).toEqual(["Evidence"]);
  });

  it("matches a case by its number and keeps all that case's chats", () => {
    const groups = groupConversations(caseChats, "wp 7", { 10: "OS 12/2026", 20: "WP 7/2025" });
    expect(groups.cases.map((g) => g.title)).toEqual(["Gamma vs Delta"]);
    expect(groups.cases[0].caseNumber).toBe("WP 7/2025");
  });

  it("recentChats takes the eight newest across scopes, never older document chats", () => {
    const rows = Array.from({ length: 12 }, (_, index) =>
      chat({
        id: 100 + index,
        case_id: index % 2 === 0 ? 10 : null,
        case_title: index % 2 === 0 ? "Alpha vs Beta" : null,
        scope: index % 2 === 0 ? "case" : "practice",
        last_message_at: `2026-11-${String(index + 1).padStart(2, "0")}T10:00:00Z`,
      }),
    );
    rows.push(chat({ id: 500, scope: "legacy_documents", last_message_at: "2026-12-01T10:00:00Z" }));
    const recent = recentChats(rows);
    expect(recent).toHaveLength(8);
    expect(recent.map((row) => row.id)).toEqual([111, 110, 109, 108, 107, 106, 105, 104]);
  });

  it("separates practice and older document chats", () => {
    const rows = [...practiceChats, chat({ id: 30, scope: "legacy_documents", title: "Old one" })];
    const groups = groupConversations(rows, "");
    expect(groups.practice.map((c) => c.id)).toEqual([9, 8]);
    expect(groups.legacy.map((c) => c.id)).toEqual([30]);
    expect(groups.cases).toEqual([]);
  });
});

/** Many chats across many cases, like a busy practice. */
function busyRows(): Conversation[] {
  const rows: Conversation[] = [];
  for (let c = 1; c <= 12; c += 1) {
    rows.push(
      chat({
        id: 1000 + c,
        case_id: c,
        case_title: `Matter ${String(c).padStart(2, "0")} vs State`,
        title: `Chat for matter ${c}`,
        last_message_at: `2026-10-${String(c).padStart(2, "0")}T10:00:00Z`,
      }),
    );
  }
  for (let k = 1; k <= 7; k += 1) {
    rows.push(
      chat({
        id: 2000 + k,
        scope: "practice",
        title: `Practice question ${k}`,
        last_message_at: `2026-10-${String(12 + k).padStart(2, "0")}T10:00:00Z`,
      }),
    );
  }
  return rows;
}

function useBusyRows() {
  const rows = busyRows();
  mocks.list.mockImplementation((_caseId?: number, scope?: string) =>
    Promise.resolve(scope === "practice" ? rows.filter((r) => r.scope === "practice") : rows.filter((r) => r.scope !== "practice")),
  );
  mocks.casesList.mockResolvedValue(
    Array.from({ length: 12 }, (_, index) => ({
      id: index + 1,
      title: `Matter ${String(index + 1).padStart(2, "0")} vs State`,
      case_number: `CC ${index + 1}/2026`,
    })),
  );
}

describe("Case Bot page sidebar", () => {
  it("keeps case groups collapsed, newest group first, with the count and the latest time", async () => {
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    const groupItems = within(casesSection).getAllByRole("listitem", { name: /vs/ });
    expect(groupItems.map((item) => item.getAttribute("aria-label"))).toEqual(["Gamma vs Delta", "Alpha vs Beta"]);
    const alpha = within(casesSection).getByRole("button", { name: /Alpha vs Beta/ });
    expect(alpha).toHaveAttribute("aria-expanded", "false");
    expect(alpha).toHaveTextContent("2 chats");
    expect(within(casesSection).queryByRole("button", { name: /^Evidence/ })).not.toBeInTheDocument();
    expect(within(casesSection).getByRole("link", { name: "Open case Alpha vs Beta" })).toHaveAttribute("href", "/cases/10");

    const practice = screen.getByRole("region", { name: "Your practice" });
    const names = within(practice).getAllByRole("button", { name: /^(Week ahead|Open deadlines)/ });
    expect(names[0]).toHaveTextContent("Open deadlines");
  });

  it("opens a group by hand, and Collapse all closes every group", async () => {
    const user = userEvent.setup();
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    expect(within(casesSection).queryByRole("button", { name: "Collapse all" })).not.toBeInTheDocument();
    await user.click(within(casesSection).getByRole("button", { name: /Alpha vs Beta/ }));
    expect(within(casesSection).getByRole("button", { name: /^Evidence/ })).toBeInTheDocument();
    expect(within(casesSection).getByRole("button", { name: /Alpha vs Beta/ })).toHaveAttribute("aria-expanded", "true");

    await user.click(within(casesSection).getByRole("button", { name: "Collapse all" }));
    expect(within(casesSection).queryByRole("button", { name: /^Evidence/ })).not.toBeInTheDocument();
    expect(within(casesSection).queryByRole("button", { name: "Collapse all" })).not.toBeInTheDocument();
  });

  it("expands the group of the selected chat and no other", async () => {
    mocks.search = "c=3";
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    expect(within(casesSection).getByRole("button", { name: /Alpha vs Beta/ })).toHaveAttribute("aria-expanded", "true");
    expect(within(casesSection).getByRole("button", { name: /^Evidence/ })).toHaveAttribute("aria-current", "true");
    expect(within(casesSection).getByRole("button", { name: /Gamma vs Delta/ })).toHaveAttribute("aria-expanded", "false");
  });

  it("Recent shows the 8 newest chats across scopes, each with its case or Practice", async () => {
    useBusyRows();
    renderPage();
    const recent = await screen.findByRole("region", { name: "Recent" });
    const rows = within(recent).getAllByRole("button");
    expect(rows).toHaveLength(8);
    // Newest first: the seven practice chats (13 to 19 Oct), then matter 12.
    expect(rows[0]).toHaveTextContent("Practice question 7");
    expect(rows[0]).toHaveTextContent("Practice");
    expect(rows[6]).toHaveTextContent("Practice question 1");
    expect(rows[7]).toHaveTextContent("Chat for matter 12");
    expect(rows[7]).toHaveTextContent("Matter 12 vs State");
  });

  it("shows five practice chats with Show all, and every case group collapsed", async () => {
    useBusyRows();
    const user = userEvent.setup();
    renderPage();
    const practice = await screen.findByRole("region", { name: "Your practice" });
    expect(within(practice).getAllByRole("button", { name: /^Practice question/ })).toHaveLength(5);
    await user.click(within(practice).getByRole("button", { name: "Show all (7)" }));
    expect(within(practice).getAllByRole("button", { name: /^Practice question/ })).toHaveLength(7);

    const casesSection = screen.getByRole("region", { name: "Cases" });
    const headers = within(casesSection).getAllByRole("button", { name: /vs State/ });
    expect(headers).toHaveLength(12);
    headers.forEach((header) => expect(header).toHaveAttribute("aria-expanded", "false"));
    // The group header carries the full title for a truncated one.
    expect(headers[0]).toHaveAttribute("title", "Matter 12 vs State (CC 12/2026)");
  });

  it("filtering expands the matching groups, hides Recent, and matches a case number", async () => {
    useBusyRows();
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Recent" });
    await user.type(screen.getByLabelText("Filter chats"), "cc 5/");
    await waitFor(() => expect(screen.queryByRole("region", { name: "Recent" })).not.toBeInTheDocument());
    const casesSection = screen.getByRole("region", { name: "Cases" });
    const groups = within(casesSection).getAllByRole("button", { name: /vs State/ });
    expect(groups).toHaveLength(1);
    expect(groups[0]).toHaveTextContent("Matter 05 vs State");
    expect(groups[0]).toHaveAttribute("aria-expanded", "true");
    expect(within(casesSection).getByRole("button", { name: /^Chat for matter 5/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your practice" })).not.toBeInTheDocument();
  });

  it("narrows the rows with the filter", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Cases" });
    await user.type(screen.getByLabelText("Filter chats"), "gamma");
    const casesSection = screen.getByRole("region", { name: "Cases" });
    expect(within(casesSection).queryByRole("link", { name: "Open case Alpha vs Beta" })).not.toBeInTheDocument();
    expect(within(casesSection).getByRole("link", { name: "Open case Gamma vs Delta" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your practice" })).not.toBeInTheDocument();
  });

  it("selecting a row puts the chat in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    await user.click(within(casesSection).getByRole("button", { name: /Alpha vs Beta/ }));
    await user.click(within(casesSection).getByRole("button", { name: /^Evidence/ }));
    expect(mocks.push).toHaveBeenCalledWith("/assistant?c=3");
  });

  it("opens the chooser from New chat with Your practice first, then the case sections", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Cases" });
    await user.click(screen.getByRole("button", { name: "New chat" }));
    const sidebar = screen.getByRole("complementary", { name: "Case Bot chats" });
    const options = await within(sidebar).findAllByRole("option");
    expect(options[0]).toHaveAccessibleName("Your practice");
    expect(within(sidebar).getByRole("group", { name: "All cases" })).toBeInTheDocument();
    await user.click(options[0]);
    expect(mocks.push).toHaveBeenCalledWith("/assistant?scope=practice");
  });

  it("starts a chat for a case picked in the chooser", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Cases" });
    await user.click(screen.getByRole("button", { name: "New chat" }));
    const sidebar = screen.getByRole("complementary", { name: "Case Bot chats" });
    await user.type(await within(sidebar).findByLabelText("Search your cases"), "wp 7");
    await user.keyboard("{ArrowDown}{Enter}");
    expect(mocks.push).toHaveBeenCalledWith("/assistant?case=20");
  });

  it("confirms in the page before deleting a chat", async () => {
    mocks.search = "c=3";
    const user = userEvent.setup();
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    await user.click(within(casesSection).getByRole("button", { name: "Delete chat Evidence" }));
    expect(screen.getByText("Delete this chat? This cannot be undone.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Delete this chat? This cannot be undone.")).not.toBeInTheDocument();
  });
});

describe("Case Bot page scope chip", () => {
  it("shows what a new chat is about next to the input, with Change", async () => {
    mocks.search = "scope=practice";
    renderPage();
    const chip = await screen.findByRole("group", { name: "Chat scope" });
    expect(within(chip).getByText("Your practice")).toBeInTheDocument();
    expect(within(chip).getByRole("button", { name: /Change scope/ })).toBeInTheDocument();
  });

  it("shows a case's title and number", async () => {
    mocks.search = "case=10";
    renderPage();
    const chip = await screen.findByRole("group", { name: "Chat scope" });
    expect(await within(chip).findByText("Alpha vs Beta")).toBeInTheDocument();
    expect(await within(chip).findByText("C 1/2026")).toBeInTheDocument();
  });
});

const invoiceCard = {
  kind: "send_invoice" as const,
  fee_id: 55,
  case_id: 10,
  invoice_number: "INV-9",
  amount: "5000.00",
  recipient_name: "A Client",
  recipient_email: "client@example.com",
  blockers: [],
};

const pastPractice: Message[] = [
  {
    id: 100,
    role: "user",
    content: "Send the invoice for Alpha",
    created_at: "2026-11-06T10:00:00Z",
    references: [
      {
        kind: "practice_request",
        v: 1,
        client_request_id: "abc",
        turn: {
          intent: "propose_invoice_send",
          status: "answer",
          summary: null,
          case_candidates: [],
          action_card: invoiceCard,
          as_of: "2026-11-06T10:00:00Z",
        },
      },
    ],
  },
  {
    id: 101,
    role: "assistant",
    content: "I can send invoice INV-9 to the client.",
    created_at: "2026-11-06T10:00:05Z",
    references: [{ kind: "case", id: 10, case_id: 10, label: "Alpha vs Beta", recorded_at: null }],
  },
];

describe("past practice conversations", () => {
  it("rebuildPracticeMessages takes answer, sources and card from the stored messages", () => {
    const rebuilt = rebuildPracticeMessages(pastPractice, 9);
    expect(rebuilt).toHaveLength(2);
    const turn = rebuilt[1].role === "assistant" ? rebuilt[1].turn : null;
    expect(turn?.answer).toBe("I can send invoice INV-9 to the client.");
    expect(turn?.sources.map((s) => s.label)).toEqual(["Alpha vs Beta"]);
    expect(turn?.action_card?.fee_id).toBe(55);
  });

  it("shows the answer, sources and invoice card, and sends nothing until confirmed", async () => {
    mocks.search = "c=9";
    mocks.getMessages.mockResolvedValue(pastPractice);
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("I can send invoice INV-9 to the client.")).toBeInTheDocument();
    expect(screen.getByText("Send the invoice for Alpha")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Sources" })).getByRole("link", { name: "Alpha vs Beta" })).toHaveAttribute(
      "href",
      "/cases/10",
    );
    const card = screen.getByRole("region", { name: "Invoice to send" });
    expect(within(card).getByText("INV-9")).toBeInTheDocument();
    // Rendering it sent nothing, and nothing has asked for confirmation yet.
    expect(sendFee).not.toHaveBeenCalled();
    expect(mocks.practiceChat).not.toHaveBeenCalled();
    expect(within(card).queryByRole("button", { name: "Confirm" })).not.toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Send invoice" }));
    expect(sendFee).not.toHaveBeenCalled();
    expect(within(card).getByRole("button", { name: "Confirm" })).toBeInTheDocument();
  });

  it("a chat that is not in the lists says so", async () => {
    mocks.search = "c=999";
    renderPage();
    await waitFor(() => expect(screen.getByText(/That chat was not found/)).toBeInTheDocument());
  });
});
