import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  generateInvoice: vi.fn(),
  del: vi.fn(),
  draftCreate: vi.fn(),
  report: vi.fn(),
  apiBlob: vi.fn(),
}));

vi.mock("@/lib/api/billing", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/billing")>();
  return {
    ...actual,
    appearanceFeesApi: {
      ...actual.appearanceFeesApi,
      create: mocks.create,
      update: mocks.update,
      generateInvoice: mocks.generateInvoice,
      delete: mocks.del,
    },
  };
});
vi.mock("@/lib/api/drafts", () => ({ draftsApi: { create: mocks.draftCreate } }));

import { APIError } from "@/lib/api/client";
import {
  CreateFeeCard,
  DeleteFeeCard,
  GenerateInvoiceCard,
  StartDraftCard,
  UpdateFeeCard,
} from "@/components/dashboard/practice/practice-action-cards";
import { PracticeMessageList } from "@/components/dashboard/practice/practice-assistant-panel";
import { PracticeReportCard } from "@/components/dashboard/practice/practice-report-card";
import { sampleTurn } from "@/components/dashboard/practice/fixtures";
import { rebuildPracticeMessages } from "@/lib/practice-history";
import type { PracticeCardActions } from "@/hooks/use-practice-card-actions";
import type {
  PracticeCreateFeeCard,
  PracticeDeleteFeeCard,
  PracticeGenerateInvoiceCard,
  PracticeReportCard as ReportCardData,
  PracticeStartDraftCard,
  PracticeTurn,
  PracticeUpdateFeeCard,
} from "@/types/practice";
import type { Message } from "@/types/chat";

function fakeActions(over: Partial<PracticeCardActions> = {}): PracticeCardActions {
  return {
    createFee: vi.fn().mockResolvedValue({}),
    updateFee: vi.fn().mockResolvedValue({}),
    generateInvoice: vi.fn().mockResolvedValue({}),
    deleteFee: vi.fn().mockResolvedValue(undefined),
    createDraft: vi.fn().mockResolvedValue(77),
    ...over,
  };
}

const base = { case_id: 7, case_title: "Rao vs State", blockers: [] as string[] };

const createCard: PracticeCreateFeeCard = {
  ...base,
  kind: "create_fee",
  hearing_id: 5,
  hearing_options: [
    { id: 5, label: "11 Nov 2026", date: "2026-11-11" },
    { id: 4, label: "2 Oct 2026", date: "2026-10-02" },
  ],
  category: "appearance",
  amount: null,
  description: "Final hearing",
};
const updateCard: PracticeUpdateFeeCard = {
  ...base,
  kind: "update_fee",
  fee_id: 31,
  invoice_number: "INV-0007",
  fee_status: "invoiced",
  current: { amount: "15000.00", category: "appearance", description: "" },
  proposed: { amount: "18000" },
  regenerates_invoice: true,
};
const generateCard: PracticeGenerateInvoiceCard = {
  ...base,
  kind: "generate_invoice",
  fee_id: 31,
  amount: "15000.00",
  category: "appearance",
};
const deleteCard: PracticeDeleteFeeCard = {
  ...base,
  kind: "delete_fee",
  fee_id: 31,
  amount: "15000.00",
  category: "appearance",
  fee_status: "pending",
};
const draftCard: PracticeStartDraftCard = {
  ...base,
  kind: "start_draft",
  subtype: "client_letter",
  subtype_label: "Client letter",
  instructions: "Tell the client about the next date.",
};

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
});

describe("create_fee card", () => {
  it("calls nothing on render", () => {
    const actions = fakeActions();
    render(<CreateFeeCard card={createCard} actions={actions} />);
    expect(actions.createFee).not.toHaveBeenCalled();
  });

  it("confirms once on a double click, with the contract payload", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<CreateFeeCard card={createCard} actions={actions} />);
    // Appearance with an empty amount is allowed: the default fee applies.
    expect(screen.getByPlaceholderText("Use your default fee")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add fee" }));
    expect(actions.createFee).not.toHaveBeenCalled();
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText(/Fee added/);
    expect(actions.createFee).toHaveBeenCalledTimes(1);
    expect(actions.createFee).toHaveBeenCalledWith(7, { hearing: 5, category: "appearance", notes: "Final hearing" });
  });

  it("needs an amount for any category other than appearance", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<CreateFeeCard card={createCard} actions={actions} />);
    await user.selectOptions(screen.getByLabelText("Category"), "hotel");
    expect(screen.getByRole("button", { name: "Add fee" })).toBeDisabled();
    await user.type(screen.getByLabelText("Amount"), "4500");
    await user.click(screen.getByRole("button", { name: "Add fee" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(actions.createFee).toHaveBeenCalledWith(7, {
        hearing: 5,
        category: "hotel",
        amount: "4500",
        notes: "Final hearing",
      }),
    );
  });

  it("makes the advocate choose a hearing when the card named none", () => {
    render(<CreateFeeCard card={{ ...createCard, hearing_id: null }} actions={fakeActions()} />);
    expect(screen.getByRole("button", { name: "Add fee" })).toBeDisabled();
  });

  it("has no confirm with blockers, or with no hearing to bill", () => {
    const { unmount } = render(<CreateFeeCard card={{ ...createCard, blockers: ["Case is closed."] }} actions={fakeActions()} />);
    expect(screen.getByText("Case is closed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add fee" })).not.toBeInTheDocument();
    unmount();
    render(<CreateFeeCard card={{ ...createCard, hearing_id: null, hearing_options: [] }} actions={fakeActions()} />);
    expect(screen.getByText("This case has no hearing to bill against.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add fee" })).not.toBeInTheDocument();
  });

  it("shows the server's message on error and lets the advocate retry", async () => {
    const user = userEvent.setup();
    const actions = fakeActions({
      createFee: vi
        .fn()
        .mockRejectedValueOnce(new APIError(409, { detail: "That hearing already has this fee." }))
        .mockResolvedValueOnce({}),
    });
    render(<CreateFeeCard card={createCard} actions={actions} />);
    await user.click(screen.getByRole("button", { name: "Add fee" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("That hearing already has this fee.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText(/Fee added/);
    expect(actions.createFee).toHaveBeenCalledTimes(2);
  });
});

describe("update_fee card", () => {
  it("shows current and proposed values and the invoice note, and calls nothing on render", () => {
    const actions = fakeActions();
    render(<UpdateFeeCard card={updateCard} actions={actions} />);
    expect(screen.getByText("₹15,000")).toBeInTheDocument();
    expect(screen.getByText("₹18,000")).toBeInTheDocument();
    expect(screen.getByText("The invoice PDF will be updated, same number.")).toBeInTheDocument();
    expect(actions.updateFee).not.toHaveBeenCalled();
  });

  it("confirms once on a double click and sends only the proposed fields", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<UpdateFeeCard card={updateCard} actions={actions} />);
    await user.click(screen.getByRole("button", { name: "Change fee" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Fee changed and the invoice PDF updated.");
    expect(actions.updateFee).toHaveBeenCalledTimes(1);
    expect(actions.updateFee).toHaveBeenCalledWith(7, 31, { amount: "18000" });
  });

  it("sends an edited proposal", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<UpdateFeeCard card={{ ...updateCard, regenerates_invoice: false }} actions={actions} />);
    await user.selectOptions(screen.getByLabelText("New category"), "other");
    await user.click(screen.getByRole("button", { name: "Change fee" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(actions.updateFee).toHaveBeenCalledWith(7, 31, { amount: "18000", category: "other" }));
  });

  it("has no confirm with blockers", () => {
    render(<UpdateFeeCard card={{ ...updateCard, blockers: ["The invoice was already sent."] }} actions={fakeActions()} />);
    expect(screen.getByText("The invoice was already sent.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change fee" })).not.toBeInTheDocument();
  });

  it("shows the refusal and allows a retry", async () => {
    const user = userEvent.setup();
    const actions = fakeActions({
      updateFee: vi
        .fn()
        .mockRejectedValueOnce(new APIError(409, { detail: "This invoice was sent and cannot change." }))
        .mockResolvedValueOnce({}),
    });
    render(<UpdateFeeCard card={updateCard} actions={actions} />);
    await user.click(screen.getByRole("button", { name: "Change fee" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("This invoice was sent and cannot change.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText(/Fee changed/);
    expect(actions.updateFee).toHaveBeenCalledTimes(2);
  });
});

describe("generate_invoice card", () => {
  it("calls nothing on render; confirms once on a double click", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<GenerateInvoiceCard card={generateCard} actions={actions} />);
    expect(actions.generateInvoice).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Generate invoice" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Invoice generated. It has not been sent.");
    expect(actions.generateInvoice).toHaveBeenCalledTimes(1);
    expect(actions.generateInvoice).toHaveBeenCalledWith(7, 31);
  });

  it("has no confirm with blockers, and retries after an error", async () => {
    const { unmount } = render(
      <GenerateInvoiceCard card={{ ...generateCard, blockers: ["Already invoiced."] }} actions={fakeActions()} />,
    );
    expect(screen.queryByRole("button", { name: "Generate invoice" })).not.toBeInTheDocument();
    unmount();

    const user = userEvent.setup();
    const actions = fakeActions({
      generateInvoice: vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce({}),
    });
    render(<GenerateInvoiceCard card={generateCard} actions={actions} />);
    await user.click(screen.getByRole("button", { name: "Generate invoice" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Invoice generated. It has not been sent.");
    expect(actions.generateInvoice).toHaveBeenCalledTimes(2);
  });
});

describe("delete_fee card", () => {
  it("calls nothing on render; confirms once on a double click", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<DeleteFeeCard card={deleteCard} actions={actions} />);
    expect(actions.deleteFee).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Delete fee" }));
    expect(screen.getByText(/This cannot be undone/)).toBeInTheDocument();
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Fee deleted.");
    expect(actions.deleteFee).toHaveBeenCalledTimes(1);
    expect(actions.deleteFee).toHaveBeenCalledWith(7, 31);
  });

  it("has no confirm with blockers, and retries after an error", async () => {
    const { unmount } = render(
      <DeleteFeeCard card={{ ...deleteCard, blockers: ["Only a pending fee can be deleted."] }} actions={fakeActions()} />,
    );
    expect(screen.queryByRole("button", { name: "Delete fee" })).not.toBeInTheDocument();
    unmount();

    const user = userEvent.setup();
    const actions = fakeActions({ deleteFee: vi.fn().mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce(undefined) });
    render(<DeleteFeeCard card={deleteCard} actions={actions} />);
    await user.click(screen.getByRole("button", { name: "Delete fee" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Fee deleted.");
    expect(actions.deleteFee).toHaveBeenCalledTimes(2);
  });
});

describe("start_draft card", () => {
  it("calls nothing on render; creates once with the edited instructions and links to the draft", async () => {
    const user = userEvent.setup();
    const actions = fakeActions();
    render(<StartDraftCard card={draftCard} actions={actions} />);
    expect(actions.createDraft).not.toHaveBeenCalled();
    const box = screen.getByLabelText("Instructions");
    await user.clear(box);
    await user.type(box, "Keep it short.");
    await user.click(screen.getByRole("button", { name: "Start draft" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    const link = await screen.findByRole("link", { name: "Open draft" });
    expect(link).toHaveAttribute("href", "/cases/7?draft=77");
    expect(actions.createDraft).toHaveBeenCalledTimes(1);
    expect(actions.createDraft).toHaveBeenCalledWith({
      caseId: 7,
      subtype: "client_letter",
      instructions: "Keep it short.",
      clientRequestId: expect.any(String),
    });
  });

  it("keeps one request id across a retry, so a dropped reply cannot start two drafts", async () => {
    const user = userEvent.setup();
    const createDraft = vi.fn().mockRejectedValueOnce(new Error("net")).mockResolvedValueOnce(78);
    render(<StartDraftCard card={draftCard} actions={fakeActions({ createDraft })} />);
    await user.click(screen.getByRole("button", { name: "Start draft" }));
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("link", { name: "Open draft" });
    expect(createDraft.mock.calls[0][0].clientRequestId).toBe(createDraft.mock.calls[1][0].clientRequestId);
  });

  it("has no confirm with blockers", () => {
    render(<StartDraftCard card={{ ...draftCard, blockers: ["Drafting is off."] }} actions={fakeActions()} />);
    expect(screen.queryByRole("button", { name: "Start draft" })).not.toBeInTheDocument();
  });
});

describe("report card", () => {
  const report: ReportCardData = {
    kind: "billing",
    title: "Billing report",
    date_from: "2026-04-01",
    date_to: "2026-11-12",
    row_count: 12,
    formats: ["pdf", "docx"],
  };

  it("fetches the file for its own kind, format and dates, then saves it", async () => {
    const user = userEvent.setup();
    const blob = new Blob(["x"]);
    const reportSpy = vi.spyOn((await import("@/lib/api/practice")).practiceApi, "report").mockResolvedValue(blob);
    URL.createObjectURL = vi.fn(() => "blob:test");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<PracticeReportCard card={report} />);
    expect(reportSpy).not.toHaveBeenCalled();
    expect(screen.getByText("Billing report")).toBeInTheDocument();
    expect(screen.getByText(/12 rows/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Download DOCX" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(reportSpy).toHaveBeenCalledWith(report, "docx");
    click.mockRestore();
    reportSpy.mockRestore();
  });

  it("shows an error when the download fails", async () => {
    const user = userEvent.setup();
    const spy = vi
      .spyOn((await import("@/lib/api/practice")).practiceApi, "report")
      .mockRejectedValue(new APIError(500, { detail: "Report failed." }));
    render(<PracticeReportCard card={report} />);
    await user.click(screen.getByRole("button", { name: "Download PDF" }));
    await screen.findByText("Report failed.");
    spy.mockRestore();
  });
});

describe("history replay", () => {
  function history(turn: Record<string, unknown>): Message[] {
    return [
      {
        id: 1,
        role: "user",
        content: "Add a fee",
        created_at: "2026-11-12T09:00:00Z",
        references: [{ kind: "practice_request", turn }],
      },
      { id: 2, role: "assistant", content: "Here is the fee.", created_at: "2026-11-12T09:00:01Z", references: [] },
    ] as unknown as Message[];
  }

  function renderList(turn: PracticeTurn) {
    const client = new QueryClient();
    return render(
      <QueryClientProvider client={client}>
        <PracticeMessageList
          messages={[{ role: "assistant", id: "m-2", turn }]}
          onChooseCase={() => {}}
          onConfirmInvoice={() => {}}
          onDismissAction={() => {}}
        />
      </QueryClientProvider>,
    );
  }

  it("rebuilds a billing card and a report card from the stored turn", () => {
    const rebuilt = rebuildPracticeMessages(
      history({ action_card: deleteCard, report: { kind: "hearings", title: "Hearings", date_from: null, date_to: null, row_count: 0, formats: ["pdf"] } }),
      3,
    );
    const turn = rebuilt[1].role === "assistant" ? rebuilt[1].turn : null;
    expect(turn?.action_card).toMatchObject({ kind: "delete_fee", fee_id: 31 });
    expect(turn?.report).toMatchObject({ kind: "hearings" });
  });

  it("a replayed card calls no API until clicked and confirmed", async () => {
    const rebuilt = rebuildPracticeMessages(history({ action_card: deleteCard }), 3);
    const turn = (rebuilt[1] as { turn: PracticeTurn }).turn;
    renderList({ ...sampleTurn, ...turn });
    await screen.findByRole("region", { name: "Delete a pending fee" });
    expect(mocks.del).not.toHaveBeenCalled();
    expect(mocks.create).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();
    expect(mocks.generateInvoice).not.toHaveBeenCalled();
    expect(mocks.draftCreate).not.toHaveBeenCalled();
  });

  it("a rendered card confirms through the existing endpoint exactly once", async () => {
    mocks.del.mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderList({ ...sampleTurn, action_card: deleteCard });
    await user.click(screen.getByRole("button", { name: "Delete fee" }));
    await user.dblClick(screen.getByRole("button", { name: "Confirm" }));
    await screen.findByText("Fee deleted.");
    expect(mocks.del).toHaveBeenCalledTimes(1);
    expect(mocks.del).toHaveBeenCalledWith(31);
  });
});

// Last: it resets the module registry to mock the client.
describe("report endpoint", () => {
  const report: ReportCardData = {
    kind: "billing",
    title: "Billing report",
    date_from: "2026-04-01",
    date_to: "2026-11-12",
    row_count: 12,
    formats: ["pdf", "docx"],
  };

  it("builds the endpoint from the card fields, never a format query parameter", async () => {
    vi.resetModules();
    const apiBlob = vi.fn().mockResolvedValue(new Blob());
    vi.doMock("@/lib/api/client", () => ({ apiBlob, apiClient: vi.fn() }));
    const { practiceApi } = await import("@/lib/api/practice");
    await practiceApi.report(report, "pdf");
    expect(apiBlob).toHaveBeenCalledWith("/practice-assistant/reports/billing/pdf/", {
      params: { date_from: "2026-04-01", date_to: "2026-11-12" },
    });
    await practiceApi.report({ kind: "cases", date_from: null, date_to: null }, "docx");
    expect(apiBlob).toHaveBeenLastCalledWith("/practice-assistant/reports/cases/docx/", {
      params: { date_from: "", date_to: "" },
    });
    vi.doUnmock("@/lib/api/client");
  });
});
