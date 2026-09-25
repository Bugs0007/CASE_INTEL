import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { CaseDetailHeader } from "@/components/cases/case-detail-header";
import { hasPlaceholderTitle, isAwaitingUpdate, pluralize } from "@/lib/utils";
import type { Case } from "@/types";

describe("pluralize", () => {
  it("agrees with the count", () => {
    // Production: the case list said "1 cases".
    expect(pluralize(1, "case")).toBe("1 case");
    expect(pluralize(0, "case")).toBe("0 cases");
    expect(pluralize(24, "case")).toBe("24 cases");
  });
});

describe("placeholder titles", () => {
  it("treats a CNR or the case number standing in as the title as no title", () => {
    // WP/23998/2026's drafts said "Update on your matter: HBHC010494552026".
    expect(hasPlaceholderTitle({ title: "HBHC010494552026", cnr_number: "HBHC010494552026", case_number: "WP/23998/2026" })).toBe(true);
    expect(hasPlaceholderTitle({ title: "WP/23998/2026", cnr_number: null, case_number: "WP/23998/2026" })).toBe(true);
    expect(hasPlaceholderTitle({ title: "", cnr_number: null, case_number: "WP/1/2026" })).toBe(true);
    expect(hasPlaceholderTitle({ title: "Lakshmi vs State", cnr_number: "HBHC010494552026", case_number: "WP/23998/2026" })).toBe(false);
  });

  it("sees through the 'CNR ' case number a CNR-added case starts with", () => {
    expect(hasPlaceholderTitle({ title: "HBHC010536072026", cnr_number: null, case_number: "CNR HBHC010536072026" })).toBe(true);
    expect(hasPlaceholderTitle({ title: "CNR Holdings vs State", cnr_number: null, case_number: "CNR HBHC010536072026" })).toBe(false);
  });

  it("asks for a title on the case page", () => {
    const onEditDetails = vi.fn();
    render(
      <CaseDetailHeader
        case={{ title: "HBHC010494552026", cnr_number: "HBHC010494552026", case_number: "WP/23998/2026", status: "open", priority: "medium", case_type: null, filing_date: null } as Case}
        onEditDetails={onEditDetails}
      />,
    );
    expect(screen.getByText("Untitled matter")).toBeInTheDocument();
    screen.getByRole("button", { name: /add a title/i }).click();
    expect(onEditDetails).toHaveBeenCalled();
  });
});

describe("awaiting update", () => {
  it("is a past date still marked scheduled", () => {
    expect(isAwaitingUpdate({ hearing_date: "2020-01-01T00:00:00Z", status: "scheduled" })).toBe(true);
    expect(isAwaitingUpdate({ hearing_date: "2020-01-01T00:00:00Z", status: "completed" })).toBe(false);
    expect(isAwaitingUpdate({ hearing_date: "2099-01-01T00:00:00Z", status: "scheduled" })).toBe(false);
  });
});
