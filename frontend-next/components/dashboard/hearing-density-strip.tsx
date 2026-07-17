"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { addDays, format, isSameDay, parseISO, startOfDay } from "date-fns";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { UpcomingHearing } from "@/types";

interface HearingDensityStripProps {
  hearings: UpcomingHearing[];
}

const DAY_COUNT = 14;

export function HearingDensityStrip({ hearings }: HearingDensityStripProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const days = useMemo(() => {
    const today = startOfDay(new Date());
    return Array.from({ length: DAY_COUNT }, (_, i) => {
      const date = addDays(today, i);
      const dayHearings = hearings.filter((h) =>
        isSameDay(parseISO(h.hearing_date), date),
      );
      return { date, hearings: dayHearings };
    });
  }, [hearings]);

  const selected = days[selectedIndex];
  const maxCount = Math.max(1, ...days.map((d) => d.hearings.length));

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Next 14 Days</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-7 sm:grid-cols-[repeat(14,minmax(0,1fr))] gap-1.5 mb-4">
          {days.map((day, i) => {
            const isSelected = i === selectedIndex;
            const barHeight = 12 + day.hearings.length * 16;
            const barColor = isSelected
              ? "#323b83"
              : day.hearings.length === 0
                ? "#eceef2"
                : day.hearings.length >= 2
                  ? "#8d9bdb"
                  : "#b9c3ec";
            return (
              <button
                key={day.date.toISOString()}
                onClick={() => setSelectedIndex(i)}
                className="flex flex-col items-center gap-1.5 rounded-lg py-1 px-0.5"
                style={{ background: isSelected ? "#eef1fb" : "transparent" }}
              >
                <div
                  className="text-[11px] leading-tight"
                  style={{
                    fontWeight: isSelected ? 700 : 400,
                    color: isSelected ? "#272e68" : "#9aa1b2",
                  }}
                >
                  {format(day.date, "EEE")}
                  <br />
                  {format(day.date, "d")}
                </div>
                <div
                  className="w-full rounded"
                  style={{ height: `${barHeight}px`, background: barColor }}
                />
                <div
                  className="text-[11px]"
                  style={{
                    fontWeight: isSelected ? 700 : 400,
                    color: isSelected ? "#272e68" : day.hearings.length > 0 ? "#717889" : "#c3c9d4",
                  }}
                >
                  {day.hearings.length}
                </div>
              </button>
            );
          })}
        </div>

        <div className="border-t border-gray-100 pt-4">
          <div className="text-sm font-semibold text-gray-600 mb-3">
            {format(selected.date, "EEEE, MMMM d")} · {selected.hearings.length}{" "}
            hearing(s)
          </div>
          {selected.hearings.length === 0 ? (
            <p className="text-sm text-gray-500">
              No hearings scheduled for this day.
            </p>
          ) : (
            <div className="space-y-2">
              {selected.hearings.map((h) => (
                <div
                  key={h.id}
                  className="flex items-center justify-between gap-3 p-3 border border-gray-100 rounded-lg flex-wrap"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-gray-900">
                      {h.case_title}
                    </div>
                    <div className="text-xs text-gray-500">
                      {h.hearing_type}
                      {h.judge ? ` · ${h.judge}` : ""} ·{" "}
                      {format(parseISO(h.hearing_date), "h:mm a")}
                    </div>
                  </div>
                  <Link href={`/cases/${h.case_id}`}>
                    <Button variant="secondary" size="sm">
                      View Case
                    </Button>
                  </Link>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
