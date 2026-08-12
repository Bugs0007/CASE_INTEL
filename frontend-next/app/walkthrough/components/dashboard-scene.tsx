"use client";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CalendarClock, RefreshCw, FileWarning } from "lucide-react";
import { Spotlight } from "./spotlight";
import { mockAttentionItems, mockDensityDays, mockUrgentCases } from "../mock-data";

const ATTENTION_ICON = { hearing: CalendarClock, update: RefreshCw, failed: FileWarning } as const;
const ATTENTION_STYLE = {
  hearing: "bg-status-pending-soft text-status-pending",
  update: "bg-gray-100 text-gray-600",
  failed: "bg-status-alert-soft text-status-alert",
} as const;

export function DashboardScene({ highlight }: { highlight: string }) {
  return (
    <div className="max-w-[1240px] mx-auto pb-4">
      <Spotlight id="attention" active={highlight} className="block mb-5">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
            <CardTitle className="flex items-center gap-2.5 text-lg font-bold">
              Needs Your Attention
              <span className="ci-chip ci-chip--pending">{mockAttentionItems.length}</span>
            </CardTitle>
            <span className="text-xs text-gray-400">Updated just now</span>
          </CardHeader>
          <CardContent>
            <div className="space-y-1">
              {mockAttentionItems.map((item) => {
                const Icon = ATTENTION_ICON[item.kind];
                return (
                  <div key={item.key} className="flex items-center gap-4 py-3 px-1 rounded-lg">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${ATTENTION_STYLE[item.kind]}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-900">
                        <span className="font-semibold">{item.title}</span> {item.message}
                      </div>
                      <div className="text-xs font-mono text-gray-500 mt-0.5">{item.meta}</div>
                    </div>
                    <Button variant="secondary" size="sm" tabIndex={-1}>
                      View Case
                    </Button>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </Spotlight>

      <Card className="mb-5">
        <CardHeader>
          <CardTitle>Next 14 Days</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-1.5 h-16">
            {mockDensityDays.map((count, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1">
                <div
                  className="w-full rounded-sm bg-primary"
                  style={{ height: `${Math.max(count, 0.15) * 18}px`, opacity: count === 0 ? 0.12 : 1 }}
                />
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-400 mt-2">Hearings per day across all your cases</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cases by Urgency</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-gray-100">
          {mockUrgentCases.map((c) => (
            <div key={c.number} className="flex items-center justify-between py-3 first:pt-0 last:pb-0 gap-3">
              <div className="min-w-0">
                <div className="text-sm font-medium text-gray-900 truncate">{c.title}</div>
                <div className="text-xs font-mono text-gray-500">{c.number}</div>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className={`ci-chip ${c.priority === "High" ? "ci-chip--alert" : "ci-chip--pending"}`}>
                  {c.priority}
                </span>
                <span className="text-xs text-gray-500 w-20 text-right">{c.days}</span>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
