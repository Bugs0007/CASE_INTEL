import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RecentDocumentsCard } from "@/components/documents/recent-documents-card";
import { ClientContactsCard } from "@/components/cases/client-contacts-card";
import { CaseFeesCard } from "@/components/cases/case-fees-card";
import type {
  CaseFeeSummary,
  ClientContact,
  Document,
  Hearing,
  NestedAppearanceFee,
} from "@/types";

vi.mock("@/lib/api/billing", () => ({
  appearanceFeesApi: {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    generateInvoice: vi.fn(),
    invoiceFile: vi.fn(),
    send: vi.fn(),
    markPaid: vi.fn(),
  },
  advocateProfileApi: { get: vi.fn(), update: vi.fn() },
  travelBookingsApi: { list: vi.fn(), upload: vi.fn(), file: vi.fn(), delete: vi.fn() },
}));

import { advocateProfileApi } from "@/lib/api/billing";

function wrap(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(advocateProfileApi.get).mockResolvedValue({
    contact_email: "advocate@example.com",
    default_fee_amount: "15000.00",
  } as never);
});

function doc(id: number, overrides: Partial<Document> = {}): Document {
  return {
    id,
    filename: `file-${id}.pdf`,
    display_name: `File ${id}`,
    file_type: "application/pdf",
    document_type: "pleading",
    document_date: null,
    processing_status: "completed",
    job_status: null,
    created_at: `2026-10-${String(id).padStart(2, "0")}T10:00:00Z`,
    ...overrides,
  } as Document;
}

describe("Documents card", () => {
  const documents = [
    doc(1, { document_type: "court_order", display_name: "Order 1", document_date: "2026-08-01" }),
    doc(2, { document_type: "court_order", display_name: "Order 2", document_date: "2026-10-01" }),
    doc(3),
    doc(4),
    doc(5),
    doc(6),
  ];

  function renderCard(onView = vi.fn()) {
    wrap(
      <RecentDocumentsCard
        documents={documents}
        isLoading={false}
        onUploadClick={vi.fn()}
        onProcess={vi.fn()}
        onDelete={vi.fn()}
        onView={onView}
        isProcessPending={false}
        isDeletePending={false}
      />,
    );
    return onView;
  }

  it("shows the latest order first, then the newest uploads, at most 4", () => {
    renderCard();
    const names = screen.getAllByTitle(/^Open /).map((el) => el.textContent);
    expect(names).toEqual(["Order 2", "File 6", "File 5", "File 4"]);
    expect(screen.getByText("Latest order")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View all (6)" })).toBeInTheDocument();
  });

  it("lists every document in the expanded view and opens one in the viewer", async () => {
    const user = userEvent.setup();
    const onView = renderCard();
    await user.click(screen.getByRole("button", { name: "Expand Documents" }));

    const dialog = within(screen.getByRole("dialog", { name: "Documents" }));
    expect(dialog.getAllByTitle(/^Open /)).toHaveLength(6);

    await user.click(dialog.getByTitle("Open file-3.pdf"));
    expect(onView).toHaveBeenCalledWith(3);
  });

  it("has no collapse control: cards never fold", () => {
    renderCard();
    expect(screen.queryByText("Collapse")).not.toBeInTheDocument();
    expect(screen.queryByText("Expand")).not.toBeInTheDocument();
  });
});

describe("Client contacts card", () => {
  const contact = (id: number, overrides: Partial<ClientContact> = {}): ClientContact =>
    ({
      id,
      name: `Person ${id}`,
      email: null,
      phone: null,
      role: "assistant",
      is_billing_contact: false,
      ...overrides,
    }) as ClientContact;

  it("shows the primary and billing contact first, max 2, and the rest on expand", async () => {
    const user = userEvent.setup();
    wrap(
      <ClientContactsCard
        contacts={[contact(1), contact(2, { is_billing_contact: true }), contact(3, { role: "primary" })]}
        onEditDetails={vi.fn()}
      />,
    );
    expect(screen.getByText("Person 3")).toBeInTheDocument();
    expect(screen.getByText("Person 2")).toBeInTheDocument();
    expect(screen.queryByText("Person 1")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "View all (3)" }));
    expect(within(screen.getByRole("dialog")).getByText("Person 1")).toBeInTheDocument();
  });
});

describe("Fees & billing card", () => {
  const fee = (id: number, status: NestedAppearanceFee["status"], paidAt: string | null = null) =>
    ({
      id,
      category: "appearance",
      category_display: "Appearance Fee",
      amount: "15000.00",
      status,
      status_display: status === "paid" ? "Paid" : status === "invoiced" ? "Invoiced" : "Pending",
      invoice_number: status === "pending" ? "" : `INV-${id}`,
      paid_at: paidAt,
      send_status: "not_sent",
    }) as NestedAppearanceFee;

  const hearing = (id: number, date: string, fees: NestedAppearanceFee[]): Hearing =>
    ({
      id,
      hearing_date: `${date}T00:00:00Z`,
      hearing_type_display: "Motion",
      status: "completed",
      appearance_fees: fees,
      travel_bookings: [],
    }) as unknown as Hearing;

  const summary = {
    pending_count: 1,
    pending_amount: "15000.00",
    invoiced_count: 1,
    invoiced_amount: "15000.00",
    paid_count: 2,
    paid_amount: "30000.00",
    outstanding_amount: "30000.00",
    total_amount: "60000.00",
  } as CaseFeeSummary;

  const hearings = [
    hearing(1, "2026-08-01", [fee(10, "paid", "2026-08-20T00:00:00Z")]),
    hearing(2, "2026-09-01", [fee(11, "invoiced")]),
    hearing(3, "2026-10-01", [fee(12, "paid", "2026-10-25T00:00:00Z"), fee(13, "pending")]),
  ];

  it("lists unpaid charges first, 3 at most, with the case's outstanding total", () => {
    wrap(<CaseFeesCard caseId={7} summary={summary} hearings={hearings} />);

    const rows = within(screen.getByRole("heading", { name: /Fees & billing/ }).closest(".ci-card")!)
      .getAllByRole("list", { name: "Charges" })
      .map((list) => list.textContent);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toContain("Invoiced");
    expect(rows[1]).toContain("Pending");
    expect(rows[2]).toContain("Paid");
    expect(screen.getByText("Outstanding").nextElementSibling).toHaveTextContent("30,000");
    expect(screen.getByRole("button", { name: "View all (4)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record fee/ })).toBeInTheDocument();
  });

  it("keeps the invoice actions inside the expanded view", async () => {
    const user = userEvent.setup();
    wrap(<CaseFeesCard caseId={7} summary={summary} hearings={hearings} />);
    await user.click(screen.getByRole("button", { name: "Expand Fees & billing" }));

    const dialog = within(screen.getByRole("dialog", { name: "Fees & billing" }));
    expect(dialog.getAllByRole("list", { name: "Charges" })).toHaveLength(4);
    expect(dialog.getByRole("button", { name: "Generate Invoice (Appearance Fee)" })).toBeInTheDocument();
    expect(dialog.getByRole("button", { name: "Mark Paid (Appearance Fee)" })).toBeInTheDocument();
  });

  it("asks for a hearing first when there is none to bill against", () => {
    wrap(<CaseFeesCard caseId={7} summary={summary} hearings={[]} />);
    expect(screen.getByText(/Add a hearing first/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Record fee/ })).not.toBeInTheDocument();
  });
});
