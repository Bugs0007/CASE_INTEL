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
  casesApi: { list: vi.fn().mockResolvedValue([]), get: vi.fn().mockResolvedValue({ id: 1, title: "Case" }) },
}));

const sendFee = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api/billing", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/billing")>();
  return { ...actual, appearanceFeesApi: { ...actual.appearanceFeesApi, send: sendFee } };
});

import { AssistantPage } from "@/components/assistant/assistant-page";
import { groupConversations } from "@/lib/assistant";
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
      <AssistantPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.search = "";
  mocks.push.mockReset();
  mocks.replace.mockReset();
  mocks.list.mockReset().mockImplementation((_caseId?: number, scope?: string) =>
    Promise.resolve(scope === "practice" ? practiceChats : [...caseChats]),
  );
  mocks.getMessages.mockReset().mockResolvedValue([]);
  mocks.practiceChat.mockReset();
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

  it("separates practice and older document chats", () => {
    const rows = [...practiceChats, chat({ id: 30, scope: "legacy_documents", title: "Old one" })];
    const groups = groupConversations(rows, "");
    expect(groups.practice.map((c) => c.id)).toEqual([9, 8]);
    expect(groups.legacy.map((c) => c.id)).toEqual([30]);
    expect(groups.cases).toEqual([]);
  });
});

describe("Case Bot page sidebar", () => {
  it("groups case chats under their case title, newest group first, with a link to the case", async () => {
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    const groupItems = within(casesSection).getAllByRole("listitem", { name: /vs/ });
    expect(groupItems.map((item) => item.getAttribute("aria-label"))).toEqual(["Gamma vs Delta", "Alpha vs Beta"]);
    expect(within(casesSection).getByRole("link", { name: "Alpha vs Beta" })).toHaveAttribute("href", "/cases/10");

    const practice = screen.getByRole("region", { name: "Your practice" });
    const names = within(practice).getAllByRole("button", { name: /^(Week ahead|Open deadlines)/ });
    expect(names[0]).toHaveTextContent("Open deadlines");
  });

  it("narrows the rows with the filter", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Cases" });
    await user.type(screen.getByLabelText("Filter chats"), "gamma");
    const casesSection = screen.getByRole("region", { name: "Cases" });
    expect(within(casesSection).queryByRole("link", { name: "Alpha vs Beta" })).not.toBeInTheDocument();
    expect(within(casesSection).getByRole("link", { name: "Gamma vs Delta" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your practice" })).not.toBeInTheDocument();
  });

  it("selecting a row puts the chat in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    await user.click(within(casesSection).getByRole("button", { name: /^Evidence/ }));
    expect(mocks.push).toHaveBeenCalledWith("/assistant?c=3");
  });

  it("asks for a scope before a new chat and puts it in the URL", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Cases" });
    await user.click(screen.getByRole("button", { name: "New chat" }));
    const sidebar = screen.getByRole("complementary", { name: "Case Bot chats" });
    await user.click(within(sidebar).getByRole("button", { name: "Your practice" }));
    expect(mocks.push).toHaveBeenCalledWith("/assistant?scope=practice");
  });

  it("confirms in the page before deleting a chat", async () => {
    const user = userEvent.setup();
    renderPage();
    const casesSection = await screen.findByRole("region", { name: "Cases" });
    await user.click(within(casesSection).getByRole("button", { name: "Delete chat Evidence" }));
    expect(screen.getByText("Delete this chat? This cannot be undone.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Delete this chat? This cannot be undone.")).not.toBeInTheDocument();
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
