"use client";

import { useRef, useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExpandDialog } from "@/components/ui/expand-dialog";
import { cn } from "@/lib/utils";

export interface ExpandedContext {
  /** True when rendering inside the dialog, false on the card itself. */
  expanded: boolean;
  /** The dialog is open (the card behind it is still mounted). */
  isOpen: boolean;
  /** The dialog's search text; always "" on the card. */
  query: string;
}

interface ExpandableCardProps {
  id?: string;
  /** Plain text: names the card's buttons and the dialog. */
  title: string;
  icon?: ReactNode;
  /** Beside the title on the card only (e.g. "3 open"). */
  titleExtra?: ReactNode;
  /** Total items. Shown in the dialog header, and drives its search box. */
  count?: number;
  /** The card's primary actions: in the card header and in the dialog's. */
  actions?: ReactNode;
  /** Replaces `actions` in the dialog header, when its rows already carry
   * their own (pass null for none). */
  dialogActions?: ReactNode;
  /** "View all (n)" under the preview while more items exist than shown. */
  viewAll?: { total: number; shown: number };
  /** Hide the expand button when there is nothing more to see. */
  expandable?: boolean;
  /** Controlled open state, for callers that open the dialog themselves
   * (a calendar day's "+n more"). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  bodyClassName?: string;
  /** Rendered twice -- on the card (preview) and in the dialog (full list) --
   * so both read the same data and hooks and stay in sync. */
  children: (context: ExpandedContext) => ReactNode;
}

/** A case-page card that shows only its recent or important items and
 * expands into a dialog with all of them. Cards never fold. */
export function ExpandableCard({
  id,
  title,
  icon,
  titleExtra,
  count,
  actions,
  dialogActions,
  viewAll,
  expandable = true,
  open,
  onOpenChange,
  className,
  bodyClassName,
  children,
}: ExpandableCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const expandRef = useRef<HTMLButtonElement>(null);
  // Whatever opened the dialog gets focus back: normally the expand button,
  // or the "View all" link.
  const openerRef = useRef<HTMLElement | null>(null);
  const [innerOpen, setInnerOpen] = useState(false);
  const [query, setQuery] = useState("");
  const isOpen = open ?? innerOpen;

  const setOpen = (next: boolean, opener?: HTMLElement | null) => {
    if (next) openerRef.current = opener ?? expandRef.current;
    if (!next) setQuery("");
    onOpenChange?.(next);
    if (open === undefined) setInnerOpen(next);
  };

  const hasMore = !!viewAll && viewAll.total > viewAll.shown;

  return (
    <div id={id} ref={cardRef} className={cn("scroll-mt-4", className)}>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle className="flex min-w-0 items-center gap-2">
            {icon}
            {title}
            {titleExtra}
          </CardTitle>
          <div className="flex items-center gap-2">
            {actions}
            {expandable && (
              <button
                ref={expandRef}
                type="button"
                onClick={() => setOpen(true)}
                aria-label={`Expand ${title}`}
                title={`Expand ${title}`}
                className="flex h-11 w-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900 md:h-8 md:w-8"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent className={bodyClassName}>
          {children({ expanded: false, isOpen, query: "" })}
        </CardContent>
        {hasMore && (
          <div className="border-t border-gray-100 px-5 py-2.5">
            <button
              type="button"
              onClick={(event) => setOpen(true, event.currentTarget)}
              className="text-sm font-medium text-gray-700 underline-offset-2 hover:text-gray-900 hover:underline"
            >
              View all ({viewAll.total})
            </button>
          </div>
        )}
      </Card>

      <ExpandDialog
        isOpen={isOpen}
        onClose={() => setOpen(false)}
        label={title}
        title={
          <>
            {icon}
            {title}
          </>
        }
        count={count}
        actions={dialogActions === undefined ? actions : dialogActions}
        search={{ value: query, onChange: setQuery }}
        originRef={cardRef}
        returnFocusRef={openerRef}
      >
        <div className={bodyClassName}>{children({ expanded: true, isOpen, query })}</div>
      </ExpandDialog>
    </div>
  );
}
