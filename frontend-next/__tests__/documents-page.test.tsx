import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Document } from "@/types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/documents",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/components/layout/section-tabs", () => ({
  CASES_TABS: [],
  SectionTabs: () => null,
}));
vi.mock("@/components/documents/edit-document-dialog", () => ({
  EditDocumentDialog: ({ document }: { document: Document | null }) =>
    document ? <div role="dialog">Editing {document.filename}</div> : null,
}));
vi.mock("@/providers/dialog-provider", () => ({
  useDialogs: () => ({ openUploadDocument: vi.fn() }),
}));

const h = vi.hoisted(() => ({
  docs: [] as unknown[],
  view: vi.fn(),
  process: vi.fn(),
  del: vi.fn(),
}));
vi.mock("@/hooks/use-documents", () => ({
  useDocuments: () => ({ data: h.docs, isLoading: false }),
  useProcessDocument: () => ({ mutateAsync: h.process, variables: undefined }),
  useDeleteDocument: () => ({ mutateAsync: h.del, variables: undefined }),
  useViewDocument: () => ({ mutate: h.view, variables: undefined }),
}));

import DocumentsPage from "@/app/(dashboard)/documents/page";

let nextId = 1;
function doc(over: Partial<Document> & { caseId?: number; caseTitle?: string; caseNumber?: string }): Document {
  const { caseId, caseTitle, caseNumber, ...rest } = over;
  const id = nextId++;
  return {
    id,
    case_id: caseId ?? null,
    filename: `file-${id}.pdf`,
    file_path: "x",
    file_type: "pdf",
    file_size: 2048,
    document_type: "evidence",
    document_date: null,
    processing_status: "completed",
    chunk_count: 1,
    ocr_applied: false,
    job_status: null,
    job_progress_current: null,
    job_progress_total: null,
    job_error: null,
    created_at: "2026-10-01T10:00:00Z",
    case: caseId ? { id: caseId, title: caseTitle ?? `Case ${caseId}`, case_number: caseNumber ?? `CN/${caseId}/2026` } : undefined,
    ...rest,
  } as Document;
}

beforeEach(() => {
  nextId = 1;
  vi.clearAllMocks();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  h.docs = [
    doc({ filename: "alpha.pdf", caseId: 1, caseTitle: "Sharma v State", caseNumber: "WP/100/2026", created_at: "2026-10-05T00:00:00Z", file_size: 5000 }),
    doc({ filename: "bravo.pdf", caseId: 1, caseTitle: "Sharma v State", caseNumber: "WP/100/2026", created_at: "2026-10-01T00:00:00Z", file_size: 100, processing_status: "failed" }),
    doc({ filename: "charlie.pdf", caseId: 2, caseTitle: "Rao v Rao", caseNumber: "CS/7/2025", created_at: "2026-10-09T00:00:00Z", file_size: 9000 }),
    doc({ filename: "delta.pdf", created_at: "2026-09-01T00:00:00Z", processing_status: "processing" }),
  ];
});

function names() {
  return screen.getAllByRole("button", { name: /^[a-z]+\.pdf$/ }).map((b) => b.textContent);
}

describe("Documents page", () => {
  it("renders a card per document and no table", () => {
    render(<DocumentsPage />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(names()).toHaveLength(4);
    // Grouped by case (the default): the group header names the case, the card does not repeat the case link.
    expect(screen.getAllByRole("link", { name: /Sharma v State/ }).length).toBeGreaterThan(0);
  });

  it("shows a status chip only for documents that are not completed", () => {
    render(<DocumentsPage />);
    const cardOf = (name: string) => screen.getByText(name).closest(".ci-card") as HTMLElement;
    expect(cardOf("alpha.pdf").querySelector(".ci-chip--ok, .ci-chip--pending, .ci-chip--alert")).toBeNull();
    expect(cardOf("delta.pdf").querySelector(".ci-chip--pending")).not.toBeNull();
    expect(cardOf("bravo.pdf").querySelector(".ci-chip--alert")).not.toBeNull();
  });

  it("shows case, date and size on a card", () => {
    render(<DocumentsPage />);
    const card = screen.getByText("charlie.pdf").closest(".ci-card") as HTMLElement;
    expect(within(card).getByText("Rao v Rao")).toBeInTheDocument();
    expect(within(card).getByText("CS/7/2025")).toBeInTheDocument();
    expect(within(card).getByText("Oct 9, 2026")).toBeInTheDocument();
    expect(within(card).getByText("8.8 KB")).toBeInTheDocument();
  });

  it("shows Retry only on failed cards", async () => {
    render(<DocumentsPage />);
    const retry = screen.getAllByRole("button", { name: "Retry" });
    expect(retry).toHaveLength(1);
    await userEvent.click(retry[0]);
    expect(h.process).toHaveBeenCalledWith(2);
    expect(h.view).not.toHaveBeenCalled();
  });

  it("opens the viewer when a card is clicked", () => {
    render(<DocumentsPage />);
    fireEvent.click(screen.getByText("alpha.pdf").closest(".ci-card")!);
    expect(h.view).toHaveBeenCalledWith(1, expect.anything());
  });

  it("has View, Edit, Retry and Delete in the card menu", async () => {
    render(<DocumentsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Actions for bravo.pdf" }));
    const menu = screen.getByRole("menu", { name: "Document actions" });
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "View",
      "Edit details",
      "Retry processing",
      "Delete",
    ]);
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Delete" }));
    expect(window.confirm).toHaveBeenCalled();
    expect(h.del).toHaveBeenCalledWith(2);
  });

  it("does not offer Retry in the menu of a completed document", async () => {
    render(<DocumentsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Actions for alpha.pdf" }));
    expect(screen.queryByRole("menuitem", { name: /Retry/ })).toBeNull();
  });

  it("groups by case with counts, newest case first, and collapses", async () => {
    render(<DocumentsPage />);
    // A flat grid by default; grouping by case is one click away.
    expect(screen.queryByRole("button", { expanded: true })).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Case" }));
    const heads = screen.getAllByRole("button", { expanded: true });
    const labels = heads.map((b) => b.getAttribute("aria-label"));
    expect(labels).toEqual(["Collapse Rao v Rao", "Collapse Sharma v State", "Collapse No case"]);
    expect(screen.getByText("2 documents")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Collapse Sharma v State" }));
    expect(screen.queryByText("alpha.pdf")).toBeNull();
    expect(screen.getByText("charlie.pdf")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(screen.queryByText("charlie.pdf")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getByText("charlie.pdf")).toBeInTheDocument();
  });

  it("drops the group headers when grouping is off", async () => {
    render(<DocumentsPage />);
    await userEvent.click(screen.getByRole("button", { name: "None" }));
    expect(screen.queryByRole("button", { name: /^Collapse / })).toBeNull();
    expect(screen.queryByRole("button", { name: "Collapse all" })).toBeNull();
    expect(names()).toHaveLength(4);
  });

  it("filters by case, searching the combobox by case number", async () => {
    render(<DocumentsPage />);
    const box = screen.getByRole("combobox", { name: "Filter by case" });
    await userEvent.click(box);
    await userEvent.type(box, "CS/7");
    const options = within(screen.getByRole("listbox", { name: "Cases" })).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["All cases", "Rao v RaoCS/7/2025"]);
    await userEvent.click(screen.getByRole("option", { name: /Rao v Rao/ }));
    expect(screen.getByText("charlie.pdf")).toBeInTheDocument();
    expect(screen.queryByText("alpha.pdf")).toBeNull();
    expect(screen.getByText("1 document across all cases")).toBeInTheDocument();
  });

  it("sorts with the Sort by select", async () => {
    render(<DocumentsPage />);
    await userEvent.click(screen.getByRole("button", { name: "None" }));
    const sort = screen.getByRole("combobox", { name: "Sort by" });
    // default: newest first
    expect(names()).toEqual(["charlie.pdf", "alpha.pdf", "bravo.pdf", "delta.pdf"]);
    await userEvent.selectOptions(sort, "oldest");
    expect(names()).toEqual(["delta.pdf", "bravo.pdf", "alpha.pdf", "charlie.pdf"]);
    await userEvent.selectOptions(sort, "name");
    expect(names()).toEqual(["alpha.pdf", "bravo.pdf", "charlie.pdf", "delta.pdf"]);
    await userEvent.selectOptions(sort, "size");
    expect(names()[0]).toBe("charlie.pdf");
    expect(names()[3]).toBe("bravo.pdf");
  });

  it("has a Failed (n) chip that filters to failed documents", async () => {
    render(<DocumentsPage />);
    await userEvent.click(screen.getByRole("button", { name: "Failed (1)" }));
    expect(names()).toEqual(["bravo.pdf"]);
  });

  it("shows the empty state when no document matches", async () => {
    render(<DocumentsPage />);
    await userEvent.type(screen.getByRole("textbox", { name: "Search documents" }), "zzzz");
    expect(screen.getByText("No documents found")).toBeInTheDocument();
  });
});
