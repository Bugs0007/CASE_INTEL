import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  BulkCreateFeesCard,
  BulkSendInvoicesCard,
  CreateTaskCard,
  MarkPaidCard,
} from "@/components/dashboard/practice/practice-more-cards";
import type { PracticeCardActions } from "@/hooks/use-practice-card-actions";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function fakeActions(over: Partial<PracticeCardActions> = {}): PracticeCardActions {
  return {
    createFee: vi.fn().mockResolvedValue({}),
    updateFee: vi.fn().mockResolvedValue({}),
    generateInvoice: vi.fn().mockResolvedValue({}),
    deleteFee: vi.fn().mockResolvedValue(undefined),
    markPaid: vi.fn().mockResolvedValue({}),
    sendInvoice: vi.fn().mockResolvedValue({}),
    createTask: vi.fn().mockResolvedValue({}),
    createDraft: vi.fn().mockResolvedValue(1),
    ...over,
  };
}

function confirm(first: RegExp) {
  fireEvent.click(screen.getByRole("button", { name: first }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
}

describe("practice cards: tasks, mark paid, bulk", () => {
  it("adds a task with the edited title and due date, only after Confirm", async () => {
    const actions = fakeActions();
    render(
      <CreateTaskCard
        card={{ kind: "create_task", case_id: 7, case_title: "Rao vs State", title: "File the counter", due_date: "2026-11-16", blockers: [] }}
        actions={actions}
      />,
    );
    expect(actions.createTask).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "File the counter affidavit" } });
    confirm(/Add task/);
    await waitFor(() =>
      expect(actions.createTask).toHaveBeenCalledWith({ case: 7, title: "File the counter affidavit", due_date: "2026-11-16" }),
    );
  });

  it("does not offer mark paid when the card is blocked", () => {
    render(
      <MarkPaidCard
        card={{
          kind: "mark_invoice_paid", case_id: 7, case_title: "Rao", fee_id: 3, invoice_number: null, amount: "100.00",
          category: "appearance", fee_status: "pending", blockers: ["Generate the invoice first."],
        }}
        actions={fakeActions()}
      />,
    );
    expect(screen.queryByRole("button", { name: /Mark paid/ })).toBeNull();
    expect(screen.getByRole("alert")).toHaveTextContent("Generate the invoice first.");
  });

  it("creates one fee per ticked hearing and reports a failed row without retrying the rest", async () => {
    const createFee = vi
      .fn()
      .mockResolvedValueOnce({})
      .mockRejectedValueOnce(new Error("Hearing is cancelled"));
    const actions = fakeActions({ createFee });
    render(
      <BulkCreateFeesCard
        card={{
          kind: "bulk_create_fees", case_id: null, case_title: "", category: "appearance", amount: "5000.00",
          period_text: "last week", blockers: [],
          rows: [
            { hearing_id: 1, case_id: 7, case_title: "Rao", date: "2026-11-10", label: "10 Nov" },
            { hearing_id: 2, case_id: 8, case_title: "Sita", date: "2026-11-11", label: "11 Nov" },
            { hearing_id: 3, case_id: 9, case_title: "Ram", date: "2026-11-12", label: "12 Nov" },
          ],
        }}
        actions={actions}
      />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: /Ram/ }));
    confirm(/Add 2 fees/);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Added 1 fee. Not added: Sita"));
    expect(createFee).toHaveBeenCalledTimes(2);
    expect(createFee).toHaveBeenCalledWith(7, { hearing: 1, category: "appearance", amount: "5000.00" });
    expect(screen.queryByRole("button", { name: /Try again/ })).toBeNull();
  });

  it("sends only invoices without blockers", async () => {
    const actions = fakeActions();
    render(
      <BulkSendInvoicesCard
        card={{
          kind: "bulk_send_invoices", case_id: null, case_title: "", blockers: [],
          rows: [
            { fee_id: 1, case_id: 7, case_title: "Rao", invoice_number: "INV-1", amount: "100.00", recipient_email: "a@x.in", blockers: [] },
            { fee_id: 2, case_id: 8, case_title: "Sita", invoice_number: "INV-2", amount: "200.00", recipient_email: null, blockers: ["No billing email."] },
          ],
        }}
        actions={actions}
      />,
    );
    expect(screen.getByLabelText(/INV-2/)).toBeDisabled();
    confirm(/Send 1 invoice/);
    await waitFor(() => expect(actions.sendInvoice).toHaveBeenCalledTimes(1));
    expect(actions.sendInvoice).toHaveBeenCalledWith(7, 1);
  });
});
