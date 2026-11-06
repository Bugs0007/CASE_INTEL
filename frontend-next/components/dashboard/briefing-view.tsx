"use client";

import { useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import { GlanceColumn, type BillingState } from "@/components/dashboard/glance-column";
import { ListDialog } from "@/components/dashboard/list-dialog";
import { PortfolioBotSlot } from "@/components/dashboard/portfolio-bot-slot";
import { MINI_BUTTON_DARK, MINI_BUTTON_LIGHT, SegText } from "@/components/dashboard/seg-text";
import { CauseChipView } from "@/components/dashboard/status";
import { dateLabel, shortDay } from "@/lib/dashboard/dates";
import {
  causeChip,
  comingUpSegments,
  needSegments,
  type DashboardModel,
  type NeedItem,
  type Seg,
} from "@/lib/dashboard/model";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";
import { matchesQuery } from "@/lib/case-previews";

const TODAY_SHOWN = 3;
const NEEDS_SHOWN = 3;

type OpenDialog = "today" | "since" | "needs" | null;

function Section({
  label,
  children,
  sectionRef,
}: {
  label: string;
  children: ReactNode;
  sectionRef?: React.RefObject<HTMLElement | null>;
}) {
  return (
    <section ref={sectionRef} className="border-t border-gray-100 pb-2 pt-[18px]">
      <h3 className="mb-3 font-mono text-[11px] font-medium uppercase tracking-[0.12em] text-gray-500">{label}</h3>
      <div className="max-w-[800px] font-serif text-[16.5px] leading-[1.65] text-gray-900">{children}</div>
    </section>
  );
}

/** A pill that opens a list: "3 more today", "13 cases", "See all 5". */
function PillButton({
  onClick,
  buttonRef,
  children,
}: {
  onClick: () => void;
  buttonRef: React.RefObject<HTMLButtonElement | null>;
  children: ReactNode;
}) {
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={onClick}
      className="inline-flex h-7 items-center gap-1 rounded-full border border-gray-200 bg-page px-3 align-middle font-sans text-[12.5px] font-semibold text-gray-900 hover:border-[var(--ci-ink)]"
    >
      {children}
    </button>
  );
}

function NeedAction({
  item,
  primary,
  completing,
  onComplete,
}: {
  item: NeedItem;
  primary: boolean;
  completing: boolean;
  onComplete: (taskId: number) => void;
}) {
  const cls = primary ? MINI_BUTTON_DARK : MINI_BUTTON_LIGHT;
  switch (item.kind) {
    case "task":
      return (
        <button
          type="button"
          className={cls}
          disabled={completing}
          aria-label={`Mark done: ${item.text}`}
          onClick={() => item.taskId !== undefined && onComplete(item.taskId)}
        >
          Mark done
        </button>
      );
    case "draft":
      return (
        <Link href="/messages" className={cls}>
          Review draft
        </Link>
      );
    case "unbilled":
      return (
        <Link href="/billing" className={cls}>
          Open billing
        </Link>
      );
    default:
      return item.caseId ? (
        <Link href={`/cases/${item.caseId}`} className={cls}>
          Open case
        </Link>
      ) : (
        <Link href="/documents" className={cls}>
          Open documents
        </Link>
      );
  }
}

export interface BriefingViewProps {
  model: DashboardModel;
  /** "Good morning, Bhagath." */
  greeting: string;
  billing: BillingState;
  completingTaskId?: number;
  onCompleteTask: (taskId: number) => void;
  onOpenMap: () => void;
}

/** The Briefing: today, what changed, what needs you and what is coming,
 * as sentences -- every one of them built from the loaded data by
 * lib/dashboard/model.ts. A Glance column sits beside it on a wide screen
 * and under it on a narrow one (a container query on the main area). */
export function BriefingView({
  model,
  greeting,
  billing,
  completingTaskId,
  onCompleteTask,
  onOpenMap,
}: BriefingViewProps) {
  const [dialog, setDialog] = useState<OpenDialog>(null);
  const todayRef = useRef<HTMLElement | null>(null);
  const sinceRef = useRef<HTMLElement | null>(null);
  const needsRef = useRef<HTMLElement | null>(null);
  const todayBtn = useRef<HTMLButtonElement | null>(null);
  const sinceBtn = useRef<HTMLButtonElement | null>(null);
  const needsBtn = useRef<HTMLButtonElement | null>(null);

  const { todays, since, needs, today } = model;
  const close = () => setDialog(null);

  return (
    <div className="grid items-start gap-5 @[1000px]:grid-cols-[minmax(0,1fr)_360px]">
      <Card className="min-w-0 px-5 pb-4 pt-6 @[1000px]:px-11 @[1000px]:pt-8">
        <h2 className="font-serif text-[30px] font-bold leading-[1.1] tracking-tight text-gray-900 @[1000px]:text-[34px]">
          {greeting}
        </h2>
        <p className="mb-6 mt-2.5 max-w-[780px] font-serif text-[20px] leading-[1.4] text-gray-600 @[1000px]:text-[22px]">
          {model.lead}
        </p>

        <Section label="Today" sectionRef={todayRef}>
          {todays.length === 0 ? (
            <p>Nothing is in court today.</p>
          ) : (
            <>
              <ul className="flex flex-col gap-3.5">
                {todays.slice(0, TODAY_SHOWN).map((row) => (
                  <li key={row.hearing.id}>
                    <SegText segs={row.segments} />
                    <Link
                      href={`/cases/${row.hearing.caseId}`}
                      className={`${MINI_BUTTON_LIGHT} ml-2 align-middle font-sans`}
                    >
                      Open case
                    </Link>
                  </li>
                ))}
              </ul>
              {todays.length > TODAY_SHOWN && (
                <p className="mt-3">
                  <PillButton buttonRef={todayBtn} onClick={() => setDialog("today")}>
                    <b>{todays.length - TODAY_SHOWN}</b> more today
                  </PillButton>
                </p>
              )}
            </>
          )}
        </Section>

        <Section label="Since your last visit" sectionRef={sinceRef}>
          {since.count === 0 ? (
            <p>Nothing has changed since your last visit.</p>
          ) : (
            <p>
              eCourts moved{" "}
              <PillButton buttonRef={sinceBtn} onClick={() => setDialog("since")}>
                <b>{since.count}</b> {since.count === 1 ? "case" : "cases"}
              </PillButton>{" "}
              to {since.count === 1 ? "a new date" : "new dates"},{" "}
              {since.count === 1 ? "on" : "the earliest on"}{" "}
              {since.earliest ? dateLabelInline(since.earliest, today) : "an unknown date"}.{" "}
              {since.clash ? (
                <span className="rounded-[3px] bg-[var(--ci-warn-soft)] px-1.5 py-px text-[color:var(--ci-warn)]">
                  {shortDay(since.clash.day)} now has hearings in {since.clash.courts} different courts, so one of
                  them may need a request to move.
                </span>
              ) : (
                "None of the new dates clash with another court."
              )}
            </p>
          )}
        </Section>

        <Section label="Needs you" sectionRef={needsRef}>
          {needs.length === 0 ? (
            <p>Nothing is waiting on you.</p>
          ) : (
            <>
              <ol className="flex flex-col gap-3.5">
                {needs.slice(0, NEEDS_SHOWN).map((item, i) => (
                  <li key={item.key} className="flex items-baseline gap-3.5">
                    <b className="flex-none font-mono text-[13px] font-semibold text-gray-500">{i + 1}</b>
                    <span>
                      <SegText segs={needSegments(item, today)} />
                      <span className="ml-2 inline-flex align-middle font-sans">
                        <NeedAction
                          item={item}
                          primary={i === 0}
                          completing={completingTaskId === item.taskId}
                          onComplete={onCompleteTask}
                        />
                      </span>
                    </span>
                  </li>
                ))}
              </ol>
              {needs.length > NEEDS_SHOWN && (
                <p className="mt-3">
                  <PillButton buttonRef={needsBtn} onClick={() => setDialog("needs")}>
                    See all <b>{needs.length}</b>
                  </PillButton>
                </p>
              )}
            </>
          )}
        </Section>

        <Section label="Coming up">
          <p>
            <SegText segs={comingUpSegments(model.comingUp, today)} />
          </p>
        </Section>
      </Card>

      <div className="flex min-w-0 flex-col gap-4">
        <GlanceColumn model={model} billing={billing} onOpenMap={onOpenMap} />
        {PORTFOLIO_BOT_ENABLED && <PortfolioBotSlot />}
      </div>

      <ListDialog
        isOpen={dialog === "today"}
        onClose={close}
        label="Today's hearings"
        count={todays.length}
        originRef={todayRef}
        returnFocusRef={todayBtn}
      >
        {(query) => (
          <ul className="divide-y divide-gray-100">
            {todays
              .filter((r) => matchesQuery(query, r.hearing.caseTitle, r.number, r.hearing.court))
              .map(({ hearing, number }) => (
                <li key={hearing.id} className="flex items-center gap-3 py-3">
                  <div className="w-12 flex-none text-center">
                    <b className="block font-serif text-lg leading-none">{hearing.item || "–"}</b>
                    <span className="font-mono text-[10px] uppercase text-gray-500">item</span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <Link href={`/cases/${hearing.caseId}`} className="block truncate text-sm font-semibold text-gray-900 hover:underline">
                      {hearing.caseTitle}
                    </Link>
                    <span className="block truncate text-xs text-gray-500">
                      {[hearing.court || "Court not recorded", number].filter(Boolean).join(" · ")}
                    </span>
                  </div>
                  <CauseChipView chip={causeChip(hearing)} />
                </li>
              ))}
          </ul>
        )}
      </ListDialog>

      <ListDialog
        isOpen={dialog === "since"}
        onClose={close}
        label="Cases with a new date"
        count={model.changedCases.length}
        originRef={sinceRef}
        returnFocusRef={sinceBtn}
      >
        {(query) => (
          <ul className="divide-y divide-gray-100">
            {model.changedCases
              .filter((c) => matchesQuery(query, c.title, c.number))
              .map((c) => (
                <li key={c.caseId} className="flex items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <Link href={`/cases/${c.caseId}`} className="block truncate text-sm font-semibold text-gray-900 hover:underline">
                      {c.title}
                    </Link>
                    <span className="block truncate text-xs text-gray-500">
                      New date {shortDay(c.day)}
                      {c.number ? ` · ${c.number}` : ""}
                    </span>
                  </div>
                </li>
              ))}
          </ul>
        )}
      </ListDialog>

      <ListDialog
        isOpen={dialog === "needs"}
        onClose={close}
        label="Needs you"
        count={needs.length}
        originRef={needsRef}
        returnFocusRef={needsBtn}
      >
        {(query) => (
          <ul className="divide-y divide-gray-100">
            {needs
              .filter((n) => matchesQuery(query, n.caseTitle, n.text))
              .map((item) => (
                <li key={item.key} className="flex flex-wrap items-center gap-3 py-3 text-sm text-gray-900">
                  <span className="min-w-0 flex-1">
                    <SegText segs={needSegments(item, today) as Seg[]} />
                  </span>
                  <NeedAction
                    item={item}
                    primary={false}
                    completing={completingTaskId === item.taskId}
                    onComplete={onCompleteTask}
                  />
                </li>
              ))}
          </ul>
        )}
      </ListDialog>
    </div>
  );
}

/** "tomorrow" / "today" / "Fri 6 Nov", for the middle of a sentence. */
function dateLabelInline(day: string, today: string): string {
  const label = dateLabel(day, today);
  return label === "Today" || label === "Tomorrow" ? label.toLowerCase() : label;
}
