import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface CollapsibleProps {
  isOpen: boolean;
  children: ReactNode;
  className?: string;
}

/** Animates a section's height between 0 and its natural content height via
 * a CSS grid-rows transition -- content stays mounted (no need to know its
 * pixel height up front, unlike a max-height trick), it just collapses to
 * zero rows and clips through the inner overflow-hidden wrapper. Pairs with
 * `CollapseToggle` everywhere a section can be expanded/collapsed. */
export function Collapsible({ isOpen, children, className }: CollapsibleProps) {
  return (
    <div
      className={cn(
        "grid transition-[grid-template-rows] duration-300 ease-out motion-reduce:transition-none",
        isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        className,
      )}
    >
      <div className="overflow-hidden min-h-0">{children}</div>
    </div>
  );
}
