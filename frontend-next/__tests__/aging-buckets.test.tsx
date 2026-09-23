import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AgingBuckets, formatRupees } from "@/components/billing/aging-buckets";

describe("AgingBuckets", () => {
  it("renders each bucket's amount and invoice count", () => {
    render(
      <AgingBuckets
        buckets={[
          { label: "0-30", count: 1, amount: "1000.00" },
          { label: "31-60", count: 0, amount: "0.00" },
          { label: "61-90", count: 2, amount: "25000.50" },
          { label: "90+", count: 3, amount: "150000.00" },
        ]}
      />,
    );

    const grid = screen.getByTestId("aging-buckets");
    expect(within(grid).getByText("0-30 days")).toBeInTheDocument();
    expect(within(grid).getByText("Rs. 1,000.00")).toBeInTheDocument();
    expect(within(grid).getByText("1 invoice")).toBeInTheDocument();
    expect(within(grid).getByText("0 invoices")).toBeInTheDocument();
    expect(within(grid).getByText("Rs. 25,000.50")).toBeInTheDocument();
    // Indian digit grouping for lakhs.
    expect(within(grid).getByText("Rs. 1,50,000.00")).toBeInTheDocument();
  });

  it("formats rupees from the API's decimal strings", () => {
    expect(formatRupees("1234.5")).toBe("Rs. 1,234.50");
  });
});
