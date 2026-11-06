import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const nav = vi.hoisted(() => ({ pathname: "/cases/1" }));

vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));
vi.mock("@/hooks/use-review-count", () => ({
  useReviewCount: () => 3,
  formatBadge: (n: number) => (n > 99 ? "99+" : String(n)),
}));

import { MobileNav } from "@/components/layout/mobile-nav";
import { MSection, Reveal } from "@/components/mobile/primitives";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { useIsMobile } from "@/hooks/use-is-mobile";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Reveal", () => {
  it("makes folded content inert and invisible, and open content neither", () => {
    const { rerender, container } = render(
      <Reveal open={false}>
        <button>inside</button>
      </Reveal>,
    );
    const root = container.firstElementChild as HTMLElement;
    expect(root).toHaveAttribute("inert");
    expect(root.className).toContain("invisible");
    expect(root.className).toContain("grid-rows-[0fr]");

    rerender(
      <Reveal open>
        <button>inside</button>
      </Reveal>,
    );
    expect(root).not.toHaveAttribute("inert");
    expect(root.className).toContain("grid-rows-[1fr]");
    expect(root.className).not.toContain("invisible");
  });
});

describe("MSection", () => {
  it("remembers whether it was folded", async () => {
    const user = userEvent.setup();
    const first = render(
      <MSection id="t-section" title="Tasks" count={2}>
        <p>body</p>
      </MSection>,
    );
    const toggle = screen.getByRole("button", { name: /Tasks/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(window.localStorage.getItem("ci:open:section:t-section")).toBe("0");
    first.unmount();

    render(
      <MSection id="t-section" title="Tasks" count={2}>
        <p>body</p>
      </MSection>,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /Tasks/ })).toHaveAttribute("aria-expanded", "false"));
  });
});

describe("BottomSheet", () => {
  it("is a labelled modal that Esc and the close button dismiss, and leaves after its exit", async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <BottomSheet open onClose={onClose} label="Case options" title="A case">
        <p>actions</p>
      </BottomSheet>,
    );
    const dialog = screen.getByRole("dialog", { name: "Case options" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByText("actions")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Close Case options" }));
    expect(onClose).toHaveBeenCalledTimes(2);

    rerender(
      <BottomSheet open={false} onClose={onClose} label="Case options" title="A case">
        <p>actions</p>
      </BottomSheet>,
    );
    // The exit plays first (it is still in the page), then it is removed.
    expect(screen.queryByRole("dialog", { name: "Case options" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Case options" })).not.toBeInTheDocument(), {
      timeout: 1500,
    });
  });

  it("fades instead of sliding for people who ask for less motion", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    render(
      <BottomSheet open onClose={() => {}} label="Quiet">
        <p>x</p>
      </BottomSheet>,
    );
    // The slide-up is declared with a motion-reduce twin that turns it off.
    expect(screen.getByRole("dialog", { name: "Quiet" }).className).toContain("motion-reduce:animate-none");
  });
});

describe("useIsMobile", () => {
  it("is false without matchMedia and follows the query when there is one", () => {
    expect(renderHook(() => useIsMobile()).result.current).toBe(false);

    let listener: (() => void) | null = null;
    let matches = true;
    vi.stubGlobal("matchMedia", () => ({
      get matches() {
        return matches;
      },
      addEventListener: (_: string, cb: () => void) => {
        listener = cb;
      },
      removeEventListener: () => {
        listener = null;
      },
    }));
    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(true);
    act(() => {
      matches = false;
      listener?.();
    });
    expect(result.current).toBe(false);
  });
});

describe("MobileNav", () => {
  it("lights the tab for the page you are in, slides its marker there, and badges Inbox", () => {
    nav.pathname = "/cases/1";
    render(<MobileNav />);
    expect(screen.getByRole("link", { name: /Cases/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Home/ })).not.toHaveAttribute("aria-current");
    // Cases is the second of six tabs: the marker is one tab-width along.
    expect(screen.getByTestId("nav-indicator").style.transform).toBe("translateX(100%)");
    expect(screen.getByTestId("nav-badge")).toHaveTextContent("3");
  });

  it("shows no marker on a page that is not a tab", () => {
    nav.pathname = "/settings";
    render(<MobileNav />);
    expect(screen.queryByTestId("nav-indicator")).not.toBeInTheDocument();
  });
});
