import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const mocks = vi.hoisted(() => ({
  notes: vi.fn(),
  remove: vi.fn(),
  flag: { on: true },
}));

vi.mock("@/lib/api/drafts", () => ({
  draftsApi: { list: vi.fn().mockResolvedValue([]) },
  caseNotesApi: { list: mocks.notes, remove: mocks.remove },
}));
vi.mock("@/lib/feature-flags", () => ({
  get CASE_DRAFTING_ENABLED() {
    return mocks.flag.on;
  },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/cases/7",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/components/cases/compact/compact-card", () => ({
  PageDialog: ({ isOpen, children }: { isOpen: boolean; children: React.ReactNode }) =>
    isOpen ? <div role="dialog">{children}</div> : null,
}));

import { CaseDraftingSection } from "@/components/drafting/case-drafting-section";
import { CaseNotesSection } from "@/components/drafting/case-notes-section";

const note = {
  id: 1,
  case_id: 7,
  title: "Memo",
  body: "<script>alert(1)</script>\nline two",
  origin_draft_id: 5,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  mocks.notes.mockReset().mockResolvedValue([note]);
  mocks.remove.mockReset().mockResolvedValue(undefined);
  mocks.flag.on = true;
});

describe("notes", () => {
  it("renders a note body as text, never as HTML", async () => {
    const { container } = wrap(<CaseNotesSection caseId={7} />);
    expect(await screen.findByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  it("deletes after a confirm", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    wrap(<CaseNotesSection caseId={7} />);
    await user.click(await screen.findByRole("button", { name: "Delete note Memo" }));
    await waitFor(() => expect(mocks.remove).toHaveBeenCalledWith(1));
  });

  it("does not delete when the confirm is declined", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    wrap(<CaseNotesSection caseId={7} />);
    await user.click(await screen.findByRole("button", { name: "Delete note Memo" }));
    expect(mocks.remove).not.toHaveBeenCalled();
  });

  it("shows the empty state only with the flag on", async () => {
    mocks.notes.mockResolvedValue([]);
    const { unmount } = wrap(<CaseNotesSection caseId={7} />);
    expect(await screen.findByText(/No notes yet/)).toBeInTheDocument();
    unmount();
    mocks.flag.on = false;
    const { container } = wrap(<CaseNotesSection caseId={7} />);
    await waitFor(() => expect(mocks.notes).toHaveBeenCalledTimes(2));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an error with Retry when the flag is on", async () => {
    mocks.notes.mockRejectedValue(new Error("boom"));
    wrap(<CaseNotesSection caseId={7} />);
    expect(await screen.findByText("Could not load notes.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("entry point", () => {
  it("renders Draft with assistant with the flag on", async () => {
    wrap(<CaseDraftingSection caseId={7} caseTitle="A v B" />);
    expect(await screen.findByRole("button", { name: "Draft with assistant" })).toBeInTheDocument();
  });

  it("hides the entry point with the flag off but keeps saved notes", async () => {
    mocks.flag.on = false;
    wrap(<CaseDraftingSection caseId={7} caseTitle="A v B" />);
    expect(await screen.findByText("Memo")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Draft with assistant" })).not.toBeInTheDocument();
  });
});
