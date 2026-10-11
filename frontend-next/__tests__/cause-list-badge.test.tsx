import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CauseListBadge, CauseListInfo } from "@/components/hearings/cause-list-badge";
import { CauseListCoverageLine } from "@/components/cases/court-tracking-card";
import type { Hearing } from "@/types";

function hearing(overrides: Partial<Hearing>): Hearing {
  return {
    id: 1,
    case: 1,
    case_title: "A vs B",
    hearing_date: "2099-01-01T00:00:00Z",
    hearing_type: "other",
    hearing_type_display: "Other",
    location: null,
    judge: null,
    status: "scheduled",
    status_display: "Scheduled",
    notes: null,
    outcome: null,
    source: "ecourts",
    business_date: null,
    purpose: null,
    appearance_fees: [],
    travel_bookings: [],
    cause_list_status: "not_checked",
    cause_list_status_display: "",
    cause_list_item_number: "",
    cause_list_court_hall: "",
    cause_list_stage: "",
    cause_list_checked_at: null,
    order_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("CauseListBadge", () => {
  it("renders nothing before any check", () => {
    const { container } = render(<CauseListBadge hearing={hearing({})} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows item and court when listed, with bench and list type in the tooltip", () => {
    render(
      <CauseListBadge
        hearing={hearing({
          cause_list_status: "listed",
          cause_list_item_number: "3",
          cause_list_court_hall: "1",
          cause_list_bench: "APARESH KUMAR SINGH, G.M. MOHIUDDIN",
          cause_list_list_type: "DAILY LIST",
        })}
      />,
    );
    const chip = screen.getByText("Item 3 · Court 1");
    expect(chip.getAttribute("title")).toContain("Bench: APARESH KUMAR SINGH");
    expect(chip.getAttribute("title")).toContain("List: DAILY LIST");
  });

  it("keeps the five non-listed states visibly different", () => {
    const labels = (["not_published", "not_listed", "fetch_failed", "unsupported"] as const).map(
      (status) => {
        const { unmount } = render(<CauseListBadge hearing={hearing({ cause_list_status: status })} />);
        const text = document.body.textContent;
        unmount();
        return text;
      },
    );
    expect(labels).toEqual(["Not yet listed", "Not listed", "Couldn't check", "Not covered"]);
  });

  it("explains a partial publication from the note", () => {
    render(
      <CauseListBadge
        hearing={hearing({ cause_list_status: "not_published", cause_list_note: "3 of 58 lists not uploaded yet" })}
      />,
    );
    expect(screen.getByText("Not yet listed").getAttribute("title")).toContain("3 of 58 lists not uploaded yet");
  });

  it("never calls an unreadable list 'Not listed'", () => {
    render(<CauseListBadge hearing={hearing({ cause_list_status: "fetch_failed" })} />);
    expect(screen.queryByText("Not listed")).toBeNull();
  });
});

describe("CauseListInfo", () => {
  it("lists every place a matter appears", () => {
    render(
      <CauseListInfo
        hearing={hearing({
          cause_list_status: "listed",
          cause_list_matches: [
            { item_number: "3", court_hall: "1", bench: "Bench A", list_type: "DAILY LIST", stage: "", is_primary: true },
            { item_number: "12", court_hall: "1", bench: "Bench A", list_type: "SUPPLEMENTARY", stage: "", is_primary: false },
          ],
        })}
      />,
    );
    expect(screen.getByText("Item 3 · Court 1 · Bench A · DAILY LIST")).toBeTruthy();
    expect(screen.getByText("Item 12 · Court 1 · Bench A · SUPPLEMENTARY")).toBeTruthy();
  });

  it("links to the court's site for verification, not to a portal PDF", () => {
    render(
      <CauseListInfo
        hearing={hearing({
          cause_list_status: "listed",
          cause_list_item_number: "3",
          cause_list_verify_url: "https://hcservices.ecourts.gov.in/hcservices/main.php",
        })}
      />,
    );
    const link = screen.getByText("Verify on the court's site");
    expect(link.getAttribute("href")).toBe("https://hcservices.ecourts.gov.in/hcservices/main.php");
  });

  it("offers the published list itself only when its URL is public", () => {
    render(
      <CauseListInfo
        hearing={hearing({
          cause_list_status: "listed",
          cause_list_source_url: "https://api.sci.gov.in/jonew/cl/2026-10-12/M_J_1.pdf",
          cause_list_verify_url: "https://www.sci.gov.in/cause-list/",
        })}
      />,
    );
    expect(screen.getByText("Open the published list").getAttribute("href")).toContain("M_J_1.pdf");
    expect(screen.queryByText("Verify on the court's site")).toBeNull();
  });

  it("shows the reason a court is not covered", () => {
    render(
      <CauseListInfo
        hearing={hearing({ cause_list_status: "unsupported", cause_list_note: "Kerala High Court: PDFs are not served" })}
      />,
    );
    expect(screen.getByText("Kerala High Court: PDFs are not served")).toBeTruthy();
  });

  it("renders nothing when there is nothing to add", () => {
    const { container } = render(<CauseListInfo hearing={hearing({ cause_list_status: "not_listed" })} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("CauseListCoverageLine", () => {
  it("says a covered court is checked before each hearing", () => {
    render(<CauseListCoverageLine coverage={{ status: "supported", label: "Andhra Pradesh High Court", reason: "", url: "" }} />);
    expect(screen.getByText("Checked before each hearing")).toBeTruthy();
  });

  it("states the reason and links the court's page for an uncovered court", () => {
    render(
      <CauseListCoverageLine
        coverage={{
          status: "unsupported",
          label: "",
          reason: "Kerala High Court: PDFs are not served",
          url: "https://hcservices.ecourts.gov.in/hcservices/main.php",
        }}
      />,
    );
    expect(screen.getByText(/Not covered — Kerala High Court/)).toBeTruthy();
    expect(screen.getByText("court's site").getAttribute("href")).toContain("hcservices");
  });

  it("explains a pending court as starting after the next refresh", () => {
    render(<CauseListCoverageLine coverage={{ status: "pending", label: "", reason: "", url: "" }} />);
    expect(screen.getByText(/starts after the next refresh/)).toBeTruthy();
  });
});
