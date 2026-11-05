import { describe, it, expect } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExpandableCard } from "@/components/ui/expandable-card";

function Harness({ count = 3, shown = 2 }: { count?: number; shown?: number }) {
  return (
    <ExpandableCard
      title="Tasks & Deadlines"
      count={count}
      viewAll={{ total: count, shown }}
      actions={<button type="button">Add thing</button>}
    >
      {({ expanded, query }) => (
        <ul>
          {Array.from({ length: expanded ? count : shown }, (_, i) => `Item ${i + 1}`)
            .filter((text) => text.toLowerCase().includes(query.toLowerCase()))
            .map((text) => (
              <li key={text}>{text}</li>
            ))}
        </ul>
      )}
    </ExpandableCard>
  );
}

const expandButton = () => screen.getByRole("button", { name: "Expand Tasks & Deadlines" });
const dialog = () => screen.getByRole("dialog", { name: "Tasks & Deadlines" });
const gone = () => waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

describe("ExpandDialog", () => {
  it("opens a labelled modal dialog with the full list, over a card that keeps its preview", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    await user.click(expandButton());

    const panel = dialog();
    expect(panel).toHaveAttribute("aria-modal", "true");
    expect(within(panel).getAllByRole("listitem")).toHaveLength(3);
    // The card behind it is still there (and did not move or refetch).
    expect(screen.getAllByRole("listitem")).toHaveLength(2 + 3);
  });

  it("renders through a portal on <body>, not inside the card", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);
    await user.click(expandButton());
    expect(container.contains(dialog())).toBe(false);
    expect(document.body.contains(dialog())).toBe(true);
  });

  it("moves focus into the dialog on open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    expect(dialog()).toHaveFocus();
  });

  it("closes on Esc and returns focus to the expand button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    await user.keyboard("{Escape}");

    expect(expandButton()).toHaveFocus();
    await gone();
  });

  it("closes on a backdrop click and returns focus to the expand button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    await user.click(screen.getByTestId("expand-dialog-backdrop"));

    expect(expandButton()).toHaveFocus();
    await gone();
  });

  it("does not close when the click lands inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    await user.click(within(dialog()).getAllByRole("listitem")[0]);
    expect(dialog()).toBeInTheDocument();
  });

  it("closes with the Close button", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    await user.click(screen.getByRole("button", { name: "Close Tasks & Deadlines" }));
    await gone();
    expect(expandButton()).toHaveFocus();
  });

  it("traps Tab and Shift+Tab inside the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    const panel = dialog();
    const add = within(panel).getByRole("button", { name: "Add thing" });
    const close = within(panel).getByRole("button", { name: "Close Tasks & Deadlines" });

    await user.tab();
    expect(add).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    // Past the last control: wraps to the first, never out to the page.
    await user.tab();
    expect(add).toHaveFocus();
    // And backwards from the first: wraps to the last.
    await user.tab({ shift: true });
    expect(close).toHaveFocus();
  });

  it("keeps focus inside when Tab is pressed with focus outside the dialog", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());
    (document.activeElement as HTMLElement).blur();
    await user.tab();
    expect(dialog().contains(document.activeElement)).toBe(true);
  });

  it("locks page scroll while open and restores it after", async () => {
    const user = userEvent.setup();
    document.body.style.overflow = "auto";
    render(<Harness />);
    await user.click(expandButton());
    expect(document.body.style.overflow).toBe("hidden");

    await user.keyboard("{Escape}");
    await gone();
    expect(document.body.style.overflow).toBe("auto");
    document.body.style.overflow = "";
  });

  it("leaves Esc to a dialog opened on top of it", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(expandButton());

    const edit = document.createElement("div");
    edit.setAttribute("role", "dialog");
    edit.setAttribute("aria-modal", "true");
    document.body.appendChild(edit);

    await user.keyboard("{Escape}");
    expect(dialog()).toBeInTheDocument();
    edit.remove();
  });

  it("offers search only when the list is longer than 8", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness count={8} />);
    await user.click(expandButton());
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    unmount();

    render(<Harness count={12} />);
    await user.click(expandButton());
    const search = screen.getByRole("searchbox", { name: "Search Tasks & Deadlines" });
    await user.type(search, "item 11");
    expect(within(dialog()).getAllByRole("listitem")).toHaveLength(1);
  });

  it("shows 'View all (n)' only while more exist than the preview shows, and opens the dialog", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<Harness count={2} shown={2} />);
    expect(screen.queryByRole("button", { name: /view all/i })).not.toBeInTheDocument();
    unmount();

    render(<Harness count={5} shown={2} />);
    const viewAll = screen.getByRole("button", { name: "View all (5)" });
    await user.click(viewAll);
    expect(within(dialog()).getAllByRole("listitem")).toHaveLength(5);

    // Focus goes back to the link that opened it.
    await user.keyboard("{Escape}");
    expect(viewAll).toHaveFocus();
  });
});
