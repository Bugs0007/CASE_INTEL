import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GenerateDocumentDialog } from "@/components/documents/generate-document-dialog";
import { APIError } from "@/lib/api/client";
import type { Case, DocTemplateField, DocTemplateForCase } from "@/types";

vi.mock("@/lib/api/clients", () => ({
  docTemplatesApi: { list: vi.fn(), forCase: vi.fn(), generate: vi.fn() },
  clientMessagesApi: {},
  clientsApi: {},
  billingPortfolioApi: {},
  sentMessagesApi: {},
  refreshAllApi: {},
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { docTemplatesApi } from "@/lib/api/clients";
import { showToast } from "@/components/ui/toaster";

function field(overrides: Partial<DocTemplateField>): DocTemplateField {
  return {
    name: "x",
    label: "X",
    required: true,
    multiline: false,
    value: "",
    source: "",
    where: "",
    missing: true,
    ...overrides,
  };
}

const VAKALAT: DocTemplateForCase = {
  key: "vakalatnama",
  title: "Vakalatnama",
  description: "Authority appointing you.",
  contact_id: 9,
  ready: false,
  fields: [
    field({ name: "case_number", label: "Case number", value: "OS/42/2026", source: "case.case_number", missing: false }),
    field({ name: "advocate_name", label: "Your name", value: "A. Rao", source: "profile.advocate_name", missing: false }),
    field({ name: "place", label: "Place of signing" }),
    field({ name: "executant_relation", label: "Executant's relation", where: "the client contact on this case" }),
  ],
};

const caseItem = {
  id: 42,
  client_contacts: [{ id: 9, name: "Ramesh Kumar" }],
} as unknown as Case;

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onClose = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <GenerateDocumentDialog isOpen onClose={onClose} caseItem={caseItem} />
    </QueryClientProvider>,
  );
  return { onClose };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(docTemplatesApi.forCase).mockResolvedValue([VAKALAT]);
});

describe("GenerateDocumentDialog", () => {
  it("shows what's on record and asks only for what isn't", async () => {
    renderDialog();
    expect(await screen.findByText("OS/42/2026")).toBeInTheDocument();
    expect(screen.getByText("A. Rao")).toBeInTheDocument();
    expect(screen.getByLabelText(/place of signing/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/executant's relation/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/your name/i)).not.toBeInTheDocument();
  });

  it("keeps Generate disabled until every required field is filled", async () => {
    const user = userEvent.setup();
    vi.mocked(docTemplatesApi.generate).mockResolvedValue({ id: 1, filename: "vakalatnama.pdf" } as never);
    const { onClose } = renderDialog();

    await screen.findByLabelText(/place of signing/i); // templates loaded
    const generate = screen.getByRole("button", { name: /generate pdf/i });
    expect(generate).toBeDisabled();
    expect(screen.getByText("2 required fields to fill")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/place of signing/i), "Hyderabad");
    await user.type(screen.getByLabelText(/executant's relation/i), "S/o Venkat Rao");
    expect(generate).toBeEnabled();
    await user.click(generate);

    await waitFor(() =>
      expect(docTemplatesApi.generate).toHaveBeenCalledWith(42, {
        template: "vakalatnama",
        contact_id: 9,
        inputs: { place: "Hyderabad", executant_relation: "S/o Venkat Rao" },
      }),
    );
    expect(showToast.success).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("asks for the side with a select and saves ticked answers for next time", async () => {
    const user = userEvent.setup();
    vi.mocked(docTemplatesApi.forCase).mockResolvedValue([
      {
        ...VAKALAT,
        fields: [
          field({
            name: "user_side", label: "Your client's side", where: "your client's side in the case details",
            savable: true, choices: ["Petitioner", "Respondent"],
          }),
          field({ name: "executant_age", label: "Executant's age", where: "the client contact on this case", savable: true }),
          field({ name: "place", label: "Place of signing" }),
        ],
      },
    ]);
    vi.mocked(docTemplatesApi.generate).mockResolvedValue({ id: 1, filename: "vakalatnama.pdf" } as never);
    renderDialog();

    const side = await screen.findByRole("combobox", { name: /^your client's side/i });
    expect(side.tagName).toBe("SELECT"); // not free text
    await user.selectOptions(side, "Respondent");
    await user.type(screen.getByLabelText(/executant's age/i), "45");
    await user.type(screen.getByLabelText(/place of signing/i), "Hyderabad");
    // "Place" has no home on the record: no box for it.
    expect(screen.getAllByLabelText(/save for next time/i)).toHaveLength(2);
    await user.click(screen.getAllByLabelText(/save for next time/i)[1]); // the age
    await user.click(screen.getByRole("button", { name: /generate pdf/i }));

    await waitFor(() =>
      expect(docTemplatesApi.generate).toHaveBeenCalledWith(42, {
        template: "vakalatnama",
        contact_id: 9,
        inputs: { user_side: "Respondent", executant_age: "45", place: "Hyderabad" },
        save: ["executant_age"],
      }),
    );
  });

  it("lists what the server still says is missing", async () => {
    const user = userEvent.setup();
    vi.mocked(docTemplatesApi.generate).mockRejectedValue(
      new APIError(400, {
        code: "missing_fields",
        detail: "Fill these in before generating: Court.",
        missing: [field({ name: "court", label: "Court", where: "court tracking for this case" })],
      }),
    );
    renderDialog();

    await user.type(await screen.findByLabelText(/place of signing/i), "Hyderabad");
    await user.type(screen.getByLabelText(/executant's relation/i), "S/o V");
    await user.click(screen.getByRole("button", { name: /generate pdf/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Court");
    expect(alert).toHaveTextContent("court tracking for this case");
    expect(showToast.error).not.toHaveBeenCalled();
  });
});
