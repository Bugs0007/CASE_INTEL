import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// What the API answers, moved on by each test.
const api = vi.hoisted(() => ({
  preference: null as unknown,
  quick: null as unknown,
  quickFor: "Zebulon Quillfeather",
  job: null as unknown,
  posts: [] as Record<string, unknown>[],
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    apiClient: vi.fn(
      async (path: string, options?: { method?: string; body?: string; params?: Record<string, string> }) => {
        if (path === "/court-structure/") {
          return options?.params?.state_code
            ? { options: { "1": "Adilabad", "2": "Hyderabad CCC", "3": "Karimnagar" } }
            : { options: { "29": "Telangana", "27": "Maharashtra" } };
        }
        if (path === "/cases/search-advocate/preference/") {
          const base = api.preference as { quick_search?: unknown } | null;
          if (options?.params?.name_or_bar_code) {
            const matches = options.params.name_or_bar_code.trim() === api.quickFor && options.params.state_code === "29";
            return { ...base, quick_search: matches ? api.quick : null };
          }
          return base;
        }
        if (path === "/cases/search-advocate/" && options?.method === "POST") {
          api.posts.push(JSON.parse(options.body ?? "{}"));
          return { job_id: 5 };
        }
        if (path === "/cases/search-advocate/5/") return api.job;
        return [];
      },
    ),
  };
});

import AdvocateSearchPage from "@/app/(dashboard)/cases/search/page";

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AdvocateSearchPage />
    </QueryClientProvider>,
  );
}

const QUICK = { complexes: 4, districts: 2, updated_at: new Date(Date.now() - 3 * 86_400_000).toISOString() };

function job(overrides: Record<string, unknown> = {}) {
  return {
    status: "running",
    cancel_requested: false,
    progress_current: 2,
    progress_total: 10,
    error: "",
    results: [],
    results_total: 0,
    results_truncated: false,
    failures: [],
    districts_total: 10,
    districts_status: {},
    complexes_searched: 6,
    complexes_done: 7,
    complexes_total_known: 18,
    current_district: "Karimnagar",
    mode: "state",
    created_at: new Date(Date.now() - 125_000).toISOString(),
    started_at: new Date(Date.now() - 125_000).toISOString(),
    ...overrides,
  };
}

beforeEach(() => {
  api.preference = { court_type: "district", hierarchy_config: { state_code: "29", dist_codes: ["1", "3"] }, quick_search: null };
  api.quick = QUICK;
  api.quickFor = "Zebulon Quillfeather";
  api.job = job();
  api.posts = [];
});

async function ready() {
  const adilabad = await screen.findByRole("checkbox", { name: "Adilabad" });
  await waitFor(() => expect(adilabad).toBeChecked());
  return adilabad;
}

const REMEMBERED = "Zebulon Quillfeather";
const NEW_NAME = "Someone Else Entirely";

async function typeName(user: ReturnType<typeof userEvent.setup>, name = NEW_NAME) {
  await user.type(screen.getByPlaceholderText(/e\.g\. Suresh Kumar/), name);
}

describe("choosing districts", () => {
  it("pre-selects the districts from the last search, and nothing else", async () => {
    renderPage();
    await ready();
    expect(screen.getByRole("checkbox", { name: "Karimnagar" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Hyderabad CCC" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /All districts/ })).not.toBeChecked();
  });

  it("first time, with nothing saved, it is all districts", async () => {
    api.preference = null;
    renderPage();
    await user_selectState();
    expect(await screen.findByRole("checkbox", { name: /All districts/ })).toBeChecked();
    expect(screen.getByRole("button", { name: /Search State-wide/ })).toBeDisabled(); // no name yet
  });

  it("searching with two districts ticked sends both", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user);
    expect(screen.getByRole("button", { name: "Search 2 Districts" })).toBeEnabled();

    await user.click(screen.getByRole("checkbox", { name: "Hyderabad CCC" }));
    await user.click(screen.getByRole("button", { name: "Search 3 Districts" }));

    await waitFor(() => expect(api.posts).toHaveLength(1));
    expect(api.posts[0]).toMatchObject({
      name_or_bar_code: NEW_NAME,
      state_code: "29",
      dist_codes: ["1", "3", "2"],
      mode: "full",
    });
  });

  it("one ticked district reads as a single-district search", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await user.click(screen.getByRole("checkbox", { name: "Karimnagar" }));
    await typeName(user);
    expect(screen.getByRole("button", { name: "Search This District" })).toBeEnabled();
  });

  it("ticking All districts clears the others and sends no district list", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user);
    await user.click(screen.getByRole("checkbox", { name: /All districts/ }));

    expect(screen.getByRole("checkbox", { name: "Adilabad" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Search State-wide" }));
    await waitFor(() => expect(api.posts).toHaveLength(1));
    expect(api.posts[0]).not.toHaveProperty("dist_codes");
    expect(api.posts[0]).toMatchObject({ mode: "full" });
  });

  it("changing the state forgets the districts", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await user.selectOptions(screen.getByRole("combobox"), "27");
    expect(await screen.findByRole("checkbox", { name: /All districts/ })).toBeChecked();
  });
});

async function user_selectState() {
  const user = userEvent.setup();
  const select = await screen.findByRole("combobox");
  await waitFor(() => expect(within(select).getByRole("option", { name: "Telangana" })).toBeInTheDocument());
  await user.selectOptions(select, "29");
}

describe("Quick search", () => {
  it("is offered, and the default, once courts are remembered for the name", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    expect(screen.queryByRole("radio", { name: /Quick search/ })).toBeNull(); // no name yet

    await typeName(user, REMEMBERED);
    const quick = await screen.findByRole("radio", { name: /Quick search/ });
    expect(quick).toBeChecked();
    expect(quick).toHaveAccessibleName(/4 court complexes in 2 districts/);
    expect(screen.getByRole("radio", { name: /Full scan/ })).not.toBeChecked();
    // Quick search ignores districts, so the checklist steps aside.
    expect(screen.queryByRole("group", { name: "Districts to search" })).toBeNull();
    expect(screen.getByRole("button", { name: "Quick Search" })).toBeEnabled();
  });

  it("sends mode quick and no districts", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user, REMEMBERED);
    await screen.findByRole("radio", { name: /Quick search/ });
    await user.click(screen.getByRole("button", { name: "Quick Search" }));

    await waitFor(() => expect(api.posts).toHaveLength(1));
    expect(api.posts[0]).toMatchObject({ mode: "quick", name_or_bar_code: REMEMBERED });
    expect(api.posts[0]).not.toHaveProperty("dist_codes");
  });

  it("Full scan brings the districts back, and stays chosen", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user, REMEMBERED);
    await user.click(await screen.findByRole("radio", { name: /Full scan/ }));

    expect(screen.getByRole("radio", { name: /Full scan/ })).toBeChecked();
    expect(screen.getByRole("group", { name: "Districts to search" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Full scan/ })).toHaveAccessibleName(/2 districts ticked/);
    await user.click(screen.getByRole("button", { name: "Search 2 Districts" }));
    await waitFor(() => expect(api.posts[0]).toMatchObject({ mode: "full", dist_codes: ["1", "3"] }));
  });

  it("is not offered for a name nothing is remembered for", async () => {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user, NEW_NAME);
    await waitFor(() => expect(screen.getByRole("button", { name: "Search 2 Districts" })).toBeEnabled());
    expect(screen.queryByRole("radio", { name: /Quick search/ })).toBeNull();
  });
});

describe("live progress", () => {
  async function startSearch() {
    const user = userEvent.setup();
    renderPage();
    await ready();
    await typeName(user, NEW_NAME);
    await user.click(screen.getByRole("button", { name: "Search 2 Districts" }));
  }

  it("shows N of M court complexes, the district and the elapsed time", async () => {
    await startSearch();
    const progress = await screen.findByTestId("search-progress");
    expect(progress).toHaveTextContent("7 of 18 court complexes searched · 7 more districts still to be listed");
    expect(progress).toHaveTextContent("Now searching Karimnagar");
    expect(progress).toHaveTextContent(/Elapsed 2m 0\ds|Elapsed 2m 1\ds/);
    expect(progress).toHaveTextContent("Results appear below as they're found");
  });

  it("says plainly when it is waiting behind other jobs", async () => {
    api.job = job({ status: "queued", started_at: null, created_at: new Date(Date.now() - 125_000).toISOString() });
    await startSearch();
    const progress = await screen.findByTestId("search-progress");
    expect(progress).toHaveTextContent("Waiting for the background worker to start this search.");
    expect(progress).toHaveTextContent("Still waiting after 2m");
    expect(progress).not.toHaveTextContent("court complexes searched");
  });

  it("shows cases as they are found", async () => {
    api.job = job({
      results: [
        {
          case_number: "OS/12/2024", case_type: "Civil", cnr_number: "TSAD010000012024", filing_number: "",
          registration_number: "", registration_date: null, petitioner: "A", respondent: "B", status: "Pending",
          court_name: "Civil Court", judges: [], next_hearing_date: null, advocate_match_verified: true,
        },
      ],
      results_total: 1,
    });
    await startSearch();
    expect(await screen.findByText("OS/12/2024")).toBeInTheDocument();
    expect(screen.getByText(/1 found so far/)).toBeInTheDocument();
  });

  it("an empty quick search points at the full scan", async () => {
    api.job = job({ status: "succeeded", mode: "quick", progress_current: 10 });
    await startSearch();
    expect(await screen.findByText(/in the remembered courts\. Run a full scan/)).toBeInTheDocument();
  });
});
