"use client";

import { type CSSProperties, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import { usePersistedOpen } from "@/hooks/use-persisted-open";
import { dateTile } from "@/lib/mobile-format";
import { cn, staggerDelay } from "@/lib/utils";

/** Small building blocks the phone layouts share. Motion is transform +
 * opacity (height via grid rows), and every animated class carries a
 * motion-reduce twin. */

/** Height + fade open/close: a grid-rows transition, so no pixel height is
 * needed and only the clip box changes size. Collapsed content is inert
 * (not focusable, not read out). */
export function Reveal({ open, children, className }: { open: boolean; children: ReactNode; className?: string }) {
  return (
    <div
      inert={!open}
      // `visibility` flips at the end of the close (and at the start of the
      // open), so folded content is also gone for screen readers and finds.
      style={{
        transition: open
          ? "grid-template-rows 300ms ease-out, opacity 300ms ease-out, visibility 0s linear 0s"
          : "grid-template-rows 300ms ease-out, opacity 300ms ease-out, visibility 0s linear 300ms",
      }}
      className={cn(
        "grid motion-reduce:transition-none",
        open ? "visible grid-rows-[1fr] opacity-100" : "invisible grid-rows-[0fr] opacity-0",
        className,
      )}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

/** A titled section the reader can fold away; whether it is folded is
 * remembered (localStorage, per `id`) so the page opens the way it was left. */
export function MSection({
  id,
  title,
  count,
  defaultOpen = true,
  action,
  children,
  className,
}: {
  id: string;
  title: string;
  count?: number;
  defaultOpen?: boolean;
  /** Small control beside the title (it does not toggle the section). */
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, toggle] = usePersistedOpen(`section:${id}`, defaultOpen);
  const panelId = `${id}-panel`;
  return (
    <section id={id} aria-label={title} className={cn("scroll-mt-[calc(var(--mobile-header-h)+8px)]", className)}>
      <div className="flex items-center">
        <h2 className="min-w-0 flex-1 !text-[17px] !font-bold">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => toggle()}
            className="flex min-h-[48px] w-full items-center gap-2 px-1 text-left font-serif [--press-scale:0.99]"
          >
            <span className="truncate text-gray-900">{title}</span>
            {count !== undefined && (
              <span key={count} className="ci-chip ci-chip--none flex-shrink-0 animate-settle motion-reduce:animate-none">
                {count}
              </span>
            )}
            <ChevronDown
              aria-hidden="true"
              className={cn(
                "ml-auto h-4 w-4 flex-shrink-0 text-gray-500 transition-transform duration-300 motion-reduce:transition-none",
                open && "rotate-180",
              )}
            />
          </button>
        </h2>
        {action}
      </div>
      <Reveal open={open}>
        <div id={panelId}>{children}</div>
      </Reveal>
    </section>
  );
}

/** FRI / 6 / NOV, as a small calendar leaf. `tone` colours the leaf; it
 * settles in (a small scale overshoot), staggered by `index`. */
export function DateTile({
  day,
  tone = "none",
  index = 0,
  className,
}: {
  day: string;
  tone?: "alert" | "pending" | "ok" | "none" | "ink";
  index?: number;
  className?: string;
}) {
  const t = dateTile(day);
  const palette: Record<string, string> = {
    ink: "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]",
    alert: "border-[var(--ci-seal)] bg-[var(--ci-seal-soft)] text-[color:var(--ci-seal)]",
    pending: "border-[var(--ci-warn)] bg-[var(--ci-warn-soft)] text-[color:var(--ci-warn)]",
    ok: "border-[var(--ci-listed)] bg-[var(--ci-listed-soft)] text-[color:var(--ci-listed)]",
    none: "border-[var(--ci-ink-14)] bg-surface text-gray-900",
  };
  return (
    <div
      aria-hidden="true"
      style={staggerDelay(index, 40)}
      className={cn(
        "flex h-[56px] w-[48px] flex-shrink-0 animate-pop-in flex-col items-center justify-center rounded-[3px] border motion-reduce:animate-none",
        palette[tone],
        className,
      )}
    >
      <span className="font-mono text-[9px] leading-none tracking-[0.14em] opacity-80">{t.weekday}</span>
      <span className="font-serif text-[23px] font-bold leading-[1.05] tabular-nums">{t.date}</span>
      <span className="font-mono text-[9px] leading-none tracking-[0.14em] opacity-80">{t.month}</span>
    </div>
  );
}

/** A success check: a green disc pops in with a ring that spreads and fades. */
export function AnimatedCheck({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex h-7 w-7 items-center justify-center", className)} aria-hidden="true">
      <span className="absolute inset-0 animate-ring-out rounded-full bg-[var(--ci-listed)] motion-reduce:animate-none" />
      <span className="relative flex h-7 w-7 animate-pop-in items-center justify-center rounded-full bg-[var(--ci-listed)] text-white motion-reduce:animate-none">
        <Check className="h-4 w-4" strokeWidth={3} />
      </span>
    </span>
  );
}

/** A list item entering: lifts and fades in, `index` steps behind the one above. */
export function riseIn(index: number): { className: string; style: CSSProperties } {
  return { className: "animate-rise-in motion-reduce:animate-none", style: staggerDelay(index, 45, 12) };
}
