import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { dailyStatusKeys, useDailyStatus } from "@/hooks/use-daily-status";
import { useRetryOrderCheck } from "@/hooks/use-order-sync";
import { istDayKey } from "@/lib/dashboard/dates";
import {
  checkErrorNote,
  hearingBusinessInfo,
  indexBusinessByDate,
  listedBusinessDays,
  type HearingBusinessInfo,
} from "@/lib/hearing-business";
import { isOrderSyncActive } from "@/lib/order-sync";
import type { Case, Hearing, OrderSyncState } from "@/types";

/** The "Check now" button's state, shared by every hearing of the case: the
 * server's order check is one job per case, not per hearing. */
export interface HearingBusinessCheck {
  /** The case is tracked, so a check can be queued. */
  canCheck: boolean;
  /** A check is being queued, waiting or running. */
  checking: boolean;
  /** A check started here has finished: a date still missing after it is
   * beyond what one check saves (a few newest days at a time). */
  checkedSince: boolean;
  /** A line about a refused or failed attempt (the server's cooldown). */
  note: string | null;
  request: () => void;
}

export interface HearingBusinessData {
  /** A district case: the hearings can carry what the court recorded. */
  enabled: boolean;
  infoFor: (hearing: Hearing) => HearingBusinessInfo;
  check: HearingBusinessCheck;
  /** Reload the entries after a failed read. */
  reload: () => void;
}

/** What the court recorded at each hearing of a district case, joined to the
 * hearings by day, plus the "Check now" control for the ones not saved yet.
 *
 * One request per case (the daily-status list). "Check now" queues the
 * server's ordinary order check -- the same one as the Retry button, with its
 * cooldown -- which also saves a few missing business dates. The page already
 * re-reads the case every few seconds while that check is queued or running;
 * when it settles the entries are read again. Nothing here reaches the portal. */
export function useHearingBusiness(
  caseItem: Case | undefined,
  hearings: readonly Hearing[],
): HearingBusinessData {
  const caseId = caseItem?.id ?? 0;
  const enabled = caseItem?.court_type === "district";
  const queryClient = useQueryClient();
  const daily = useDailyStatus(caseId, enabled);
  const { mutate: queueCheck, isPending: queuing } = useRetryOrderCheck(caseId);
  const state = caseItem?.order_sync?.state;

  const [note, setNote] = useState<string | null>(null);
  const [checkedSince, setCheckedSince] = useState(false);
  const asked = useRef(false);
  const previous = useRef<OrderSyncState | undefined>(undefined);

  // The check settled: read the entries again.
  useEffect(() => {
    const before = previous.current;
    previous.current = state;
    if (!enabled || !isOrderSyncActive(before) || isOrderSyncActive(state)) return;
    queryClient.invalidateQueries({ queryKey: dailyStatusKeys.list(caseId) });
    if (asked.current) {
      asked.current = false;
      setCheckedSince(true);
      if (state === "failed") setNote("The check could not finish. Try again in a few minutes.");
    }
  }, [state, enabled, caseId, queryClient]);

  const request = useCallback(() => {
    setNote(null);
    setCheckedSince(false);
    asked.current = true;
    queueCheck(undefined, {
      onError: (error) => {
        asked.current = false;
        setNote(checkErrorNote(error));
      },
    });
  }, [queueCheck]);

  const status = daily.isError ? "error" : daily.isLoading ? "loading" : "ready";
  const index = useMemo(() => indexBusinessByDate(daily.data), [daily.data]);
  const listed = useMemo(() => listedBusinessDays(hearings), [hearings]);
  const today = istDayKey();

  const tracked = !!caseItem?.tracking_enabled;
  const infoFor = useCallback(
    (hearing: Hearing): HearingBusinessInfo => {
      const info = hearingBusinessInfo(hearing, { enabled, status, index, listed, today });
      // An untracked case never gets its business saved: no "not saved yet" to offer.
      return !tracked && (info.kind === "missing" || info.kind === "unlisted") ? { kind: "none" } : info;
    },
    [enabled, status, index, listed, today, tracked],
  );

  const { refetch } = daily;
  const reload = useCallback(() => void refetch(), [refetch]);

  return {
    enabled,
    infoFor,
    reload,
    check: {
      canCheck: tracked,
      checking: queuing || isOrderSyncActive(state),
      checkedSince,
      note,
      request,
    },
  };
}
