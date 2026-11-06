"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

/** A small dropdown menu: a trigger button and a list of actions.
 *
 *   <Menu>
 *     <MenuTrigger>New</MenuTrigger>
 *     <MenuList label="New">
 *       <MenuItem onSelect={...}>New case</MenuItem>
 *     </MenuList>
 *   </Menu>
 *
 * One menu is open at a time (opening one closes the rest). It closes on an
 * outside click, on Esc (focus goes back to the trigger), on Tab and when an
 * item is chosen. Up/Down/Home/End move between items. */

const OPEN_EVENT = "ci:menu-open";

interface MenuContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  /** Closes the menu and puts focus back on the trigger. */
  close: () => void;
  listId: string;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
}

const MenuContext = createContext<MenuContextValue | null>(null);

function useMenu(): MenuContextValue {
  const ctx = useContext(MenuContext);
  if (!ctx) throw new Error("Menu parts must be rendered inside <Menu>");
  return ctx;
}

export function Menu({ children, className }: { children: ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const listId = `${id}-menu`;
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!open) return;

    // Opening this one closes every other.
    window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: id }));
    const onOtherOpened = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== id) setOpen(false);
    };
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    };

    window.addEventListener(OPEN_EVENT, onOtherOpened);
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("touchstart", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener(OPEN_EVENT, onOtherOpened);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("touchstart", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, id, close]);

  return (
    <MenuContext.Provider value={{ open, setOpen, close, listId, triggerRef }}>
      <div ref={rootRef} className={cn("relative", className)}>
        {children}
      </div>
    </MenuContext.Provider>
  );
}

export function MenuTrigger({
  className,
  onClick,
  onKeyDown,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  const { open, setOpen, listId, triggerRef } = useMenu();
  return (
    <button
      ref={triggerRef}
      type="button"
      aria-haspopup="menu"
      aria-expanded={open}
      aria-controls={open ? listId : undefined}
      className={className}
      onClick={(event) => {
        onClick?.(event);
        setOpen(!open);
      }}
      onKeyDown={(event) => {
        onKeyDown?.(event);
        if (event.key === "ArrowDown" && !open) {
          event.preventDefault();
          setOpen(true);
        }
      }}
      {...props}
    />
  );
}

type Placement = "below" | "above";

const PLACEMENT: Record<Placement, string> = {
  below: "top-full mt-1.5",
  above: "bottom-full mb-1.5",
};

export function MenuList({
  children,
  label,
  placement = "below",
  align = "start",
  className,
}: {
  children: ReactNode;
  /** Accessible name of the menu. */
  label: string;
  /** Opens under the trigger, or above it (for a trigger at the bottom). */
  placement?: Placement;
  align?: "start" | "end";
  className?: string;
}) {
  const { open, listId } = useMenu();
  const listRef = useRef<HTMLDivElement>(null);

  // Focus the first item as the menu opens, so the keyboard works at once.
  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true });
  }, [open]);

  if (!open) return null;

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const items = Array.from(
      listRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])') ?? [],
    );
    if (items.length === 0) return;
    const current = items.indexOf(document.activeElement as HTMLElement);
    let next = -1;
    if (event.key === "ArrowDown") next = (current + 1) % items.length;
    else if (event.key === "ArrowUp") next = (current - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    if (next >= 0) {
      event.preventDefault();
      items[next].focus({ preventScroll: true });
    }
  }

  return (
    <div
      ref={listRef}
      id={listId}
      role="menu"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn(
        "absolute z-[60] min-w-[200px] rounded-lg border border-[var(--ci-ink-14)] bg-surface p-1.5 text-gray-900 shadow-[0_12px_32px_rgba(10,20,40,0.22)]",
        PLACEMENT[placement],
        align === "end" ? "right-0" : "left-0",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Non-interactive heading inside a menu (e.g. who is signed in). */
export function MenuHeader({ children }: { children: ReactNode }) {
  return <div className="mb-1 border-b border-[var(--ci-ink-14)] px-2.5 pb-2.5 pt-2">{children}</div>;
}

export function MenuItem({
  children,
  icon,
  hint,
  onSelect,
  href,
  className,
}: {
  children: ReactNode;
  icon?: ReactNode;
  /** A keyboard shortcut shown at the right edge. */
  hint?: string;
  onSelect?: () => void;
  /** Go to this route when chosen. */
  href?: string;
  className?: string;
}) {
  const { close } = useMenu();
  const router = useRouter();

  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={-1}
      onClick={() => {
        onSelect?.();
        close();
        if (href) router.push(href);
      }}
      className={cn(
        "flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-left text-[13.5px] font-medium text-gray-900 hover:bg-[var(--ci-ink-08)] focus-visible:bg-[var(--ci-ink-08)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ci-seal)]",
        className,
      )}
    >
      {icon && <span className="flex-shrink-0 text-gray-500">{icon}</span>}
      <span className="flex-1">{children}</span>
      {hint && (
        <kbd className="rounded-sm border border-[var(--ci-ink-14)] bg-page px-1.5 py-px font-mono text-[11px] text-gray-500">
          {hint}
        </kbd>
      )}
    </button>
  );
}
