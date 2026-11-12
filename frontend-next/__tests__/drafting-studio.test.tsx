import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { body, detail, output, revision } from "./drafting-fixtures";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  create: vi.fn(),
  get: vi.fn(),
  revision: vi.fn(),
  saveRevision: vi.fn(),
  retry: vi.fn(),
  approve: vi.fn(),
  createOutput: vi.fn(),
  downloadOutput: vi.fn(),
  docs: vi.fn(),
}));

vi.mock("@/lib/api/drafts", () => ({
  draftsApi: {
    list: mocks.list,
    create: mocks.create,
    get: mocks.get,
    revision: mocks.revision,
    saveRevision: mocks.saveRevision,
    retry: mocks.retry,
    approve: mocks.approve,
    createOutput: mocks.createOutput,
    downloadOutput: mocks.downloadOutput,
  },
  caseNotesApi: { list: vi.fn().mockResolvedValue([]), remove: vi.fn() },
}));
vi.mock("@/lib/api/documents", () => ({ documentsApi: { list: mocks.docs } }));
vi.mock("@/components/cases/compact/compact-card", () => ({
  PageDialog: ({ isOpen, children }: { isOpen: boolean; children: React.ReactNode }) =>
    isOpen ? <div role="dialog">{children}</div> : null,
}));

import { APIError } from "@/lib/api/client";
import { DraftStudio } from "@/components/drafting/draft-studio";

function Harness({ initial = null }: { initial?: number | null }) {
  const [id, setId] = useState<number | null>(initial);
  return <DraftStudio caseId={7} caseTitle="A v B" open draftId={id} onSelect={setId} onClose={() => {}} />;
}

function renderStudio(initial: number | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness initial={initial} />
    </QueryClientProvider>,
  );
}

const apiError = (status: number, data: unknown) => new APIError(status, data);

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
  mocks.list.mockResolvedValue([]);
  mocks.docs.mockResolvedValue([
    { id: 42, filename: "order.pdf", display_name: "Order 4" },
  ]);
  mocks.get.mockResolvedValue(detail());
  vi.stubGlobal("crypto", { randomUUID: vi.fn().mockReturnValueOnce("req-1").mockReturnValue("req-n") });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("brief form", () => {
  it("shows the case, the no-documents line, and sends the contract payload with a reused request id", async () => {
    const user = userEvent.setup();
    mocks.create.mockRejectedValue(apiError(500, null));
    renderStudio();
    expect(screen.getByTestId("brief-case")).toHaveTextContent("A v B");
    expect(
      screen.getByText("No documents selected. The draft will use the recorded case details only."),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Instructions"), "Summarise");
    await user.click(await screen.findByLabelText("Order 4"));
    await user.click(screen.getByRole("button", { name: "Generate draft" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
    expect(mocks.create.mock.calls[0][0]).toEqual({
      case_id: 7,
      subtype: "status_memo",
      instructions: "Summarise",
      audience: "",
      tone: "neutral",
      length: "standard",
      source_document_ids: [42],
      client_request_id: expect.any(String),
    });
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Generate draft" }));
    await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(2));
    expect(mocks.create.mock.calls[1][0].client_request_id).toBe(mocks.create.mock.calls[0][0].client_request_id);
  });

  it("explains a 429 draft_limit", async () => {
    const user = userEvent.setup();
    mocks.create.mockRejectedValue(apiError(429, { code: "draft_limit", detail: "x" }));
    renderStudio();
    await user.click(screen.getByRole("button", { name: "Generate draft" }));
    expect(await screen.findByText(/Too many drafts are still being written/)).toBeInTheDocument();
  });
});

describe("generation", () => {
  it("polls while generating and stops when ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.get
      .mockResolvedValueOnce(detail({ status: "generating", current_revision: null }))
      .mockResolvedValue(detail());
    renderStudio(5);
    await screen.findByText(/Writing the draft/);
    await vi.advanceTimersByTimeAsync(2600);
    await screen.findByLabelText("Title");
    const calls = mocks.get.mock.calls.length;
    await vi.advanceTimersByTimeAsync(8000);
    expect(mocks.get.mock.calls.length).toBe(calls);
  });

  it("shows the server error and a Retry button when failed", async () => {
    const user = userEvent.setup();
    mocks.get.mockResolvedValue(detail({ status: "failed", current_revision: null, error: "The model was unavailable." }));
    mocks.retry.mockResolvedValue(detail({ status: "queued", current_revision: null }));
    renderStudio(5);
    expect(await screen.findByText("The model was unavailable.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mocks.retry).toHaveBeenCalledWith(5));
  });
});

describe("editing and saving", () => {
  it("marks unsaved, posts expected_revision and body, then clears the marker", async () => {
    const user = userEvent.setup();
    mocks.saveRevision.mockResolvedValue(detail({ current_revision: revision({ id: 101, version: 2, source: "edited" }) }));
    renderStudio(5);
    const title = await screen.findByLabelText("Title");
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    await user.type(title, "!");
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save as new version" }));
    await waitFor(() => expect(mocks.saveRevision).toHaveBeenCalled());
    expect(mocks.saveRevision).toHaveBeenCalledWith(5, {
      expected_revision: 100,
      body: { ...body, title: "Status memo!" },
    });
    await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());
  });

  it("warns on unload only while there are unsaved edits", async () => {
    const user = userEvent.setup();
    renderStudio(5);
    const title = await screen.findByLabelText("Title");
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await user.type(title, "x");
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });

  it("keeps the edits on a 409 stale_revision", async () => {
    const user = userEvent.setup();
    mocks.saveRevision.mockRejectedValue(apiError(409, { code: "stale_revision", detail: "x", current_revision_id: 101 }));
    renderStudio(5);
    await user.type(await screen.findByLabelText("Title"), "!");
    await user.click(screen.getByRole("button", { name: "Save as new version" }));
    expect(await screen.findByText("This draft changed elsewhere.")).toBeInTheDocument();
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Status memo!");
    expect(screen.getByRole("button", { name: "Reload latest" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep editing" })).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("lists the errors on 400 invalid_body", async () => {
    const user = userEvent.setup();
    mocks.saveRevision.mockRejectedValue(apiError(400, { code: "invalid_body", detail: "x", errors: ["Title is empty", "Section 1 has no blocks"] }));
    renderStudio(5);
    await user.type(await screen.findByLabelText("Title"), "!");
    await user.click(screen.getByRole("button", { name: "Save as new version" }));
    expect(await screen.findByText("Title is empty")).toBeInTheDocument();
    expect(screen.getByText("Section 1 has no blocks")).toBeInTheDocument();
  });

  it("tags suggestions and opens evidence with a route built from the record kind", async () => {
    const user = userEvent.setup();
    renderStudio(5);
    expect(await screen.findByText("Suggestion")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Hearing on 12 Nov" }));
    const region = screen.getByRole("region", { name: "Source" });
    expect(region).toHaveTextContent("Hearing");
    expect(region.querySelector("a")).toHaveAttribute("href", "/cases/7");
  });
});

describe("approval and release", () => {
  it("disables Approve with unsaved edits", async () => {
    const user = userEvent.setup();
    renderStudio(5);
    const approve = await screen.findByRole("button", { name: "Approve this version" });
    expect(approve).toBeEnabled();
    await user.type(screen.getByLabelText("Title"), "!");
    expect(approve).toBeDisabled();
  });

  it("requires the acknowledgement checkbox when items to verify exist", async () => {
    const user = userEvent.setup();
    mocks.get.mockResolvedValue(detail({ current_revision: revision({ body: { ...body, verification_items: ["Check the CNR"] }, missing_facts: ["Client address"] }) }));
    mocks.approve.mockResolvedValue(detail());
    renderStudio(5);
    const approve = await screen.findByRole("button", { name: "Approve this version" });
    expect(screen.getByText("Check the CNR")).toBeInTheDocument();
    expect(screen.getByText("Client address")).toBeInTheDocument();
    expect(approve).toBeDisabled();
    await user.click(screen.getByLabelText("I have checked the items above"));
    expect(approve).toBeEnabled();
    await user.click(approve);
    await waitFor(() => expect(mocks.approve).toHaveBeenCalledWith(5, { revision_id: 100, acknowledge_open_items: true }));
  });

  it("explains evidence_changed with the listed records", async () => {
    const user = userEvent.setup();
    mocks.approve.mockRejectedValue(apiError(409, { code: "evidence_changed", detail: "x", items: ["Hearing on 12 Nov"] }));
    renderStudio(5);
    await user.click(await screen.findByRole("button", { name: "Approve this version" }));
    expect(await screen.findByText(/changed or were removed since the draft was written/)).toBeInTheDocument();
    expect(screen.getAllByText("Hearing on 12 Nov").length).toBeGreaterThan(0);
  });

  it("exports the approved revision through the blob download path", async () => {
    const user = userEvent.setup();
    const created = vi.fn().mockReturnValue("blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    mocks.get.mockResolvedValue(
      detail({
        approved_revision_id: 100,
        current_revision: revision({ approved_at: "2026-11-02T10:00:00Z" }),
        revisions: [{ id: 100, version: 1, source: "generated", created_at: "2026-11-01T10:00:00Z", approved_at: "2026-11-02T10:00:00Z" }],
      }),
    );
    mocks.createOutput.mockResolvedValue(output());
    mocks.downloadOutput.mockResolvedValue(new Blob(["x"]));
    renderStudio(5);
    expect(await screen.findByTestId("approved-line")).toHaveTextContent("Approved");
    await user.click(screen.getByRole("button", { name: "Export DOCX" }));
    await waitFor(() => expect(mocks.createOutput).toHaveBeenCalledWith(5, { revision_id: 100, destination: "docx" }));
    await waitFor(() => expect(mocks.downloadOutput).toHaveBeenCalledWith(900));
    await waitFor(() => expect(created).toHaveBeenCalled());
  });

  it("saves a case note and refreshes the notes list", async () => {
    const user = userEvent.setup();
    mocks.get.mockResolvedValue(
      detail({
        approved_revision_id: 100,
        current_revision: revision({ approved_at: "2026-11-02T10:00:00Z" }),
        revisions: [{ id: 100, version: 1, source: "generated", created_at: "2026-11-01T10:00:00Z", approved_at: "2026-11-02T10:00:00Z" }],
      }),
    );
    mocks.createOutput.mockResolvedValue(output({ destination: "case_note", case_note_id: 3, filename: "" }));
    renderStudio(5);
    await user.click(await screen.findByRole("button", { name: "Save as case note" }));
    await waitFor(() => expect(mocks.createOutput).toHaveBeenCalledWith(5, { revision_id: 100, destination: "case_note" }));
  });

  it("says the approval belongs to the older version after an edit", async () => {
    mocks.get.mockResolvedValue(
      detail({
        approved_revision_id: 100,
        current_revision: revision({ id: 101, version: 2, source: "edited" }),
        revisions: [
          { id: 100, version: 1, source: "generated", created_at: "2026-11-01T10:00:00Z", approved_at: "2026-11-02T10:00:00Z" },
          { id: 101, version: 2, source: "edited", created_at: "2026-11-03T10:00:00Z", approved_at: null },
        ],
      }),
    );
    renderStudio(5);
    expect(await screen.findByText(/The approval belongs to version 1/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve this version" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Export DOCX" })).toBeInTheDocument();
  });
});

describe("version history", () => {
  it("loads an older version read only", async () => {
    const user = userEvent.setup();
    mocks.get.mockResolvedValue(
      detail({
        current_revision: revision({ id: 101, version: 2, source: "edited" }),
        revisions: [
          { id: 100, version: 1, source: "generated", created_at: "2026-11-01T10:00:00Z", approved_at: null },
          { id: 101, version: 2, source: "edited", created_at: "2026-11-03T10:00:00Z", approved_at: null },
        ],
      }),
    );
    mocks.revision.mockResolvedValue(revision({ body: { ...body, title: "Old title" } }));
    renderStudio(5);
    await screen.findByLabelText("Title");
    await user.click(screen.getByRole("button", { name: /^Version 1,/ }));
    await waitFor(() => expect(mocks.revision).toHaveBeenCalledWith(5, 1));
    await waitFor(() => expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Old title"));
    expect(screen.getByLabelText("Title")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Save as new version" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve this version" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Back to latest" }));
    expect(screen.getByRole("button", { name: "Save as new version" })).toBeInTheDocument();
  });
});
