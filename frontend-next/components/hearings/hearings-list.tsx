"use client";

import { useMemo, useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { CauseListBadge } from "@/components/hearings/cause-list-badge";
import { Collapsible } from "@/components/ui/collapsible";
import { formatDateTime, staggerDelay } from "@/lib/utils";
import { groupOrdersByDate, hearingDateKey } from "@/hooks/use-court-orders";
import {
  Calendar,
  MapPin,
  User,
  Plus,
  Edit,
  Trash2,
  Loader2,
  FileText,
  Plane,
} from "lucide-react";
import type {
  CourtOrder,
  FeeStatus,
  Hearing,
  NestedAppearanceFee,
  NestedTravelBooking,
} from "@/types";

const DEFAULT_VISIBLE_COUNT = 5;

interface HearingsListProps {
  caseId: number;
  hearings: Hearing[];
  isLoading?: boolean;
  onAddHearing?: () => void;
  onEditHearing?: (hearing: Hearing) => void;
  onDeleteHearing?: (id: number) => void;
  deletingId?: number;
  /** All of the case's court orders; bucketed by date here so each card
      can show the order(s) filed on its own hearing date. */
  orders?: CourtOrder[];
  onViewOrder?: (orderId: number) => void;
  viewingOrderId?: number;
}

export function HearingsList({
  caseId,
  hearings,
  isLoading,
  onAddHearing,
  onEditHearing,
  onDeleteHearing,
  deletingId,
  orders = [],
  onViewOrder,
  viewingOrderId,
}: HearingsListProps) {
  const ordersByDate = useMemo(() => groupOrdersByDate(orders), [orders]);
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
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
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
                    orders={ordersByDate.get(hearingDateKey(hearing.hearing_date))}
                    onViewOrder={onViewOrder}
                    viewingOrderId={viewingOrderId}
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
                      orders={ordersByDate.get(hearingDateKey(hearing.hearing_date))}
                      onViewOrder={onViewOrder}
                      viewingOrderId={viewingOrderId}
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
  /** Court orders filed on this hearing's date, already in portal
      sequence (the API sorts them). */
  orders?: CourtOrder[];
  onViewOrder?: (orderId: number) => void;
  viewingOrderId?: number;
}

function HearingItem({
  hearing,
  isUpcoming,
  onEdit,
  onDelete,
  isDeleting,
  index = 0,
  orders,
  onViewOrder,
  viewingOrderId,
}: HearingItemProps) {
  return (
    <div
      style={staggerDelay(index)}
      className="p-3.5 border border-gray-100 rounded-lg transition-colors hover:bg-gray-50 animate-fade-up motion-reduce:animate-none"
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {/* Date and Type -- flex-wrap so a long hearing type (e.g.
              "Status Conference") wraps the badge to its own line instead of
              squeezing it and the date until the badge's own text wraps and
              breaks its pill shape. */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <div className="text-sm font-medium text-gray-900 flex-shrink-0">
              {formatDateTime(hearing.hearing_date)}
            </div>
            <span className="text-[11px] font-semibold bg-[#f3ecfb] text-[#6b3aa0] h-5 px-2 inline-flex items-center flex-shrink-0 whitespace-nowrap rounded-full">
              {hearing.hearing_type_display}
            </span>
            <span className="text-[11px] font-semibold bg-gray-100 text-[#4b5468] h-5 px-2 inline-flex items-center flex-shrink-0 whitespace-nowrap rounded-full">
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

          {/* Status, fee badge and travel state */}
          <div className="mt-2 flex items-center gap-2 flex-wrap">
            <StatusBadge status={hearing.status} />
            <CauseListBadge hearing={hearing} />
            <FeeBadge fee={hearing.appearance_fee} />
            <TravelBadge bookings={hearing.travel_bookings} />
          </div>

          {hearing.outcome && (
            <div className="mt-3 text-sm text-gray-700 italic">
              <strong>Outcome:</strong> {hearing.outcome}
            </div>
          )}

          {hearing.notes && (
            <div className="mt-2 text-sm text-gray-600">📝 {hearing.notes}</div>
          )}

          {/* Order PDFs filed on this date. A date routinely carries more
              than one, so a single order gets one button and several get a
              labelled stack rather than a row of identical buttons. */}
          <HearingOrders
            orders={orders}
            onViewOrder={onViewOrder}
            viewingOrderId={viewingOrderId}
          />
        </div>

        {/* Actions -- eCourts-sourced hearings are edited via Court Tracking
            refresh, not manually, so only manual hearings get edit/delete. */}
        {hearing.source === "manual" && (
          <div className="flex items-center gap-1 ml-4">
            <Button
              variant="ghost"
              size="sm"
              className="p-2 w-11 md:w-8"
              onClick={() => onEdit?.(hearing)}
              title="Edit hearing"
            >
              <Edit className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="p-2 w-11 md:w-8 text-destructive hover:text-destructive-hover"
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

const FEE_BADGE_STYLES: Record<FeeStatus, string> = {
  pending: "bg-[#fdf3e3] text-[#8a5a0b]",
  invoiced: "bg-[#eef1fb] text-[#33449b]",
  paid: "bg-[#e6f6ed] text-[#1d6b3f]",
};

/** The fee state for this hearing, at a glance.
 *
 * Renders nothing when no fee has been recorded -- an absent fee is not
 * the same as a zero one, and a badge on every hearing whether or not
 * the advocate uses invoicing would just be noise. */
function FeeBadge({ fee }: { fee: NestedAppearanceFee | null }) {
  if (!fee) return null;

  // Amounts arrive as decimal strings so money never round-trips
  // through a float; format for display only.
  const amount = Number(fee.amount);
  const formatted = Number.isFinite(amount)
    ? amount.toLocaleString("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 0,
      })
    : fee.amount;

  const title =
    fee.status === "paid"
      ? `Paid${fee.invoice_number ? ` (invoice ${fee.invoice_number})` : ""}`
      : fee.status === "invoiced"
        ? `Invoiced as ${fee.invoice_number}${
            // "logged" means the server had no SMTP configured -- say so
            // rather than letting it read as delivered.
            fee.send_status === "sent"
              ? ", emailed to the billing contact"
              : fee.send_status === "logged"
                ? ", logged only (email not configured on the server)"
                : ", not yet sent"
          }`
        : "Fee recorded, not yet invoiced";

  return (
    <span
      title={title}
      className={`text-[11px] font-semibold h-5 px-2 inline-flex items-center flex-shrink-0 whitespace-nowrap rounded-full ${FEE_BADGE_STYLES[fee.status]}`}
    >
      {formatted} · {fee.status_display}
    </span>
  );
}

/** Travel/hotel bookings for this hearing. Collapses to one badge --
 * the detail belongs on the booking list, not the hearing card. */
function TravelBadge({ bookings }: { bookings: NestedTravelBooking[] }) {
  if (!bookings || bookings.length === 0) return null;

  const booked = bookings.filter((b) => b.status === "booked").length;
  const allBooked = booked === bookings.length;

  return (
    <span
      title={bookings
        .map((b) => `${b.booking_type_display}: ${b.status_display}`)
        .join(" · ")}
      className={`text-[11px] font-semibold h-5 px-2 inline-flex items-center gap-1 flex-shrink-0 whitespace-nowrap rounded-full ${
        allBooked ? "bg-[#e6f6ed] text-[#1d6b3f]" : "bg-[#fdf3e3] text-[#8a5a0b]"
      }`}
    >
      <Plane className="h-3 w-3" />
      {allBooked ? `Travel booked${bookings.length > 1 ? ` (${booked})` : ""}` : `Travel ${booked}/${bookings.length}`}
    </span>
  );
}

interface HearingOrdersProps {
  orders?: CourtOrder[];
  onViewOrder?: (orderId: number) => void;
  viewingOrderId?: number;
}

/** The order PDF(s) filed on a hearing's date.
 *
 * Orders arrive already sorted in portal sequence from the API. Each opens
 * in a new tab via GET /api/orders/<id>/file/, which streams the bytes
 * behind an ownership check -- there is no direct file URL to link to, so
 * the click goes through the fetch-to-blob path in useViewOrder(). */
function HearingOrders({ orders, onViewOrder, viewingOrderId }: HearingOrdersProps) {
  // has_file is false when the underlying Document row is gone -- the
  // serve endpoint would 404, so don't offer a button at all.
  const openable = (orders ?? []).filter((order) => order.has_file);
  if (openable.length === 0) return null;

  if (openable.length === 1) {
    const order = openable[0];
    return (
      <div className="mt-3">
        <OrderButton
          order={order}
          label="Order"
          onViewOrder={onViewOrder}
          isViewing={viewingOrderId === order.id}
        />
      </div>
    );
  }

  return (
    <div className="mt-3">
      <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
        Orders ({openable.length})
      </div>
      <div className="flex flex-wrap gap-1.5">
        {openable.map((order) => (
          <OrderButton
            key={order.id}
            order={order}
            label={`Order ${order.order_number}`}
            onViewOrder={onViewOrder}
            isViewing={viewingOrderId === order.id}
          />
        ))}
      </div>
    </div>
  );
}

interface OrderButtonProps {
  order: CourtOrder;
  label: string;
  onViewOrder?: (orderId: number) => void;
  isViewing?: boolean;
}

function OrderButton({ order, label, onViewOrder, isViewing }: OrderButtonProps) {
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => onViewOrder?.(order.id)}
      disabled={isViewing}
      title={order.description || `Open ${label} (PDF, opens in a new tab)`}
    >
      {isViewing ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <FileText className="h-4 w-4" />
      )}
      {label}
    </Button>
  );
}
