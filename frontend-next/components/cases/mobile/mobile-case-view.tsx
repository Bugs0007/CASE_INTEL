"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode, type TouchEvent } from "react";
import {
  Bot,
  ChevronRight,
  FileText,
  FilePlus2,
  Gavel,
  Loader2,
  Plus,
  RefreshCw,
  Upload,
  Users,
} from "lucide-react";
import { PriorityBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { showToast } from "@/components/ui/toaster";
import { DateTile, MSection, Reveal, riseIn } from "@/components/mobile/primitives";
import { useMobileHeader, MobileSubbar } from "@/components/layout/mobile-chrome";
import { CauseListBadge } from "@/components/hearings/cause-list-badge";
import { HearingItem } from "@/components/hearings/hearings-list";
import { HearingDigestDialog } from "@/components/hearings/hearing-digest-dialog";
import { HearingBusinessPreview, HearingBusinessSection } from "@/components/cases/hearing-business";
import { CompactCalendar, directionsOf } from "@/components/cases/compact/compact-main";
import {
  CompactClientUpdates,
  CompactDocuments,
  CompactFees,
  CompactTasks,
} from "@/components/cases/compact/compact-rail";
import { groupOrdersByDate, hearingDateKey } from "@/hooks/use-court-orders";
import { useRefreshTracking } from "@/hooks/use-case-tracking";
import { useHearingBusiness } from "@/hooks/use-hearing-business";
import { hearingDayKey } from "@/lib/calendar";
import { allHearingRows, caseFacts, filterHearingRows, syncState, type HearingFilter, type HearingRow, type SyncTone } from "@/lib/case-page-rows";
import { latestOrderForOverview } from "@/lib/case-previews";
import { dayMonth, istDayKey } from "@/lib/dashboard/dates";
import { caseDisplayTitle } from "@/lib/dashboard/adapt";
import { dateTile, dueUrgency, relativeDay } from "@/lib/mobile-format";
import { cn, hasPlaceholderTitle, staggerDelay } from "@/lib/utils";
import { usePersistedOpen } from "@/hooks/use-persisted-open";
import type { Case, CourtOrder, Document, Hearing } from "@/types";

const DOT: Record<SyncTone, string> = {
  ok: "bg-[var(--ci-listed)]",
  stale: "bg-[var(--ci-warn)]",
  failed: "bg-[var(--ci-seal)]",
  off: "bg-gray-400",
};

type TabId = "overview" | "hearings" | "docs" | "more";
const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "hearings", label: "Hearings" },
  { id: "docs", label: "Documents" },
  { id: "more", label: "Fees & more" },
];

export interface MobileCaseViewProps {
  caseItem: Case;
  caseId: number;
  hearings: Hearing[];
  hearingsLoading: boolean;
  orders: CourtOrder[];
  documents: Document[];
  docsLoading: boolean;
  latestDatedOrder: { id: number; order_date: string } | null;
  viewingOrderId?: number;
  onViewOrder: (orderId: number) => void;
  onAddHearing: () => void;
  onEditHearing: (hearing: Hearing) => void;
  onDeleteHearing: (id: number) => void;
  deletingHearingId?: number;
  onUpload: () => void;
  onGenerate: () => void;
  onViewDocument: (id: number) => void;
  onProcessDocument: (id: number) => void;
  onDeleteDocument: (id: number) => void;
  processPending: boolean;
  processingDocId?: number;
  onEditDetails: () => void;
  onOpenTracking: () => void;
  onOpenDetails: () => void;
  onOpenBot: () => void;
  /** The order-check line (Documents and Hearings). */
  statusLine: ReactNode;
  /** The daily-status card, mounted by the case page. */
  dailyStatusSlot?: ReactNode;
}

/** The case page on a phone. Instead of the desktop's screenful of cards it is
 * one column: who and what at the top (title in the top bar, status, the
 * facts that matter), then the NEXT HEARING as the first thing you see, a
 * slot for what happened last, quick actions, and four tabs that swap with
 * a slide (swipe left/right works too). The Case Bot is a button that
 * floats at the thumb. The dialogs underneath are the same as on desktop and
 * show as bottom sheets. */
export function MobileCaseView(props: MobileCaseViewProps) {
  const { caseItem } = props;
  const title = hasPlaceholderTitle(caseItem) ? "Untitled matter" : caseDisplayTitle(caseItem.title, caseItem.case_number);
  useMobileHeader(title, "/cases", "Back to cases", "Cases");

  const [tab, setTab] = useState<TabId>("overview");
  const [direction, setDirection] = useState<1 | -1>(1);
  const select = (next: TabId) => {
    if (next === tab) return;
    setDirection(TABS.findIndex((t) => t.id === next) > TABS.findIndex((t) => t.id === tab) ? 1 : -1);
    setTab(next);
    // The page starts at the top of the new tab, hero showing the facts.
    document.querySelector<HTMLElement>("[data-page-scroll]")?.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Swipe sideways over the tab content to move to the next/previous tab.
  const touch = useRef<{ x: number; y: number; ok: boolean } | null>(null);
  const onTouchStart = (e: TouchEvent) => {
    const t = e.touches[0];
    // Leave swipes that start inside a sideways-scrolling row alone.
    const inRow = (e.target as HTMLElement).closest(".ci-hscroll, [data-no-swipe]") !== null;
    touch.current = { x: t.clientX, y: t.clientY, ok: !inRow };
  };
  const onTouchEnd = (e: TouchEvent) => {
    const start = touch.current;
    touch.current = null;
    if (!start?.ok) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - start.x;
    const dy = t.clientY - start.y;
    if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 2) return;
    const index = TABS.findIndex((x) => x.id === tab);
    const next = TABS[index + (dx < 0 ? 1 : -1)];
    if (next) select(next.id);
  };

  return (
    <div data-testid="mobile-case" className="pb-28">
      {/* The tabs are pinned to the top of the screen, under the top bar. */}
      <MobileSubbar height={44}>
        <CaseTabs tab={tab} onSelect={select} />
      </MobileSubbar>

      {/* The summary (who, the next hearing, the facts) is the Overview's
          top; the other tabs start straight at their content, with the case
          title in the top bar above. */}
      {tab === "overview" && <Hero {...props} />}

      <div
        key={tab}
        role="tabpanel"
        id={`case-panel-${tab}`}
        aria-labelledby={`case-tab-${tab}`}
        onTouchStart={onTouchStart}
        onTouchEnd={onTouchEnd}
        className={cn(
          "px-4 pt-1 motion-reduce:animate-none",
          direction === 1 ? "animate-page-in" : "animate-page-in-reverse",
        )}
      >
        {tab === "overview" && <OverviewTab {...props} />}
        {tab === "hearings" && <HearingsTab {...props} />}
        {tab === "docs" && <DocsTab {...props} />}
        {tab === "more" && <MoreTab {...props} />}
      </div>

      <BotButton onClick={props.onOpenBot} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function CaseTabs({ tab, onSelect }: { tab: TabId; onSelect: (tab: TabId) => void }) {
  const refs = useRef<Partial<Record<TabId, HTMLButtonElement>>>({});
  const [mark, setMark] = useState<{ left: number; width: number } | null>(null);

  useEffect(() => {
    const el = refs.current[tab];
    if (!el) return;
    setMark({ left: el.offsetLeft, width: el.offsetWidth });
    el.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [tab]);

  return (
    <div role="tablist" aria-label="Case sections" className="ci-hscroll relative h-full items-stretch !gap-0 px-1">
      {TABS.map((t) => (
        <button
          key={t.id}
          ref={(el) => {
            if (el) refs.current[t.id] = el;
          }}
          id={`case-tab-${t.id}`}
          type="button"
          role="tab"
          aria-selected={tab === t.id}
          aria-controls={`case-panel-${t.id}`}
          onClick={() => onSelect(t.id)}
          className={cn("h-full px-4 text-[13.5px] font-semibold transition-colors", tab === t.id ? "text-gray-900" : "text-gray-500")}
        >
          {t.label}
        </button>
      ))}
      {mark && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-0 left-0 h-[3px] w-[100px] origin-left bg-[var(--ci-ink)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
          style={{ transform: `translateX(${mark.left}px) scaleX(${mark.width / 100})` }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero: who, the facts, the next hearing, what happened last, quick actions
// ---------------------------------------------------------------------------

function Hero(props: MobileCaseViewProps) {
  const { caseItem, hearings, onOpenTracking, onOpenDetails, onEditDetails } = props;
  const facts = caseFacts(caseItem);
  const sync = syncState(caseItem);
  const untitled = hasPlaceholderTitle(caseItem);
  const [detailsOpen, toggleDetails] = usePersistedOpen("case:facts", false);

  const factRows: [string, ReactNode][] = [
    ["Court", facts.court],
    ["Stage", facts.stage],
    [
      "Your side",
      facts.side || (
        <button type="button" onClick={onEditDetails} className="inline-flex min-h-[32px] items-center gap-1.5 font-semibold underline">
          <span className="ci-chip ci-chip--pending !no-underline">Not set</span> Set
        </button>
      ),
    ],
    ["Client", facts.client],
  ];

  return (
    <section aria-label="Case summary" className="px-4 pb-3 pt-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <StatusBadge status={caseItem.status} />
        <PriorityBadge priority={caseItem.priority} />
        <span className="font-mono text-[12px] text-gray-500">{caseItem.case_number}</span>
        {caseItem.disposal && (
          <button type="button" onClick={onOpenDetails} className="ci-chip ci-chip--pending min-h-[28px] cursor-pointer">
            Looks disposed
          </button>
        )}
      </div>

      <h1 className={cn("mt-1.5 !text-[24px] !font-bold !leading-[1.15]", untitled ? "text-gray-400" : "text-gray-900")}>
        {untitled ? "Untitled matter" : caseItem.title}
      </h1>
      {untitled && (
        <button type="button" onClick={onEditDetails} className="mt-1 min-h-[36px] text-[13px] font-semibold text-gray-700 underline">
          Add a title
        </button>
      )}

      <button
        type="button"
        onClick={onOpenTracking}
        className="mt-1 flex min-h-[44px] w-full items-center gap-2 text-left text-[12.5px] text-gray-600"
        aria-label={`${sync.label}. Open court tracking`}
      >
        <span className="relative flex h-2 w-2 flex-shrink-0" aria-hidden="true">
          {sync.tone === "ok" && <span className={cn("absolute inset-0 animate-ring-out rounded-full motion-reduce:animate-none", DOT.ok)} />}
          <span className={cn("relative h-2 w-2 rounded-full", DOT[sync.tone])} />
        </span>
        <span className="min-w-0 flex-1 truncate">{sync.label}</span>
        <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
      </button>

      <NextHearingCard hearings={hearings} onAdd={props.onAddHearing} />

      {/* daily-status slot: what happened at the last hearing. The case page
          passes <DailyStatusCard/> in through the `dailyStatusSlot` prop. */}
      {props.dailyStatusSlot ? (
        <div data-testid="daily-status-slot" className="mt-3">
          {props.dailyStatusSlot}
        </div>
      ) : null}

      <QuickActions {...props} />

      {/* The remaining facts, folded away and remembered. */}
      <div className="mt-3 rounded-[3px] border border-[var(--ci-ink-14)] bg-surface">
        <button
          type="button"
          aria-expanded={detailsOpen}
          onClick={() => toggleDetails()}
          className="flex min-h-[48px] w-full items-center gap-2 px-3 text-left [--press-scale:0.99]"
        >
          <Users className="h-4 w-4 text-gray-500" aria-hidden="true" />
          <span className="flex-1 text-[13.5px] font-semibold text-gray-900">Case facts</span>
          <span className="max-w-[48%] truncate text-[12.5px] text-gray-500">{facts.court}</span>
          <ChevronRight
            aria-hidden="true"
            className={cn("h-4 w-4 flex-shrink-0 text-gray-400 transition-transform duration-300 motion-reduce:transition-none", detailsOpen && "rotate-90")}
          />
        </button>
        <Reveal open={detailsOpen}>
          <dl className="border-t border-gray-100 px-3 py-1">
            {factRows.map(([label, value]) => (
              <div key={label} className="flex min-h-[40px] items-center justify-between gap-4 border-b border-dashed border-gray-200 py-1.5 last:border-0">
                <dt className="flex-shrink-0 font-mono text-[10.5px] uppercase tracking-[0.08em] text-gray-500">{label}</dt>
                <dd className="min-w-0 text-right text-[13.5px] font-semibold leading-snug text-gray-900">{value}</dd>
              </div>
            ))}
            <div className="flex min-h-[40px] items-center justify-between gap-4 py-1.5">
              <dt className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-gray-500">CNR</dt>
              <dd className="font-mono text-[12.5px] text-gray-900">{facts.cnr}</dd>
            </div>
            <button
              type="button"
              onClick={onOpenDetails}
              className="mb-1 flex min-h-[44px] w-full items-center justify-between border-t border-gray-100 text-[13.5px] font-semibold text-gray-800"
            >
              All details <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </dl>
        </Reveal>
      </div>
    </section>
  );
}

function NextHearingCard({ hearings, onAdd }: { hearings: Hearing[]; onAdd: () => void }) {
  const [prepId, setPrepId] = useState<number | null>(null);
  const today = istDayKey();
  // By India DAY, not by clock time: a hearing today stays "next" all day.
  const hearing = useMemo(() => allHearingRows(hearings, [], today).find((r) => r.isNext)?.hearing ?? null, [hearings, today]);
  const day = hearing ? hearingDayKey(hearing.hearing_date) : null;

  if (!hearing || !day) {
    return (
      <div className="mt-3 flex min-h-[72px] items-center gap-3 rounded-[3px] border border-dashed border-gray-300 bg-surface px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-gray-500">Next hearing</div>
          <div className="text-[14px] text-gray-600">No upcoming hearing is scheduled.</div>
        </div>
        <Button variant="secondary" size="sm" onClick={onAdd}>
          <Plus className="h-4 w-4" /> Add
        </Button>
      </div>
    );
  }

  const urgent = dueUrgency(day, today) !== "none";
  const purpose = hearing.purpose || hearing.hearing_type_display;
  return (
    <section
      aria-label="Next hearing"
      className={cn(
        "mt-3 animate-rise-in rounded-[3px] border-x border-b border-t-[3px] bg-surface p-3 shadow-card motion-reduce:animate-none",
        urgent ? "border-[var(--ci-warn)]" : "border-[var(--ci-ink)] !border-t-[var(--ci-ink)]",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-gray-500">Next hearing</span>
        <span
          className={cn("ci-chip ml-auto animate-settle motion-reduce:animate-none", urgent ? "ci-chip--pending" : "ci-chip--none")}
          style={staggerDelay(2, 60)}
        >
          {relativeDay(day, today)}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <DateTile day={day} tone={urgent ? "pending" : "ink"} className="!h-[64px] !w-[56px]" />
        <div className="min-w-0 flex-1">
          <div className="font-serif text-[18px] font-bold leading-tight text-gray-900">
            {dateTile(day).weekday.charAt(0) + dateTile(day).weekday.slice(1).toLowerCase()}, {dayMonth(day)} {day.slice(0, 4)}
          </div>
          {purpose && <div className="mt-0.5 line-clamp-2 text-[13.5px] text-gray-700">{purpose}</div>}
          {hearing.location && <div className="mt-0.5 truncate text-[12.5px] text-gray-500">{hearing.location}</div>}
        </div>
      </div>
      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <CauseListBadge hearing={hearing} />
        <Button variant="secondary" size="sm" className="ml-auto" onClick={() => setPrepId(hearing.id)}>
          <FileText className="h-4 w-4" /> Prep sheet
        </Button>
      </div>
      <HearingDigestDialog hearingId={prepId} onClose={() => setPrepId(null)} />
    </section>
  );
}

function QuickActions(props: MobileCaseViewProps) {
  const { caseItem } = props;
  const refresh = useRefreshTracking(caseItem.id);

  async function handleRefresh() {
    try {
      const result = await refresh.mutateAsync(false);
      if (result.rate_limited) {
        showToast.error("Refresh limited", "This case was checked recently. Try again in a bit.");
      } else {
        showToast.success(
          "Tracking refreshed",
          result.new_hearing_dates && result.new_hearing_dates.length > 0
            ? `${result.new_hearing_dates.length} new hearing date(s) found.`
            : "No changes since last check.",
        );
      }
    } catch {
      showToast.error("Refresh failed", "Could not reach the court portal. Please try again later.");
    }
  }

  return (
    <div className="ci-hscroll -mx-4 mt-3 px-4 py-0.5" aria-label="Quick actions">
      {caseItem.tracking_enabled && (
        <Button variant="secondary" size="sm" onClick={handleRefresh} disabled={refresh.isPending}>
          {refresh.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
      )}
      <Button variant="secondary" size="sm" onClick={props.onAddHearing}>
        <Plus className="h-4 w-4" /> Hearing
      </Button>
      <Button variant="secondary" size="sm" onClick={props.onUpload}>
        <Upload className="h-4 w-4" /> Upload
      </Button>
      <Button variant="secondary" size="sm" onClick={props.onGenerate}>
        <FilePlus2 className="h-4 w-4" /> Generate
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

function OverviewTab(props: MobileCaseViewProps) {
  const { caseItem, orders, viewingOrderId } = props;
  const order = latestOrderForOverview(orders);
  const summary = order?.summary;
  const ready = !!order && !!summary && summary.status !== "pending";
  const directions = summary ? directionsOf(summary) : null;
  const [more, setMore] = useState(false);

  return (
    <div className="flex flex-col gap-3">
      <MSection id="m-case-last-order" title="Last order">
        <div className="mb-2 rounded-[3px] border border-[var(--ci-ink-14)] bg-surface p-3 shadow-card">
          {!order || !ready || !summary ? (
            <p className="text-[13.5px] text-gray-500">No order summary yet.</p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Gavel className="h-4 w-4 text-gray-500" aria-hidden="true" />
                <span className="font-mono text-[11px] uppercase tracking-[0.08em] text-gray-500">
                  {order.order_date ? `${dayMonth(order.order_date)} ${order.order_date.slice(0, 4)}` : "Order"}
                </span>
              </div>
              <p className={cn("mt-1.5 text-[14px] leading-[1.5] text-gray-900", !more && "line-clamp-4")}>
                {summary.status === "failed" ? "Summary unavailable. Open the order to read it." : summary.what_happened}
              </p>
              {directions && (
                <Reveal open={more}>
                  <div className="mt-2 rounded border border-gray-200 bg-page px-2.5 py-2">
                    <div className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-gray-500">{directions.label}</div>
                    <p className="mt-0.5 text-[13px] leading-[1.45] text-gray-900">{directions.text}</p>
                  </div>
                </Reveal>
              )}
              {caseItem.user_party_role === "unknown" && directions && more && (
                <p className="mt-1.5 text-xs text-gray-500">
                  Your side isn&apos;t recorded, so both sides are shown.{" "}
                  <button type="button" onClick={props.onEditDetails} className="font-semibold text-gray-800 underline">
                    Set it
                  </button>
                </p>
              )}
              <div className="mt-2 flex items-center gap-2">
                <button
                  type="button"
                  aria-expanded={more}
                  onClick={() => setMore((v) => !v)}
                  className="min-h-[44px] text-[13px] font-semibold text-gray-700 underline"
                >
                  {more ? "Show less" : "Read more"}
                </button>
                {order.has_file && (
                  <Button variant="secondary" size="sm" className="ml-auto" onClick={() => props.onViewOrder(order.id)} disabled={viewingOrderId === order.id}>
                    {viewingOrderId === order.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                    Read the order
                  </Button>
                )}
              </div>
            </>
          )}
        </div>
      </MSection>

      <CompactTasks
        caseId={props.caseId}
        caseTitle={caseItem.title}
        courtType={caseItem.court_type}
        latestOrder={props.latestDatedOrder}
        rows={3}
      />
      <CompactCalendar
        caseId={props.caseId}
        hearings={props.hearings}
        caseItem={caseItem}
        mode="week"
        items={3}
        onEditDetails={props.onEditDetails}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hearings
// ---------------------------------------------------------------------------

const ROW_DOT: Record<HearingRow["tone"], string> = {
  upcoming: "bg-[var(--ci-warn)]",
  passed: "bg-gray-400",
  order: "bg-[var(--ci-listed)]",
  other: "bg-gray-400",
};

function HearingsTab(props: MobileCaseViewProps) {
  const today = istDayKey();
  const [filter, setFilter] = useState<HearingFilter>("all");
  const [openId, setOpenId] = useState<number | null>(null);
  const [prepId, setPrepId] = useState<number | null>(null);

  const all = useMemo(() => allHearingRows(props.hearings, props.orders, today), [props.hearings, props.orders, today]);
  const byDate = useMemo(() => groupOrdersByDate(props.orders), [props.orders]);
  // What the court recorded at each hearing (district cases): a preview line
  // in the row, the full text in the sheet.
  const business = useHearingBusiness(props.caseItem, props.hearings);
  const rows = filterHearingRows(all, filter);
  const open = all.find((r) => r.hearing.id === openId) ?? null;
  const chips: [HearingFilter, string][] = [
    ["all", "All"],
    ["upcoming", "Upcoming"],
    ["passed", "Passed"],
    ["orders", "Orders"],
  ];

  return (
    <div>
      <div className="flex items-center gap-2 py-1">
        <h2 className="min-w-0 flex-1 !text-[17px] !font-bold">Hearings &amp; orders</h2>
        <span className="ci-chip ci-chip--none">{all.length}</span>
        <Button variant="secondary" size="sm" onClick={props.onAddHearing}>
          <Plus className="h-4 w-4" /> Add
        </Button>
      </div>

      <div role="group" aria-label="Filter hearings" className="ci-hscroll -mx-4 mb-2 px-4">
        {chips.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
            className={cn(
              "h-10 rounded-full border px-4 text-[13px] font-semibold transition-colors",
              filter === key ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]" : "border-gray-200 bg-surface text-gray-700",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {props.hearingsLoading ? (
        <p className="py-4 text-sm text-gray-500">Loading hearings…</p>
      ) : rows.length === 0 ? (
        <p className="rounded-[3px] border border-dashed border-gray-200 px-4 py-6 text-center text-[14px] text-gray-500">No hearings here.</p>
      ) : (
        <ul key={filter} className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface shadow-card">
          {rows.map((row, i) => {
            const t = dateTile(row.day);
            const info = business.infoFor(row.hearing);
            const entry = info.kind === "entry" ? info.entry : null;
            return (
              <li key={row.hearing.id} style={riseIn(i).style} className={cn("border-b border-gray-100 last:border-0", riseIn(i).className)}>
                <button
                  type="button"
                  onClick={() => setOpenId(row.hearing.id)}
                  className={cn(
                    "flex min-h-[64px] w-full items-center gap-3 px-3 py-2 text-left [--press-scale:0.99]",
                    row.isNext && "bg-[color-mix(in_srgb,var(--ci-warn)_9%,white)]",
                  )}
                  aria-label={`${dayMonth(row.day)} ${row.day.slice(0, 4)}: ${row.status}. Open details${entry ? ". What happened is saved" : ""}`}
                >
                  <span className={cn("h-2.5 w-2.5 flex-shrink-0 rounded-full", ROW_DOT[row.tone])} aria-hidden="true" />
                  <span className="w-[54px] flex-shrink-0">
                    <span className="block font-serif text-[16px] font-bold leading-tight text-gray-900">
                      {t.date} {t.month.charAt(0) + t.month.slice(1).toLowerCase()}
                    </span>
                    <span className="block font-mono text-[10.5px] text-gray-500">{row.day.slice(0, 4)}</span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="line-clamp-2 text-[13px] leading-snug text-gray-700">{row.text || "—"}</span>
                    {entry && <HearingBusinessPreview entry={entry} />}
                    <span className="mt-0.5 block font-mono text-[10.5px] tracking-[0.06em] text-gray-500">{row.status}</span>
                  </span>
                  {row.order?.has_file && <FileText className="h-4 w-4 flex-shrink-0 text-[color:var(--ci-listed)]" aria-label="Order available" />}
                  <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <div className="px-1 pt-2 text-xs text-gray-500">{props.statusLine}</div>

      <BottomSheet
        open={open !== null}
        onClose={() => setOpenId(null)}
        label="Hearing details"
        title={open ? `${dayMonth(open.day)} ${open.day.slice(0, 4)}` : "Hearing"}
        bodyClassName="p-3"
      >
        {open && (
          <HearingItem
            hearing={open.hearing}
            caseId={props.caseId}
            isUpcoming={open.tone === "upcoming"}
            onPrepare={open.tone === "upcoming" ? setPrepId : undefined}
            onEdit={(h) => {
              setOpenId(null);
              props.onEditHearing(h);
            }}
            onDelete={(id) => {
              setOpenId(null);
              props.onDeleteHearing(id);
            }}
            isDeleting={props.deletingHearingId === open.hearing.id}
            orders={byDate.get(hearingDateKey(open.hearing.hearing_date))}
            onViewOrder={props.onViewOrder}
            viewingOrderId={props.viewingOrderId}
            whatHappened={
              <HearingBusinessSection info={business.infoFor(open.hearing)} check={business.check} onReload={business.reload} />
            }
          />
        )}
      </BottomSheet>
      <HearingDigestDialog hearingId={prepId} onClose={() => setPrepId(null)} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Documents, and fees & more
// ---------------------------------------------------------------------------

function DocsTab(props: MobileCaseViewProps) {
  return (
    <CompactDocuments
      documents={props.documents}
      isLoading={props.docsLoading}
      rows={6}
      onUploadClick={props.onUpload}
      onGenerateClick={props.onGenerate}
      onView={props.onViewDocument}
      onProcess={props.onProcessDocument}
      onDelete={props.onDeleteDocument}
      isProcessPending={props.processPending}
      processingDocId={props.processingDocId}
      statusLine={props.statusLine}
    />
  );
}

function MoreTab(props: MobileCaseViewProps) {
  const { caseItem } = props;
  return (
    <div className="flex flex-col gap-3">
      <CompactFees caseItem={caseItem} hearings={props.hearings} />
      <CompactClientUpdates caseItem={caseItem} onEditDetails={props.onEditDetails} />
      <ul className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface shadow-card">
        {[
          ["Court tracking", props.onOpenTracking],
          ["Case details and contacts", props.onOpenDetails],
          ["Edit case details", props.onEditDetails],
        ].map(([label, action]) => (
          <li key={label as string} className="border-b border-gray-100 last:border-0">
            <button
              type="button"
              onClick={action as () => void}
              className="flex min-h-[52px] w-full items-center gap-2 px-4 text-left text-[14px] font-semibold text-gray-900 [--press-scale:0.99]"
            >
              <span className="flex-1">{label as string}</span>
              <ChevronRight className="h-4 w-4 text-gray-400" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Case Bot button
// ---------------------------------------------------------------------------

/** The Case Bot, floating over the bottom-right where the thumb rests, above
 * the tab bar. It settles in after the page and presses in under a tap. */
function BotButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Ask the Case Bot"
      className="fixed right-4 z-20 flex h-14 animate-pop-in items-center gap-2 rounded-full bg-[var(--ci-ink)] pl-4 pr-5 text-[14px] font-semibold text-[color:var(--ci-paper)] shadow-[0_10px_26px_-8px_rgba(14,26,44,0.6)] [--press-scale:0.92] motion-reduce:animate-none md:hidden"
      style={{ bottom: "calc(var(--mobile-nav-height) + 14px)", animationDelay: "350ms" }}
    >
      <Bot className="h-5 w-5" aria-hidden="true" />
      Case Bot
    </button>
  );
}
