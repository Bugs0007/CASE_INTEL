"use client";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plane, Hotel, Upload, FileText } from "lucide-react";
import { Spotlight } from "./spotlight";
import { mockCase, mockHearings, mockTravelBookings } from "../mock-data";

const TYPE_ICON: Record<string, typeof Plane> = { Train: Plane, Hotel: Hotel };

export function TravelScene({ highlight }: { highlight: string }) {
  const hearing = mockHearings[1];

  return (
    <div className="max-w-[700px] mx-auto pb-4">
      <div className="mb-5">
        <div className="ci-eyebrow mb-1">{mockCase.caseNumber}</div>
        <h1 className="text-[26px]">Travel for {hearing.date.split(",")[0]}</h1>
        <p className="text-sm text-gray-600 mt-1.5">
          Out-of-town hearings often mean a train or flight and a hotel stay. Keep the bookings
          here, attached to the hearing they&apos;re for, instead of buried in an email inbox.
        </p>
      </div>

      <Spotlight id="travel-upload" active={highlight} className="block">
        <Card>
          <CardHeader>
            <CardTitle>Travel Bookings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="ci-empty !py-7">
              <Upload className="h-8 w-8 text-gray-400 mx-auto mb-2.5" />
              <h3 className="text-base mb-1">Upload a ticket or booking confirmation</h3>
              <p className="text-sm text-gray-500 mb-3.5">PDF, or a photo of a printed ticket</p>
              <Button size="sm" tabIndex={-1}>
                <Upload className="h-4 w-4" />
                Choose File
              </Button>
            </div>

            <div className="space-y-2">
              {mockTravelBookings.map((b) => {
                const Icon = TYPE_ICON[b.type] ?? FileText;
                return (
                  <div
                    key={b.file}
                    className="flex items-center gap-3 p-3 border border-gray-100 rounded-lg"
                  >
                    <div className="w-9 h-9 rounded-lg bg-status-ok-soft text-status-ok flex items-center justify-center flex-shrink-0">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-900">{b.type} · {b.label}</div>
                      <div className="text-xs font-mono text-gray-500">{b.file}</div>
                    </div>
                    <span className="ci-chip ci-chip--ok flex-shrink-0">{b.status}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </Spotlight>
    </div>
  );
}
