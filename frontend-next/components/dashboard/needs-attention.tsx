import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { CalendarClock, RefreshCw, FileWarning } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import type { UpcomingHearing, Document } from "@/types";

interface NeedsAttentionProps {
  /** Hearings happening within the next 48 hours, across all cases. */
  hearingsSoon: UpcomingHearing[];
  /** eCourts-sourced hearings whose date changed since the user's last visit. */
  ecourtsUpdates: UpcomingHearing[];
  /** Documents that failed processing. */
  failedDocuments: Document[];
}

type AttentionItem = {
  key: string;
  href: string;
  iconBg: string;
  iconColor: string;
  icon: typeof CalendarClock;
  message: ReactNode;
  meta: string;
};

export function NeedsAttention({
  hearingsSoon,
  ecourtsUpdates,
  failedDocuments,
}: NeedsAttentionProps) {
  // "Updated just now" -> relative time, refreshed on an interval so it
  // reads naturally as the section ages on screen (matches the design's
  // "Updated 2 minutes ago" header treatment).
  const [renderedAt] = useState(() => new Date().toISOString());
  const [, forceTick] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => forceTick((n) => n + 1), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const hearingSoonIds = new Set(hearingsSoon.map((h) => h.id));

  const items: AttentionItem[] = [];

  for (const h of hearingsSoon) {
    items.push({
      key: `hearing-${h.id}`,
      href: `/cases/${h.case_id}`,
      iconBg: "bg-[#fdecec]",
      iconColor: "text-[#b32e26]",
      icon: CalendarClock,
      message: (
        <>
          <span className="font-semibold">{h.case_title}</span> has a{" "}
          {h.hearing_type} hearing {h.days_until === 0 ? "today" : "tomorrow"}
          {h.purpose ? ` — ${h.purpose}` : ""}
        </>
      ),
      meta: `${formatDate(h.hearing_date, "MMM d, h:mm a")} · ${h.case_number}`,
    });
  }

  for (const h of ecourtsUpdates) {
    if (hearingSoonIds.has(h.id)) continue; // already surfaced above
    items.push({
      key: `ecourts-${h.id}`,
      href: `/cases/${h.case_id}`,
      iconBg: "bg-[#ebf3fb]",
      iconColor: "text-[#2f6fb0]",
      icon: RefreshCw,
      message: (
        <>
          <span className="font-semibold">{h.case_title}</span> — eCourts found
          a new hearing date since your last login
        </>
      ),
      meta: `New date ${formatDate(h.hearing_date)} · ${h.case_number}`,
    });
  }

  for (const d of failedDocuments) {
    items.push({
      key: `doc-${d.id}`,
      href: d.case_id ? `/cases/${d.case_id}` : "/documents",
      iconBg: "bg-[#fdecec]",
      iconColor: "text-[#b32e26]",
      icon: FileWarning,
      message: (
        <>
          <span className="font-semibold">{d.case?.title || "Unassigned"}</span>
          : {d.filename} failed processing
        </>
      ),
      meta: d.case?.case_number || d.filename,
    });
  }

  return (
    <Card className="mb-5">
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2.5 text-lg font-bold">
          Needs Your Attention
          {items.length > 0 && (
            <span className="inline-flex items-center h-5 px-2 rounded-full bg-[#fdf0e4] text-[#9a4a12] text-xs font-bold">
              {items.length}
            </span>
          )}
        </CardTitle>
        <span className="text-xs text-gray-400">
          Updated {formatRelativeTime(renderedAt)}
        </span>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-gray-500 text-sm py-4">
            Nothing needs your attention right now.
          </p>
        ) : (
          <div className="space-y-1">
            {items.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.key}
                  className="flex items-center gap-4 py-3 px-1 rounded-lg"
                >
                  <div
                    className={`w-9 h-9 rounded-lg ${item.iconBg} flex items-center justify-center flex-shrink-0`}
                  >
                    <Icon className={`h-4 w-4 ${item.iconColor}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-900">{item.message}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{item.meta}</div>
                  </div>
                  <Link href={item.href}>
                    <Button variant="secondary" size="sm">
                      View Case
                    </Button>
                  </Link>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
