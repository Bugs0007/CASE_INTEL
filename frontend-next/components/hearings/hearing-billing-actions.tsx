"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, FileText, Loader2, Plane, Plus, Send, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import { APIError } from "@/lib/api/client";
import { formatFeeAmount } from "@/lib/utils";
import {
  useAdvocateProfile,
  useCreateFee,
  useGenerateInvoice,
  useMarkPaid,
  useSendInvoice,
  useUploadTravelBooking,
  useViewInvoice,
} from "@/hooks/use-billing";
import type { BookingType, FeeCategory, Hearing, NestedAppearanceFee } from "@/types";

/** What each kind of charge is called in the picker, in the order it is
 * offered. Mirrors AppearanceFee.CATEGORY_CHOICES on the server. */
const CATEGORY_OPTIONS: { value: FeeCategory; label: string }[] = [
  { value: "appearance", label: "Appearance Fee" },
  { value: "hotel", label: "Hotel" },
  { value: "flight", label: "Flight" },
  { value: "other", label: "Other" },
];

/** Pull the server's own message out of a DRF error body, so the user
 * sees "This case has no billing contact..." rather than a generic
 * failure. The lifecycle endpoints answer {detail: "..."} on 4xx; a
 * rejected form field (say a malformed amount) answers {field: ["..."]},
 * so fall back to the first of those before giving up. */
function errorDetail(error: unknown, fallback: string): string {
  if (error instanceof APIError && error.data && typeof error.data === "object") {
    const body = error.data as Record<string, unknown>;
    if (typeof body.detail === "string" && body.detail) return body.detail;
    for (const value of Object.values(body)) {
      const message = Array.isArray(value) ? value[0] : value;
      if (typeof message === "string" && message) return message;
    }
  }
  return fallback;
}

interface HearingBillingActionsProps {
  hearing: Hearing;
  caseId: number;
}

/** The billable charges on one hearing, plus travel upload.
 *
 * A hearing can carry several charges -- the appearance fee, a hotel bill,
 * a flight, anything that was missed -- each with its own invoice and its
 * own lifecycle. The form at the top adds one; each row below it then
 * moves that ONE charge through generate invoice -> send -> mark paid,
 * calling the live endpoints. Which buttons a row has is driven by that
 * charge's own status, mirroring the server's forward-only transitions
 * (invoice_service rejects paying an un-invoiced fee, so there is no
 * button for it).
 *
 * The fee badges above this block show STATE; this is where it changes. */
export function HearingBillingActions({ hearing, caseId }: HearingBillingActionsProps) {
  const fees = hearing.appearance_fees;
  const [category, setCategory] = useState<FeeCategory>("appearance");
  const [amount, setAmount] = useState("");
  const [bookingType, setBookingType] = useState<BookingType>("travel");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: advocateProfile } = useAdvocateProfile();
  // Undefined while the profile is still loading -- don't flash the
  // warning before we actually know it's missing.
  const contactEmailMissing =
    advocateProfile !== undefined && !advocateProfile.contact_email;
  // One warning for the block, not one per row: several invoiced charges
  // are exactly the case this UI exists for.
  const showContactEmailWarning =
    contactEmailMissing && fees.some((fee) => fee.status === "invoiced");

  const createFee = useCreateFee(caseId);
  const uploadTravel = useUploadTravelBooking(caseId);

  async function handleAddCharge() {
    const trimmed = amount.trim();
    // Only an appearance fee has a default amount (the profile's
    // default_fee_amount, applied by the server). Billing anything else at
    // that rate would be wrong money, so the server refuses it too -- this
    // just answers before the round trip.
    if (category !== "appearance" && !trimmed) {
      showToast.error(
        "Enter an amount",
        "Only an appearance fee has a default amount. Enter what this charge costs.",
      );
      return;
    }

    try {
      await createFee.mutateAsync({
        hearing: hearing.id,
        category,
        // Blank means "use the profile's default_fee_amount" (appearance
        // only) -- the server applies that fallback, so don't send "0".
        ...(trimmed ? { amount: trimmed } : {}),
      });
      setAmount("");
      showToast.success("Charge added", "Generate an invoice when you're ready to bill it.");
    } catch (error) {
      showToast.error("Could not add the charge", errorDetail(error, "Please try again."));
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Reset immediately so re-picking the SAME file still fires a change
    // event (the input keeps its value otherwise and the second upload
    // silently does nothing).
    event.target.value = "";
    if (!file) return;

    try {
      await uploadTravel.mutateAsync({
        file,
        hearing_id: hearing.id,
        booking_type: bookingType,
      });
      showToast.success("Booking uploaded", "This hearing is marked as booked.");
    } catch (error) {
      showToast.error("Upload failed", errorDetail(error, "Please try again."));
    }
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={category}
          onChange={(e) => setCategory(e.target.value as FeeCategory)}
          aria-label="Charge category"
          // py-0: at md+ the box is h-8, and Select's own py-2 would leave
          // a 14px content area for 20px text, clipping the label.
          className="h-11 md:h-8 w-40 py-0 text-sm"
        >
          {CATEGORY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Input
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder={category === "appearance" ? "Amount (optional)" : "Amount"}
          inputMode="decimal"
          aria-label="Charge amount"
          className="h-11 md:h-8 w-40 text-sm"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={handleAddCharge}
          disabled={createFee.isPending}
          title="Add a charge to this hearing"
        >
          {createFee.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Add charge
        </Button>
      </div>

      {fees.length > 0 && (
        <ul aria-label="Charges" className="space-y-1.5">
          {fees.map((fee) => (
            <ChargeRow key={fee.id} fee={fee} caseId={caseId} canSend={!contactEmailMissing} />
          ))}
        </ul>
      )}

      {showContactEmailWarning && (
        <div
          className="flex items-center gap-1.5 rounded-md bg-status-alert-soft px-2.5 py-1.5 text-sm text-status-alert"
          title="Set a contact email in Settings so clients can reply directly to you."
        >
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          <span>No contact email set.</span>
          <Link href="/settings" className="font-medium underline">
            Add it in Settings
          </Link>
        </div>
      )}

      {/* Travel/hotel confirmation. Uploading the file is what marks the
          booking BOOKED -- there is no separate status control. This is a
          document upload, separate from the billable charges above: what a
          hotel COST is a charge; the confirmation PDF is a booking. */}
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={bookingType}
          onChange={(e) => setBookingType(e.target.value as BookingType)}
          aria-label="Booking type"
          className="h-11 md:h-8 w-24 text-sm"
        >
          <option value="travel">Travel</option>
          <option value="hotel">Hotel</option>
          <option value="other">Other</option>
        </Select>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          aria-label="Booking confirmation file"
          onChange={handleFileChange}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadTravel.isPending}
          title="Upload a ticket or hotel confirmation for this hearing"
        >
          {uploadTravel.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <Plane className="h-4 w-4" />
              <Upload className="h-3 w-3" />
            </>
          )}
          Upload booking
        </Button>
      </div>
    </div>
  );
}

interface ChargeRowProps {
  fee: NestedAppearanceFee;
  caseId: number;
  /** False when the advocate has no contact email set: the Send button is
   * withheld (the block shows one warning saying why). */
  canSend: boolean;
}

/** One charge and the actions available to it right now.
 *
 * Its own component, so every row owns its own mutations: generating the
 * hotel invoice shows a spinner on the hotel row only, and never disables
 * the appearance fee's buttons next to it. */
function ChargeRow({ fee, caseId, canSend }: ChargeRowProps) {
  const generateInvoice = useGenerateInvoice(caseId);
  const sendInvoice = useSendInvoice(caseId);
  const markPaid = useMarkPaid(caseId);
  const viewInvoice = useViewInvoice();

  // Every row carries the same buttons, so name each for its charge -- a
  // screen reader hears "Mark Paid (Hotel)", not "Mark Paid" three times.
  const forThisCharge = (label: string) => `${label} (${fee.category_display})`;

  async function handleGenerate() {
    try {
      const updated = await generateInvoice.mutateAsync(fee.id);
      showToast.success(
        `Invoice ${updated.invoice_number} generated`,
        "Send it to the billing contact, or open the PDF.",
      );
    } catch (error) {
      showToast.error(
        "Could not generate the invoice",
        errorDetail(error, "Please try again."),
      );
    }
  }

  async function handleSend() {
    try {
      const result = await sendInvoice.mutateAsync(fee.id);
      if (result.sent) {
        showToast.success("Invoice sent", `Emailed to ${result.recipient}.`);
      } else {
        // sent=false is a 200, not an error: the server has no mail
        // credentials and only LOGGED the delivery. Saying "sent" here
        // would be a lie the fee's own send_status contradicts.
        showToast.warning(
          "Invoice logged, not emailed",
          result.missing_env_vars?.length
            ? `${result.detail} Missing: ${result.missing_env_vars.join(", ")}.`
            : result.detail,
        );
      }
    } catch (error) {
      showToast.error("Could not send the invoice", errorDetail(error, "Please try again."));
    }
  }

  async function handleMarkPaid() {
    try {
      await markPaid.mutateAsync(fee.id);
      showToast.success("Marked paid", "The charge is settled.");
    } catch (error) {
      // 409 when the fee isn't invoiced yet or is already paid.
      showToast.error("Could not mark it paid", errorDetail(error, "Please try again."));
    }
  }

  function handleView() {
    viewInvoice.mutate(fee.id, {
      onError: (error) =>
        showToast.error("Could not open the invoice", errorDetail(error, "Please try again.")),
    });
  }

  return (
    <li className="flex flex-wrap items-center gap-2 rounded-md border border-gray-100 px-2.5 py-1.5">
      <span className="text-sm font-medium text-gray-900">{fee.category_display}</span>
      <span className="font-mono text-sm text-gray-700">{formatFeeAmount(fee.amount)}</span>
      {/* "invoiced" reads as pending -- billed but not yet paid is the same
          ok/pending bucket as not-yet-billed, just further along. */}
      <span
        className={`ci-chip ci-chip--${fee.status === "paid" ? "ok" : "pending"} flex-shrink-0`}
      >
        {fee.status_display}
      </span>
      {fee.invoice_number && (
        <span className="text-xs text-gray-500">{fee.invoice_number}</span>
      )}

      {fee.status === "pending" && (
        <Button
          size="sm"
          onClick={handleGenerate}
          disabled={generateInvoice.isPending}
          aria-label={forThisCharge("Generate Invoice")}
        >
          {generateInvoice.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          Generate Invoice
        </Button>
      )}

      {fee.status === "invoiced" && (
        <>
          {canSend && (
            <Button
              size="sm"
              onClick={handleSend}
              disabled={sendInvoice.isPending}
              aria-label={forThisCharge("Send to Billing Contact")}
            >
              {sendInvoice.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
              Send to Billing Contact
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={handleMarkPaid}
            disabled={markPaid.isPending}
            aria-label={forThisCharge("Mark Paid")}
          >
            {markPaid.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Mark Paid
          </Button>
        </>
      )}

      {fee.status !== "pending" && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleView}
          disabled={viewInvoice.isPending}
          title="Open the invoice PDF in a new tab"
          aria-label={forThisCharge("View PDF")}
        >
          {viewInvoice.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          View PDF
        </Button>
      )}
    </li>
  );
}
