import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { advocateProfileApi, appearanceFeesApi, travelBookingsApi } from "@/lib/api/billing";
import { caseKeys } from "@/hooks/use-cases";
import { billingPortfolioKeys } from "@/hooks/use-clients";
import { hearingKeys } from "@/hooks/use-hearings";
import type {
  AdvocateProfileUpdateInput,
  AppearanceFee,
  AppearanceFeeCreateInput,
  BookingType,
  FeeCategory,
} from "@/types";

export const advocateProfileKeys = {
  all: ["advocate-profile"] as const,
};

/** Long enough for the new tab to have loaded the PDF before the object
 * URL is released. Same treatment as useViewOrder's order PDFs. */
const BLOB_REVOKE_DELAY_MS = 60_000;

export const billingFeeKeys = {
  all: ["appearance-fees"] as const,
  list: () => [...billingFeeKeys.all, "list"] as const,
};

/** Every fee/travel mutation changes data that is EMBEDDED in other
 * responses rather than fetched on its own:
 *   - hearing.appearance_fees / hearing.travel_bookings (HearingSerializer)
 *   - case.fee_summary (CaseSerializer)
 * so both caches have to be invalidated or the badge the user just acted
 * on keeps rendering its previous state. The Billing page's own fee list and
 * portfolio (unbilled hearings) are the same data again. */
function invalidateBilling(queryClient: QueryClient, caseId: number) {
  queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
  queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
  queryClient.invalidateQueries({ queryKey: billingFeeKeys.all });
  queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
}

/** Put fees the server just answered with into the Billing page's list, so a
 * row shows its new state before the refetch lands. */
function patchFeeList(queryClient: QueryClient, fees: AppearanceFee[]) {
  const answered = fees.filter((fee) => fee && typeof fee.id === "number");
  if (answered.length === 0) return;
  const byId = new Map(answered.map((fee) => [fee.id, fee]));
  queryClient.setQueryData<AppearanceFee[]>(billingFeeKeys.list(), (old) =>
    old?.map((fee) => byId.get(fee.id) ?? fee),
  );
}

// ---------------------------------------------------------------------------
// Advocate profile (invoice letterhead)
// ---------------------------------------------------------------------------

export function useAdvocateProfile() {
  return useQuery({
    queryKey: advocateProfileKeys.all,
    queryFn: () => advocateProfileApi.get(),
  });
}

export function useUpdateAdvocateProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: AdvocateProfileUpdateInput) => advocateProfileApi.update(data),
    onSuccess: (profile) => {
      // The PATCH response is the updated profile, so seed the cache with
      // it instead of triggering a second GET.
      queryClient.setQueryData(advocateProfileKeys.all, profile);
    },
  });
}

// ---------------------------------------------------------------------------
// Appearance fees -- the PENDING -> INVOICED -> PAID lifecycle
// ---------------------------------------------------------------------------

/** Record a charge against a hearing. A hearing can carry several -- one
 * per `category` or more. Omitting `amount` makes the server fall back to
 * the advocate profile's default_fee_amount, but only for an appearance
 * fee; any other category is rejected without an explicit amount. */
/** Every charge the advocate has recorded, on every case (the Billing page).
 * The server scopes it to the signed-in advocate. */
export function useBillingFees() {
  return useQuery({
    queryKey: billingFeeKeys.list(),
    queryFn: () => appearanceFeesApi.list(),
    staleTime: 30 * 1000,
  });
}

export function useCreateFee(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: AppearanceFeeCreateInput) => appearanceFeesApi.create(input),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}

export function useUpdateFee(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      ...data
    }: {
      id: number;
      amount?: string;
      notes?: string;
      category?: FeeCategory;
    }) =>
      appearanceFeesApi.update(id, data),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}

export function useDeleteFee(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feeId: number) => appearanceFeesApi.delete(feeId),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}

/** Generate (or re-render) the invoice PDF; moves the fee to INVOICED.
 * Re-running for an already-invoiced fee deliberately reuses the same
 * invoice number -- the server owns that rule. */
export function useGenerateInvoice(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feeId: number) => appearanceFeesApi.generateInvoice(feeId),
    onSuccess: (fee) => {
      patchFeeList(queryClient, [fee]);
      invalidateBilling(queryClient, caseId);
    },
  });
}

/** Email the invoice to the case's billing contact.
 *
 * Resolves (does NOT reject) with sent=false when the server has no mail
 * credentials -- the invoice is logged instead. Callers must branch on
 * result.sent rather than treating a resolved promise as delivery. */
export function useSendInvoice(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feeId: number) => appearanceFeesApi.send(feeId),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}

export function useMarkPaid(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (feeId: number) => appearanceFeesApi.markPaid(feeId),
    onSuccess: (fee) => {
      patchFeeList(queryClient, [fee]);
      invalidateBilling(queryClient, caseId);
    },
  });
}

export interface MarkPaidOutcome {
  paid: AppearanceFee[];
  /** The charges the server refused, with its error (a 409 carries the
   * reason: not invoiced yet, or already paid). */
  failed: { feeId: number; error: unknown }[];
}

/** Mark several charges paid (the Billing page: one, or all of a client's
 * invoiced ones), one request at a time -- the server has no bulk endpoint
 * and a refusal on one must not stop the rest.
 *
 * It RESOLVES with what happened instead of rejecting, so a half-done batch
 * is reported as exactly that. Paid fees go into the list at once; the
 * invalidation afterwards also corrects a charge the server refused because
 * it had changed elsewhere. */
export function useMarkFeesPaid() {
  const queryClient = useQueryClient();

  return useMutation<MarkPaidOutcome, unknown, { feeId: number; caseId: number }[]>({
    mutationFn: async (items) => {
      const outcome: MarkPaidOutcome = { paid: [], failed: [] };
      for (const { feeId } of items) {
        try {
          outcome.paid.push(await appearanceFeesApi.markPaid(feeId));
        } catch (error) {
          outcome.failed.push({ feeId, error });
        }
      }
      return outcome;
    },
    onSuccess: (outcome, items) => {
      patchFeeList(queryClient, outcome.paid);
      for (const caseId of new Set(items.map((item) => item.caseId))) {
        invalidateBilling(queryClient, caseId);
      }
    },
  });
}

/** Open the invoice PDF in a new tab.
 *
 * Mirrors useViewOrder: the endpoint streams bytes behind an ownership
 * check, so a plain <a href> can't carry the auth header -- fetch to a
 * blob and point a tab opened during the click gesture at it (opening it
 * after the await would be blocked as a popup). */
export function useViewInvoice() {
  return useMutation<string, unknown, number, { win: Window | null }>({
    mutationFn: async (feeId: number) => {
      const blob = await appearanceFeesApi.invoiceFile(feeId);
      return URL.createObjectURL(blob);
    },
    onMutate: () => ({
      win: typeof window !== "undefined" ? window.open("", "_blank") : null,
    }),
    onSuccess: (url, _feeId, context) => {
      if (context?.win) {
        context.win.location.href = url;
      } else if (typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      setTimeout(() => URL.revokeObjectURL(url), BLOB_REVOKE_DELAY_MS);
    },
    onError: (_err, _feeId, context) => {
      context?.win?.close();
    },
  });
}

// ---------------------------------------------------------------------------
// Travel bookings
// ---------------------------------------------------------------------------

/** Uploading the ticket/confirmation is what marks a booking BOOKED --
 * there is no separate "mark booked" call. */
export function useUploadTravelBooking(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (args: {
      file: File;
      hearing_id?: number;
      booking_id?: number;
      booking_type?: BookingType;
      notes?: string;
    }) => travelBookingsApi.upload(args),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}

export function useDeleteTravelBooking(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (bookingId: number) => travelBookingsApi.delete(bookingId),
    onSuccess: () => invalidateBilling(queryClient, caseId),
  });
}
