import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { AgingBuckets } from "@/components/billing/aging-buckets";
import { formatINR } from "@/lib/utils";

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
    expect(within(grid).getByText("₹1,000")).toBeInTheDocument();
    expect(within(grid).getByText("1 invoice")).toBeInTheDocument();
    expect(within(grid).getByText("0 invoices")).toBeInTheDocument();
    expect(within(grid).getByText("₹25,000.50")).toBeInTheDocument();
    // Indian digit grouping for lakhs.
    expect(within(grid).getByText("₹1,50,000")).toBeInTheDocument();
  });

  it("keeps an empty bucket neutral -- amber and red only with invoices in it", () => {
    render(
      <AgingBuckets
        buckets={[
          { label: "0-30", count: 0, amount: "0.00" },
          { label: "31-60", count: 0, amount: "0.00" },
          { label: "61-90", count: 1, amount: "5000.00" },
          { label: "90+", count: 0, amount: "0.00" },
        ]}
      />,
    );
    const tiles = screen.getByTestId("aging-buckets").children;
    expect(tiles[1].className).not.toContain("border-status-pending");
    expect(tiles[3].className).not.toContain("border-status-alert");
    expect(tiles[2].className).toContain("border-status-pending");
  });

  it("formats every amount one way: rupee sign, lakh grouping, no .00", () => {
    expect(formatINR("131000.00")).toBe("₹1,31,000");
    expect(formatINR("1234.5")).toBe("₹1,234.50");
    expect(formatINR(0)).toBe("₹0");
  });
});
