"use client";

import { useRef, useState } from "react";
import { Search } from "lucide-react";
import { AddTaskDialog } from "@/components/dashboard/add-task-dialog";
import { CasePeek } from "@/components/dashboard/case-peek";
import { ListDialog } from "@/components/dashboard/list-dialog";
import { STATUS_COLOR, StatusSwatch } from "@/components/dashboard/status";
import { dayMonth } from "@/lib/dashboard/dates";
import {
  STATUS_LABEL,
  STATUS_ORDER,
  caseMatches,
  firstParty,
  insightSegments,
  type DashboardModel,
  type PracticeCase,
  type PracticeStatus,
} from "@/lib/dashboard/model";
import { SegText } from "@/components/dashboard/seg-text";
import { cn } from "@/lib/utils";

const TILE_TONE: Record<"today" | "attn" | "week", string> = {
  today: "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]",
  attn: "border-[color-mix(in_srgb,var(--ci-seal)_30%,white)] bg-[color-mix(in_srgb,var(--ci-seal)_12%,white)] text-gray-900",
  week: "border-[color-mix(in_srgb,var(--ci-warn)_30%,white)] bg-[var(--ci-warn-soft)] text-gray-900",
};
const REASON_TONE: Record<"today" | "attn" | "week", string> = {
  today: "text-[color:var(--ci-on-field-dim)]",
  attn: "font-semibold text-[color:var(--ci-seal)]",
  week: "font-semibold text-[color:var(--ci-warn)]",
};

/** Every active case on one page, grouped by court. Cases that need a look
 * are tiles with the reason in words; the quiet ones are small squares, so
 * a hundred and fifty cases still fit. Click a legend chip to filter, type
 * to find a case, click a case to see it on the right. */
export function PracticeMap({ model }: { model: DashboardModel }) {
  const [filter, setFilter] = useState<PracticeStatus | null>(null);
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(model.defaultSelectedId);
  const [peekOpen, setPeekOpen] = useState(false);
  const [taskCaseId, setTaskCaseId] = useState<number | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  const selected =
    model.practice.find((c) => c.id === selectedId) ??
    model.practice.find((c) => c.id === model.defaultSelectedId) ??
    null;

  function pick(c: PracticeCase, trigger: HTMLElement) {
    setSelectedId(c.id);
    // Below the width where the right panel fits it is hidden (display:none),
    // so the same peek opens in the shared dialog instead.
    if (panelRef.current && panelRef.current.getClientRects().length === 0) {
      openerRef.current = trigger;
      setPeekOpen(true);
    }
  }

  const dimmed = (c: PracticeCase) =>
    (filter !== null && c.status !== filter) || (query.trim() !== "" && !caseMatches(c, query));

  if (model.practice.length === 0) {
    return <p className="text-sm text-gray-500">No cases yet. Add one from the New menu.</p>;
  }

  const taskCase = model.practice.find((c) => c.id === taskCaseId);

  return (
    <div className="grid items-start gap-5 @[1300px]:grid-cols-[minmax(0,1fr)_390px]">
      <div ref={mapRef} className="min-w-0">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <label className="relative">
            <span className="sr-only">Find a case</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" strokeWidth={1.8} />
            <input
              type="search"
              placeholder="Find a case by party, number or court"
              aria-label="Find a case"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-10 w-[300px] max-w-full rounded border border-gray-200 bg-surface pl-9 pr-3 text-[13.5px] text-gray-900 outline-none placeholder:text-gray-400 focus:border-[var(--ci-ink)] md:h-9"
            />
          </label>
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={filter === s}
              onClick={() => setFilter(filter === s ? null : s)}
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-full border px-3.5 text-[12.5px] font-semibold md:h-9",
                filter === s
                  ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                  : "border-gray-200 bg-surface text-gray-900 hover:border-[var(--ci-ink)]",
              )}
            >
              <StatusSwatch status={s} className="h-3 w-3" />
              {STATUS_LABEL[s]}
              <b className={filter === s ? "text-[color:var(--ci-on-field-dim)]" : "text-gray-600"}>{model.counts[s]}</b>
            </button>
          ))}
        </div>

        <div>
          {model.bands.map((band) => (
            <section
              key={band.court}
              aria-label={band.court}
              className="grid gap-3 border-t border-gray-200 py-4 @[700px]:grid-cols-[190px_minmax(0,1fr)] @[700px]:gap-5"
            >
              <div>
                <h3 className="font-serif text-[17px] font-bold leading-tight text-gray-900">{band.court}</h3>
                <span className="text-[12.5px] text-gray-600">
                  {band.cases.length} {band.cases.length === 1 ? "case" : "cases"} · {band.needLook} need a look
                </span>
              </div>
              <div className="min-w-0">
                {band.tiles.length > 0 && (
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
                    {band.tiles.map((c) => {
                      const tone = c.status as "today" | "attn" | "week";
                      return (
                        <button
                          key={c.id}
                          type="button"
                          data-status={c.status}
                          aria-pressed={c.id === selected?.id}
                          aria-label={`${c.title}, ${c.number}, ${c.reason}`}
                          onClick={(e) => pick(c, e.currentTarget)}
                          className={cn(
                            "flex h-[62px] min-w-0 flex-col items-start gap-px rounded border px-2.5 py-2 text-left transition-opacity",
                            TILE_TONE[tone],
                            c.id === selected?.id && "outline outline-2 outline-offset-2 outline-[var(--ci-ink)]",
                            dimmed(c) && "opacity-[0.16]",
                          )}
                        >
                          <small className="max-w-full truncate font-mono text-[10px] tracking-[0.03em] opacity-75">{c.number}</small>
                          <b className="max-w-full truncate text-[13px] font-bold">{firstParty(c.title)}</b>
                          <span className={cn("max-w-full truncate text-[11.5px]", REASON_TONE[tone])}>{c.reason}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
                {band.squares.length > 0 && (
                  <>
                    <p className="mb-1.5 mt-3 font-mono text-[10.5px] uppercase tracking-[0.1em] text-gray-500">
                      {band.newDates > 0 ? `${band.newDates} new ${band.newDates === 1 ? "date" : "dates"} from eCourts (blue) · ` : ""}
                      {band.quiet} quiet
                    </p>
                    <div className="flex flex-wrap gap-[5px]">
                      {band.squares.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          data-status={c.status}
                          aria-pressed={c.id === selected?.id}
                          title={`${c.title}${c.newDate ? ` · new date ${dayMonth(c.newDate)}` : ""}`}
                          aria-label={`${c.title}, ${c.number}, ${c.reason}`}
                          onClick={(e) => pick(c, e.currentTarget)}
                          className={cn(
                            "h-4 w-4 rounded-[3px] ring-1 ring-inset ring-[var(--ci-ink-14)] transition-opacity hover:ring-[var(--ci-ink)]",
                            c.id === selected?.id && "outline outline-2 outline-offset-2 outline-[var(--ci-ink)]",
                            dimmed(c) && "opacity-[0.16]",
                          )}
                          style={{ background: STATUS_COLOR[c.status] }}
                        />
                      ))}
                    </div>
                  </>
                )}
              </div>
            </section>
          ))}
        </div>
      </div>

      <aside
        ref={panelRef}
        aria-label="Case details"
        className="ci-card hidden flex-col @[1300px]:sticky @[1300px]:top-4 @[1300px]:flex"
      >
        {model.insights.length > 0 && (
          <section className="border-b border-gray-100 px-5 pb-2 pt-4">
            <h4 className="mb-1 font-mono text-[11px] uppercase tracking-[0.1em] text-gray-500">Heads up</h4>
            <ul>
              {model.insights.map((insight, i) => (
                <li key={i} className="border-t border-dashed border-gray-200 py-2 text-[13px] leading-snug text-gray-900 first:border-0">
                  <SegText segs={insightSegments(insight)} />
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="p-5">
          {selected && <CasePeek item={selected} model={model} onAddTask={setTaskCaseId} />}
        </div>
      </aside>

      <ListDialog
        isOpen={peekOpen && selected !== null}
        onClose={() => setPeekOpen(false)}
        label={selected?.title ?? "Case"}
        originRef={mapRef}
        returnFocusRef={openerRef}
      >
        {() => selected && <CasePeek item={selected} model={model} onAddTask={setTaskCaseId} />}
      </ListDialog>

      <AddTaskDialog
        caseId={taskCaseId}
        caseTitle={taskCase?.title ?? ""}
        onClose={() => setTaskCaseId(null)}
      />
    </div>
  );
}
