import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { UnbilledHearings } from "@/components/billing/unbilled-hearings";
import type { AdvocateProfile, UninvoicedHearing } from "@/types";

// Only the network layer is mocked: the hooks and the component run for real.
vi.mock("@/lib/api/billing", () => ({
  appearanceFeesApi: { create: vi.fn() },
  advocateProfileApi: { get: vi.fn(), update: vi.fn() },
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { advocateProfileApi, appearanceFeesApi } from "@/lib/api/billing";

// Shaped like the scratch-DB rows the Billing page showed: CNR-added cases
// whose case number is "CNR <cnr>" and whose title is still the bare CNR.
const ROWS: UninvoicedHearing[] = [
  { hearing_id: 518, hearing_date: "2026-09-03T00:00:00Z", case_id: 21, case_title: "HBHC010536072026", case_number: "CNR HBHC010536072026", pending_amount: "0.00", has_fee: false },
  { hearing_id: 480, hearing_date: "2026-09-11T00:00:00Z", case_id: 10, case_title: "Lakshmi vs State", case_number: "WP/26147/2026", pending_amount: "0.00", has_fee: false },
  { hearing_id: 481, hearing_date: "2026-09-15T00:00:00Z", case_id: 10, case_title: "Lakshmi vs State", case_number: "WP/26147/2026", pending_amount: "2500.50", has_fee: true },
];

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <UnbilledHearings rows={ROWS} />
    </QueryClientProvider>,
  );
}

describe("UnbilledHearings", () => {
  beforeEach(() => vi.clearAllMocks());

  it("groups by case and fills in the default fee once the profile arrives", async () => {
    let resolveProfile: (p: AdvocateProfile) => void = () => {};
    vi.mocked(advocateProfileApi.get).mockReturnValue(new Promise((r) => (resolveProfile = r)));
    renderList();

    const groups = screen.getAllByRole("list").map((ul) => ul.closest("section")!);
    expect(groups).toHaveLength(2);
    // A placeholder title isn't repeated under the case number.
    expect(within(groups[0]).queryByText("HBHC010536072026")).not.toBeInTheDocument();
    expect(within(groups[1]).getByText("Lakshmi vs State")).toBeInTheDocument();
    // A hearing that already has a fee says so instead of offering another.
    expect(within(groups[1]).getByText("₹2,500.50 not invoiced")).toBeInTheDocument();

    const first = screen.getByLabelText("Fee for the hearing on Sep 3, 2026") as HTMLInputElement;
    expect(first.value).toBe("");
    resolveProfile({ default_fee_amount: "15000.00" } as AdvocateProfile);
    // The rows rendered before the profile loaded -- the prefill still lands.
    await waitFor(() => expect(first.value).toBe("15000"));
  });

  it("records the fee inline with the amount shown", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue({ default_fee_amount: "15000.00" } as AdvocateProfile);
    vi.mocked(appearanceFeesApi.create).mockResolvedValue({} as never);
    renderList();

    const input = screen.getByLabelText("Fee for the hearing on Sep 11, 2026") as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe("15000"));
    await userEvent.clear(input);
    await userEvent.type(input, "20000");
    await userEvent.click(within(input.closest("li")!).getByRole("button", { name: /record fee/i }));

    await waitFor(() =>
      expect(appearanceFeesApi.create).toHaveBeenCalledWith({ hearing: 480, category: "appearance", amount: "20000" }),
    );
  });
});
