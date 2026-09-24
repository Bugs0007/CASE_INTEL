"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Loader2, MailWarning } from "lucide-react";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { useUpdateCase } from "@/hooks/use-cases";
import { apiErrorDetail } from "@/lib/api/client";
import { formatHearingDate } from "@/lib/utils";
import type { Case } from "@/types";

const OPEN_STATUSES = new Set(["open", "pending"]);

function dismissKey(caseItem: Case): string | null {
  const d = caseItem.disposal;
  return d ? `case_intel_disposal_dismissed:${caseItem.id}:${d.source}:${d.order_id ?? d.detail}` : null;
}

function readDismissed(key: string | null): boolean {
  if (!key) return false;
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

/** "This case looks disposed of -- close it?" Shown when the latest order
 * disposes of the case or eCourts lists it as disposed, while the case is
 * still open here. Never closes anything on its own. "Not now" is
 * remembered per viewer for this particular signal (a later disposing
 * order asks again). */
export function DisposalBanner({ caseItem }: { caseItem: Case }) {
  const updateCase = useUpdateCase();
  const key = dismissKey(caseItem);
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => setDismissed(readDismissed(key)), [key]);

  const disposal = caseItem.disposal;
  if (!disposal || !OPEN_STATUSES.has(caseItem.status) || dismissed) return null;

  const what =
    disposal.source === "order"
      ? `The order of ${disposal.order_date ? formatHearingDate(disposal.order_date) : "the latest hearing"} disposes of this case.`
      : `eCourts lists this case as disposed${disposal.detail ? ` (${disposal.detail})` : ""}.`;

  async function handleClose() {
    try {
      await updateCase.mutateAsync({ id: caseItem.id, data: { status: "closed" } });
      showToast.success("Case closed", "You can reopen it from Edit Details at any time.");
    } catch (error) {
      showToast.error("Could not close the case", apiErrorDetail(error, "Please try again."));
    }
  }

  function handleDismiss() {
    try {
      if (key) window.localStorage.setItem(key, "1");
    } catch {
      // Storage unavailable: dismiss for this view only.
    }
    setDismissed(true);
  }

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-3 rounded-xl border border-status-ok bg-status-ok-soft px-4 py-3 text-sm text-gray-800"
    >
      <CheckCircle2 className="h-5 w-5 flex-shrink-0 text-status-ok" />
      <div className="min-w-0 flex-1">
        <div className="font-medium text-gray-900">{what}</div>
        <div className="text-xs text-gray-600">
          Close the case here once you&apos;ve checked -- client updates will say the matter was disposed of.
        </div>
      </div>
      <div className="flex gap-2">
        <Button variant="ghost" size="sm" onClick={handleDismiss}>
          Not now
        </Button>
        <Button size="sm" onClick={handleClose} disabled={updateCase.isPending}>
          {updateCase.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
          Close case
        </Button>
      </div>
    </div>
  );
}

/** Nobody on this case can receive case-update emails, so none are
 * drafted. Says so where the drafts would have been, instead of a pile of
 * unsendable drafts. Only on tracked cases -- that's where updates come
 * from. */
export function UpdateRecipientsNote({
  caseItem,
  onEditDetails,
}: {
  caseItem: Case;
  onEditDetails: () => void;
}) {
  if (!caseItem.tracking_enabled || caseItem.update_recipient_count !== 0) return null;
  if (!OPEN_STATUSES.has(caseItem.status)) return null;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-surface px-4 py-3 text-sm">
      <MailWarning className="h-5 w-5 flex-shrink-0 text-gray-400" />
      <div className="min-w-0 flex-1">
        <div className="font-medium text-gray-900">Add a client email to get update drafts</div>
        <div className="text-xs text-gray-600">
          After each hearing, a ready-to-send update for your client is drafted here -- but no contact on
          this case has an email address (or they&apos;ve opted out).
        </div>
      </div>
      <Button variant="secondary" size="sm" onClick={onEditDetails}>
        Add client email
      </Button>
    </div>
  );
}
