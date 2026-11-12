"use client";

import { Suspense, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Inbox, ScrollText, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ClientMessageCard } from "@/components/client-updates/client-message-card";
import { MobileSubbar } from "@/components/layout/mobile-chrome";
import { UnderlineTabs } from "@/components/mobile/underline-tabs";
import { useClientMessages, useSentMessages } from "@/hooks/use-clients";
import { useIsMobile } from "@/hooks/use-is-mobile";
import {
  DRAFT_FILTERS,
  SENT_FILTERS,
  draftCounts,
  filterDrafts,
  filterSent,
  sentCounts,
  type DraftFilter,
  type SentFilter,
} from "@/lib/messages-model";
import { cn, formatDate, staggerDelay } from "@/lib/utils";

type Tab = "drafts" | "sent";

/** Client emails written by the system for the advocate to review and send
 * (case updates after an order or a new hearing date; payment reminders on
 * overdue invoices), plus the audit log of everything that went out.
 *
 * The tab lives in the URL (?tab=sent) so the sent log can be linked to. */
export default function MessagesPage() {
  // useSearchParams needs a Suspense boundary on a prerendered page.
  return (
    <Suspense fallback={null}>
      <Messages />
    </Suspense>
  );
}

function Messages() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isMobile = useIsMobile();
  const tab: Tab = searchParams.get("tab") === "sent" ? "sent" : "drafts";
  const setTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams.toString());
    if (next === "drafts") params.delete("tab");
    else params.set("tab", next);
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  };
  const [kind, setKind] = useState<DraftFilter>("all");
  const [delivery, setDelivery] = useState<SentFilter>("all");
  const [query, setQuery] = useState("");

  // All drafts at once: the kind chips filter and count them here, so each
  // chip can say how many it holds.
  const drafts = useClientMessages({ status: "draft" });
  const sent = useSentMessages();

  const draftRows = drafts.data;
  const sentRows = sent.data;
  const dCounts = useMemo(() => draftCounts(draftRows ?? []), [draftRows]);
  const sCounts = useMemo(() => sentCounts(sentRows ?? []), [sentRows]);
  const shownDrafts = useMemo(() => filterDrafts(draftRows ?? [], kind, query), [draftRows, kind, query]);
  const shownSent = useMemo(() => filterSent(sentRows ?? [], delivery, query), [sentRows, delivery, query]);

  const searching = query.trim().length > 0;
  const clearFilters = () => {
    setQuery("");
    setKind("all");
    setDelivery("all");
  };

  const tabs: { key: Tab; label: string; count: number | null; icon: React.ReactNode }[] = [
    { key: "drafts", label: "Drafts", count: draftRows ? dCounts.all : null, icon: <Inbox className="h-4 w-4" /> },
    { key: "sent", label: "Sent log", count: null, icon: <ScrollText className="h-4 w-4" /> },
  ];

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[900px] mx-auto">
      {/* On a phone the two tabs are pinned under the top bar. */}
      {isMobile && (
        <MobileSubbar height={44}>
          <UnderlineTabs
            label="Messages"
            active={tab}
            onChange={setTab}
            tabs={tabs.map((t) => ({
              key: t.key,
              label: (
                <>
                  {t.label}
                  {t.count ? <span className="ci-chip ci-chip--pending !px-1.5">{t.count}</span> : null}
                </>
              ),
            }))}
          />
        </MobileSubbar>
      )}

      <div className="mb-5 max-md:mb-3.5 max-md:animate-rise-in motion-reduce:animate-none">
        <h1 className="text-page-title max-md:!text-[26px] max-md:!leading-[1.1] text-gray-900 mb-1.5">Client messages</h1>
        <p className="text-sm text-gray-600">
          Updates and reminders drafted for you. Nothing reaches a client until you press Send.
        </p>
      </div>

      {!isMobile && (
        <div className="flex flex-wrap items-center gap-2 mb-4" role="tablist" aria-label="Messages">
          {tabs.map((t) => (
            <TabButton key={t.key} active={tab === t.key} onClick={() => setTab(t.key)} icon={t.icon}>
              {t.label}
              {t.count ? ` (${t.count})` : ""}
            </TabButton>
          ))}
        </div>
      )}

      <div className="mb-3 flex flex-col gap-2.5 md:mb-4 md:flex-row md:items-center">
        <div
          role="search"
          className="flex h-12 min-w-0 items-center gap-2.5 rounded-lg border border-gray-200 bg-surface px-3 focus-within:border-[var(--ci-ink)] md:h-10 md:flex-1"
        >
          <Search className="h-[18px] w-[18px] flex-shrink-0 text-gray-400" strokeWidth={1.8} aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search client, case or subject"
            aria-label="Search messages"
            enterKeyHint="search"
            className="min-w-0 flex-1 bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-400 [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <button
              type="button"
              aria-label="Clear search"
              onClick={() => setQuery("")}
              className="flex h-8 w-8 flex-shrink-0 animate-pop-in items-center justify-center rounded-full bg-gray-100 text-gray-500 motion-reduce:animate-none"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {tab === "drafts" ? (
          <FilterChips
            label="Filter drafts"
            value={kind}
            onChange={setKind}
            options={DRAFT_FILTERS.map((f) => ({ ...f, count: draftRows ? dCounts[f.value] : null }))}
          />
        ) : (
          <FilterChips
            label="Filter sent messages"
            value={delivery}
            onChange={setDelivery}
            options={SENT_FILTERS.map((f) => ({ ...f, count: sentRows ? sCounts[f.value] : null }))}
          />
        )}
      </div>

      {tab === "drafts" ? (
        drafts.isLoading ? (
          <ListSkeleton />
        ) : drafts.isError ? (
          <LoadError what="drafts" onRetry={() => drafts.refetch()} />
        ) : !draftRows?.length ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-gray-500">
              No drafts waiting. New ones appear after an order is processed, a new hearing date is
              found, or an invoice goes unpaid past your reminder interval (set in{" "}
              <Link href="/settings" className="underline">Settings</Link>).
            </CardContent>
          </Card>
        ) : shownDrafts.length === 0 ? (
          <NoMatches onClear={clearFilters} searching={searching} />
        ) : (
          <div className="space-y-2" data-testid="draft-list">
            {shownDrafts.map((message, i) => (
              <div
                key={message.id}
                style={staggerDelay(i, 40, 8)}
                className="animate-rise-in motion-reduce:animate-none"
              >
                <ClientMessageCard message={message} showCase variant="inbox" />
              </div>
            ))}
          </div>
        )
      ) : sent.isLoading ? (
        <ListSkeleton />
      ) : sent.isError ? (
        <LoadError what="the sent log" onRetry={() => sent.refetch()} />
      ) : !sentRows?.length ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-gray-500">Nothing sent yet.</CardContent>
        </Card>
      ) : shownSent.length === 0 ? (
        <NoMatches onClear={clearFilters} searching={searching} />
      ) : (
        <Card>
          {/* Phones: one stacked row per message. As a table, To and
              Delivery -- whether it was actually emailed -- sat off-screen
              behind a sideways scroll at 375px. */}
          <ul className="md:hidden divide-y divide-gray-100" data-testid="sent-log-list">
            {shownSent.map((row) => (
              <li key={row.id} className="space-y-1 px-4 py-3 text-sm">
                <div className="text-gray-900">{row.subject}</div>
                <div className="text-xs text-gray-500">
                  {row.kind_display}
                  {row.case_number ? ` · ${row.case_number}` : ""}
                </div>
                <div className="break-words text-xs text-gray-700">To {row.to_emails.join(", ")}</div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span className={cn("ci-chip", row.delivery === "sent" ? "ci-chip--ok" : "ci-chip--pending")}>
                    {row.delivery === "sent" ? "Sent" : "Logged, not emailed"}
                  </span>
                  {formatDate(row.sent_at, "d MMM yyyy, HH:mm")}
                  {row.sent_by_username && ` · by ${row.sent_by_username}`}
                </div>
              </li>
            ))}
          </ul>
          <CardContent className="hidden md:block p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-gray-500 border-b border-gray-100">
                <tr>
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">What</th>
                  <th className="px-4 py-2 font-medium">To</th>
                  <th className="px-4 py-2 font-medium">Delivery</th>
                </tr>
              </thead>
              <tbody>
                {shownSent.map((row) => (
                  <tr key={row.id} className="border-b border-gray-50 align-top">
                    <td className="px-4 py-2 whitespace-nowrap text-gray-600">
                      {formatDate(row.sent_at, "d MMM yyyy, HH:mm")}
                      {row.sent_by_username && <div className="text-xs text-gray-400">by {row.sent_by_username}</div>}
                    </td>
                    <td className="px-4 py-2">
                      <div className="text-gray-900">{row.subject}</div>
                      <div className="text-xs text-gray-500">
                        {row.kind_display}
                        {row.case_number ? ` · ${row.case_number}` : ""}
                      </div>
                    </td>
                    <td className="px-4 py-2 text-gray-700">{row.to_emails.join(", ")}</td>
                    <td className="px-4 py-2">
                      <span className={cn("ci-chip", row.delivery === "sent" ? "ci-chip--ok" : "ci-chip--pending")}>
                        {row.delivery === "sent" ? "Sent" : "Logged, not emailed"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function FilterChips<V extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: V;
  onChange: (value: V) => void;
  /** null while the list is still loading: no number rather than a false 0. */
  options: { value: V; label: string; count: number | null }[];
}) {
  return (
    <div className="ci-hscroll md:flex-wrap md:overflow-visible" role="group" aria-label={label}>
      {options.map((f) => (
        <button
          key={f.value}
          type="button"
          onClick={() => onChange(f.value)}
          aria-pressed={value === f.value}
          className={cn(
            "inline-flex min-h-[44px] items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors md:min-h-[36px]",
            value === f.value
              ? "border-primary bg-primary text-page"
              : "border-gray-200 bg-surface text-gray-700 hover:bg-gray-50",
          )}
        >
          {f.label}
          {f.count !== null && (
            <span className={cn("text-xs", value === f.value ? "opacity-80" : "text-gray-500")}>{f.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading messages">
      <Skeleton className="h-[88px] rounded-lg" />
      <Skeleton className="h-[88px] rounded-lg" />
      <Skeleton className="h-[88px] rounded-lg" />
    </div>
  );
}

function LoadError({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="py-10 text-center">
        <p className="text-sm text-status-alert">Could not load {what}. Try again.</p>
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      </CardContent>
    </Card>
  );
}

function NoMatches({ onClear, searching }: { onClear: () => void; searching: boolean }) {
  return (
    <Card>
      <CardContent className="py-8 text-center text-sm text-gray-500">
        {searching ? "Nothing matches your search here." : "Nothing in this view."}{" "}
        <button type="button" onClick={onClear} className="underline">
          Show everything
        </button>
      </CardContent>
    </Card>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium",
        active ? "bg-primary text-page" : "text-gray-700 hover:bg-gray-100",
      )}
    >
      {icon}
      {children}
    </button>
  );
}
