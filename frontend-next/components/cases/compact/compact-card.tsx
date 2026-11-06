"use client";

import { useRef, useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { EmbeddedCardContext } from "@/components/ui/expandable-card";
import { ExpandDialog } from "@/components/ui/expand-dialog";
import { cn } from "@/lib/utils";

/** What a compact card shows in its dialog. */
export interface CompactDialog {
  /** Defaults to the card's title. */
  title?: string;
  count?: number;
  /** The primary action (Add hearing, Upload, Add event). */
  actions?: ReactNode;
  /** Filter chips and a search box, under the header. */
  toolbar?: ReactNode;
  /** A one-line hint under the body. */
  footer?: ReactNode;
  /** The body. Existing cards placed here draw their expanded form and drop
   * their own frame (EmbeddedCardContext). */
  children: ReactNode;
}

interface CompactCardProps {
  id?: string;
  title: string;
  icon?: ReactNode;
  count?: number;
  /** Small text beside the title (a date). */
  titleExtra?: ReactNode;
  /** Buttons in the header, left of the expand button. */
  actions?: ReactNode;
  /** A "View all N" button in the header that opens the same dialog. */
  viewAll?: number;
  dialog?: CompactDialog;
  /** Controlled open state, for callers that open the dialog elsewhere (a
   * "Details" action on a row, a sync status in the page header). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

/** A case-page card: a 44px header (icon, title, count, actions, expand) over a
 * body that shows only as many rows as the window has room for. Everything
 * else is behind the expand button, in a dialog; Esc closes it and focus goes
 * back to the button that opened it. */
export function CompactCard({
  id,
  title,
  icon,
  count,
  titleExtra,
  actions,
  viewAll,
  dialog,
  open,
  onOpenChange,
  className,
  bodyClassName,
  children,
}: CompactCardProps) {
  const expandRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const [innerOpen, setInnerOpen] = useState(false);
  const isOpen = open ?? innerOpen;

  const setOpen = (next: boolean, opener?: HTMLElement | null) => {
    if (next) openerRef.current = opener ?? expandRef.current;
    onOpenChange?.(next);
    if (open === undefined) setInnerOpen(next);
  };

  return (
    <section
      id={id}
      aria-label={title}
      className={cn("ci-card flex min-h-0 min-w-0 flex-col overflow-hidden", className)}
    >
      {/* On a phone the header may take two lines: the title row, then the
          buttons wrap beneath (right-aligned) instead of squeezing the title
          down to "Ord...". From md up it is the single 44px row it was. */}
      <header className="flex h-11 flex-shrink-0 items-center gap-2 border-b border-gray-100 px-4 max-md:h-auto max-md:min-h-[48px] max-md:flex-wrap max-md:gap-y-1.5 max-md:py-1.5">
        {icon && <span className="flex-shrink-0 text-gray-600">{icon}</span>}
        <h2 className="min-w-0 truncate font-serif text-[15px] font-bold text-gray-900 max-md:flex-shrink-0 max-md:text-[16px]">{title}</h2>
        {count !== undefined && <span className="ci-chip ci-chip--none flex-shrink-0">{count}</span>}
        {titleExtra && <span className="flex-shrink-0 font-serif text-xs text-gray-500">{titleExtra}</span>}
        <div className="ml-auto flex flex-shrink-0 items-center gap-1.5 max-md:flex-wrap max-md:justify-end">
          {viewAll !== undefined && dialog && (
            <button
              type="button"
              onClick={(event) => setOpen(true, event.currentTarget)}
              className="inline-flex h-7 items-center rounded border border-[var(--ci-ink-14)] bg-surface px-2.5 text-xs font-semibold text-gray-900 hover:border-[var(--ci-ink)] max-md:h-10 max-md:px-3.5"
            >
              View all {viewAll}
            </button>
          )}
          {actions}
          {dialog && (
            <button
              ref={expandRef}
              type="button"
              onClick={() => setOpen(true)}
              aria-label={`Expand ${title}`}
              title={`Expand ${title}`}
              className="flex h-7 w-7 items-center justify-center rounded border border-[var(--ci-ink-14)] text-gray-600 hover:border-[var(--ci-ink)] hover:text-gray-900 max-md:h-10 max-md:w-10"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </header>
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>

      {dialog && (
        <>
          <ExpandDialog
            rise
            isOpen={isOpen}
            onClose={() => setOpen(false)}
            label={dialog.title ?? title}
            title={
              <>
                {icon}
                {dialog.title ?? title}
              </>
            }
            count={dialog.count ?? count}
            actions={dialog.actions}
            toolbar={dialog.toolbar}
            footer={dialog.footer}
            returnFocusRef={openerRef}
          >
            <EmbeddedCardContext.Provider value>{dialog.children}</EmbeddedCardContext.Provider>
          </ExpandDialog>
        </>
      )}
    </section>
  );
}

/** A dialog with no card of its own (Court tracking, Case details), opened
 * from the header or the facts strip. */
export function PageDialog({
  isOpen,
  onClose,
  title,
  icon,
  returnFocusRef,
  footer,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  icon?: ReactNode;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  footer?: ReactNode;
  children: ReactNode;
}) {
  return (
    <ExpandDialog
      rise
      isOpen={isOpen}
      onClose={onClose}
      label={title}
      title={
        <>
          {icon}
          {title}
        </>
      }
      footer={footer}
      returnFocusRef={returnFocusRef}
    >
      <EmbeddedCardContext.Provider value>{children}</EmbeddedCardContext.Provider>
    </ExpandDialog>
  );
}
