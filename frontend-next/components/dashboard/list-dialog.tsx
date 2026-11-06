"use client";

import { useState, type ReactNode, type RefObject } from "react";
import { ExpandDialog } from "@/components/ui/expand-dialog";

/** The shared centred dialog for "N more" lists on the dashboard: it grows
 * from the section it belongs to, closes on Esc or a click outside, traps
 * focus and gives it back to the button that opened it. A search box shows
 * once the list is longer than eight (ExpandDialog's own rule). */
export function ListDialog({
  isOpen,
  onClose,
  label,
  count,
  originRef,
  returnFocusRef,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  label: string;
  /** Items listed; omit for a dialog that is not a list. */
  count?: number;
  originRef?: RefObject<HTMLElement | null>;
  returnFocusRef?: RefObject<HTMLElement | null>;
  children: (query: string) => ReactNode;
}) {
  const [query, setQuery] = useState("");
  return (
    <ExpandDialog
      isOpen={isOpen}
      onClose={() => {
        setQuery("");
        onClose();
      }}
      label={label}
      title={label}
      count={count}
      search={{ value: query, onChange: setQuery }}
      originRef={originRef}
      returnFocusRef={returnFocusRef}
    >
      {children(query)}
    </ExpandDialog>
  );
}
