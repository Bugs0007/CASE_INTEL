import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatDateTime, staggerDelay } from "@/lib/utils";
import { Calendar, MapPin, User, Plus, Edit, Trash2, Loader2 } from "lucide-react";
import type { Hearing } from "@/types";

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
  const now = new Date();
  const upcomingHearings = hearings.filter(
    (h) => new Date(h.hearing_date) >= now && h.status === "scheduled",
  );
  const pastHearings = hearings.filter(
    (h) => new Date(h.hearing_date) < now || h.status !== "scheduled",
  );

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

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Hearings & Deadlines</CardTitle>
        <Button variant="secondary" size="sm" onClick={onAddHearing}>
          <Plus className="h-4 w-4" />
          Add Hearing
        </Button>
      </CardHeader>
      <CardContent>
        {/* Upcoming Hearings */}
        {upcomingHearings.length > 0 && (
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-700 mb-3 uppercase tracking-wide">
              Upcoming
            </h4>
            <div className="space-y-3">
              {upcomingHearings.map((hearing, i) => (
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
          </div>
        )}

        {/* Past Hearings */}
        {pastHearings.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-gray-700 mb-3 uppercase tracking-wide">
              Past
            </h4>
            <div className="space-y-3">
              {pastHearings.map((hearing, i) => (
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
