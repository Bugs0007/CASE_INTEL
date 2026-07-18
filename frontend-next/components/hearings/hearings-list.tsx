"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Collapsible } from "@/components/ui/collapsible";
import { formatDateTime, staggerDelay } from "@/lib/utils";
import { Calendar, MapPin, User, Plus, Edit, Trash2, Loader2 } from "lucide-react";
import type { Hearing } from "@/types";

const DEFAULT_VISIBLE_COUNT = 5;

interface HearingsListProps {
  caseId: number;
  hearings: Hearing[];
  isLoading?: boolean;
  onAddHearing?: () => void;
  onEditHearing?: (hearing: Hearing) => void;
  onDeleteHearing?: (id: number) => void;
  deletingId?: number;
}

export function HearingsList({
  caseId,
  hearings,
  isLoading,
  onAddHearing,
  onEditHearing,
  onDeleteHearing,
  deletingId,
}: HearingsListProps) {
  const [sectionOpen, setSectionOpen] = useState(true);
  const [upcomingShowAll, setUpcomingShowAll] = useState(false);
  // Past hearings grow unbounded over a long case and are rarely what the
  // user opened the page to see, so this subsection defaults collapsed.
  const [pastOpen, setPastOpen] = useState(false);
  const [pastShowAll, setPastShowAll] = useState(false);

  const now = new Date();
  // Hearing model default ordering is ascending by hearing_date, so this is
  // already soonest-first -- exactly what "Upcoming" wants.
  const upcomingHearings = hearings.filter(
    (h) => new Date(h.hearing_date) >= now && h.status === "scheduled",
  );
  // Reversed to most-recent-first for "Past", since that's the useful
  // default view on a long-running case.
  const pastHearings = hearings
    .filter((h) => new Date(h.hearing_date) < now || h.status !== "scheduled")
    .slice()
    .reverse();

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hearings & Deadlines</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-20 bg-gray-200 rounded animate-pulse" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const visibleUpcoming = upcomingShowAll
    ? upcomingHearings
    : upcomingHearings.slice(0, DEFAULT_VISIBLE_COUNT);
  const visiblePast = pastShowAll ? pastHearings : pastHearings.slice(0, DEFAULT_VISIBLE_COUNT);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>
          Hearings & Deadlines{hearings.length > 0 ? ` (${hearings.length})` : ""}
        </CardTitle>
        <div className="flex items-center gap-2">
          <CollapseToggle isOpen={sectionOpen} onToggle={() => setSectionOpen((v) => !v)} />
          <Button variant="secondary" size="sm" onClick={onAddHearing}>
            <Plus className="h-4 w-4" />
            Add Hearing
          </Button>
        </div>
      </CardHeader>
      <Collapsible isOpen={sectionOpen}>
        <CardContent>
          {/* Upcoming Hearings */}
          {upcomingHearings.length > 0 && (
            <div className="mb-6">
              <h4 className="text-sm font-medium text-gray-700 mb-3 uppercase tracking-wide">
                Upcoming ({upcomingHearings.length})
              </h4>
              <div
                className={
                  upcomingShowAll ? "max-h-[480px] overflow-y-auto pr-1 space-y-3" : "space-y-3"
                }
              >
                {visibleUpcoming.map((hearing, i) => (
                  <HearingItem
                    key={hearing.id}
                    hearing={hearing}
                    index={i}
                    isUpcoming
                    onEdit={onEditHearing}
                    onDelete={onDeleteHearing}
                    isDeleting={deletingId === hearing.id}
                  />
                ))}
              </div>
              {upcomingHearings.length > DEFAULT_VISIBLE_COUNT && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full mt-2"
                  onClick={() => setUpcomingShowAll((v) => !v)}
                >
                  {upcomingShowAll ? "Show less" : `Show all (${upcomingHearings.length})`}
                </Button>
              )}
            </div>
          )}

          {/* Past Hearings -- collapsed by default */}
          {pastHearings.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-medium text-gray-700 uppercase tracking-wide">
                  Past ({pastHearings.length})
                </h4>
                <CollapseToggle isOpen={pastOpen} onToggle={() => setPastOpen((v) => !v)} />
              </div>
              <Collapsible isOpen={pastOpen}>
                <div
                  className={
                    pastShowAll ? "max-h-[480px] overflow-y-auto pr-1 space-y-3" : "space-y-3"
                  }
                >
                  {visiblePast.map((hearing, i) => (
                    <HearingItem
                      key={hearing.id}
                      hearing={hearing}
                      index={i}
                      onEdit={onEditHearing}
                      onDelete={onDeleteHearing}
                      isDeleting={deletingId === hearing.id}
                    />
                  ))}
                </div>
                {pastHearings.length > DEFAULT_VISIBLE_COUNT && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full mt-2"
                    onClick={() => setPastShowAll((v) => !v)}
                  >
                    {pastShowAll ? "Show less" : `Show all (${pastHearings.length})`}
                  </Button>
                )}
              </Collapsible>
            </div>
          )}

          {/* Empty State */}
          {hearings.length === 0 && (
            <div className="text-center py-8">
              <Calendar className="h-12 w-12 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-500 text-sm">No hearings scheduled</p>
              <Button variant="secondary" size="sm" className="mt-3" onClick={onAddHearing}>
                <Plus className="h-4 w-4" />
                Schedule First Hearing
              </Button>
            </div>
          )}
        </CardContent>
      </Collapsible>
    </Card>
  );
}

interface HearingItemProps {
  hearing: Hearing;
  isUpcoming?: boolean;
  onEdit?: (hearing: Hearing) => void;
  onDelete?: (id: number) => void;
  isDeleting?: boolean;
  /** Position within its (upcoming/past) list, for a stagger-in delay. */
  index?: number;
}

function HearingItem({ hearing, isUpcoming, onEdit, onDelete, isDeleting, index = 0 }: HearingItemProps) {
  return (
    <div
      style={staggerDelay(index)}
      className="p-3.5 border border-gray-100 rounded-lg transition-colors hover:bg-gray-50 animate-fade-up motion-reduce:animate-none"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {/* Date and Type */}
          <div className="flex items-center gap-2 mb-2">
            <div className="text-sm font-medium text-gray-900">
              {formatDateTime(hearing.hearing_date)}
            </div>
            <span className="text-[11px] font-semibold bg-[#f3ecfb] text-[#6b3aa0] h-5 px-2 inline-flex items-center rounded-full">
              {hearing.hearing_type_display}
            </span>
            <span className="text-[11px] font-semibold bg-gray-100 text-[#4b5468] h-5 px-2 inline-flex items-center rounded-full">
              {hearing.source === "manual" ? "Manual" : "eCourts"}
            </span>
          </div>

          {/* Details */}
          <div className="space-y-1">
            {hearing.location && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <MapPin className="h-4 w-4" />
                <span>{hearing.location}</span>
              </div>
            )}
            {hearing.judge && (
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <User className="h-4 w-4" />
                <span>{hearing.judge}</span>
              </div>
            )}
          </div>

          {/* Status and Outcome */}
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge status={hearing.status} />
          </div>

          {hearing.outcome && (
            <div className="mt-3 text-sm text-gray-700 italic">
              <strong>Outcome:</strong> {hearing.outcome}
            </div>
          )}

          {hearing.notes && (
            <div className="mt-2 text-sm text-gray-600">📝 {hearing.notes}</div>
          )}
        </div>

        {/* Actions -- eCourts-sourced hearings are edited via Court Tracking
            refresh, not manually, so only manual hearings get edit/delete. */}
        {hearing.source === "manual" && (
          <div className="flex items-center gap-1 ml-4">
            <Button
              variant="ghost"
              size="sm"
              className="p-2"
              onClick={() => onEdit?.(hearing)}
              title="Edit hearing"
            >
              <Edit className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="p-2 text-destructive hover:text-destructive-hover"
              onClick={() => onDelete?.(hearing.id)}
              disabled={isDeleting}
              title="Delete hearing"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
