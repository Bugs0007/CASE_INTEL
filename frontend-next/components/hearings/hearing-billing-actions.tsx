"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, FileText, Loader2, Plane, Send, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import { APIError } from "@/lib/api/client";
import {
  useAdvocateProfile,
  useCreateFee,
  useGenerateInvoice,
  useMarkPaid,
  useSendInvoice,
  useUploadTravelBooking,
  useViewInvoice,
} from "@/hooks/use-billing";
import type { BookingType, Hearing } from "@/types";

/** Pull the server's own message out of a DRF error body, so the user
 * sees "This case has no billing contact..." rather than a generic
 * failure. Every endpoint here returns {detail: "..."} on 4xx. */
function errorDetail(error: unknown, fallback: string): string {
  if (error instanceof APIError && error.data && typeof error.data === "object") {
    const detail = (error.data as { detail?: string }).detail;
    if (detail) return detail;
  }
  return fallback;
}

interface HearingBillingActionsProps {
  hearing: Hearing;
  caseId: number;
}

/** The real appearance-fee lifecycle and travel upload for one hearing.
 *
 * The fee badge above this row shows STATE; these are the actions that
 * move it: record -> generate invoice -> send -> mark paid, each calling
 * the live endpoint. Which buttons exist is driven by the fee's current
 * status, mirroring the server's forward-only transitions (invoice_service
 * rejects paying an un-invoiced fee, so there is no button for it). */
export function HearingBillingActions({ hearing, caseId }: HearingBillingActionsProps) {
  const fee = hearing.appearance_fee;
  const [amount, setAmount] = useState("");
  const [bookingType, setBookingType] = useState<BookingType>("travel");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: advocateProfile } = useAdvocateProfile();
  // Undefined while the profile is still loading -- don't flash the
  // warning before we actually know it's missing.
  const contactEmailMissing =
    advocateProfile !== undefined && !advocateProfile.contact_email;

  const createFee = useCreateFee(caseId);
  const generateInvoice = useGenerateInvoice(caseId);
  const sendInvoice = useSendInvoice(caseId);
  const markPaid = useMarkPaid(caseId);
  const viewInvoice = useViewInvoice();
  const uploadTravel = useUploadTravelBooking(caseId);

  async function handleCreateFee() {
    try {
      await createFee.mutateAsync({
        hearing: hearing.id,
        // Blank means "use the profile's default_fee_amount" -- the
        // server applies that fallback, so don't send "0" here.
        ...(amount.trim() ? { amount: amount.trim() } : {}),
      });
      setAmount("");
      showToast.success("Fee recorded", "Generate an invoice when you're ready to bill it.");
    } catch (error) {
      showToast.error("Could not record the fee", errorDetail(error, "Please try again."));
    }
  }

  async function handleGenerate() {
    if (!fee) return;
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
    if (!fee) return;
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
    if (!fee) return;
    try {
      await markPaid.mutateAsync(fee.id);
      showToast.success("Marked paid", "The fee is settled.");
    } catch (error) {
      // 409 when the fee isn't invoiced yet or is already paid.
      showToast.error("Could not mark it paid", errorDetail(error, "Please try again."));
    }
  }

  function handleView() {
    if (!fee) return;
    viewInvoice.mutate(fee.id, {
      onError: (error) =>
        showToast.error("Could not open the invoice", errorDetail(error, "Please try again.")),
    });
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
    <div className="mt-3 flex flex-wrap items-center gap-2">
      {!fee && (
        <>
          <Input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Fee amount"
            inputMode="decimal"
            aria-label="Fee amount"
            className="h-11 md:h-8 w-32 text-sm"
          />
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCreateFee}
            disabled={createFee.isPending}
            title="Record an appearance fee for this hearing"
          >
            {createFee.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            Record fee
          </Button>
        </>
      )}

      {fee?.status === "pending" && (
        <Button size="sm" onClick={handleGenerate} disabled={generateInvoice.isPending}>
          {generateInvoice.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          Generate Invoice
        </Button>
      )}

      {fee?.status === "invoiced" && (
        <>
          {contactEmailMissing ? (
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
          ) : (
            <Button size="sm" onClick={handleSend} disabled={sendInvoice.isPending}>
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
          >
            {markPaid.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Mark Paid
          </Button>
        </>
      )}

      {fee && fee.status !== "pending" && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleView}
          disabled={viewInvoice.isPending}
          title="Open the invoice PDF in a new tab"
        >
          {viewInvoice.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          View PDF
        </Button>
      )}

      {/* Travel/hotel confirmation. Uploading the file is what marks the
          booking BOOKED -- there is no separate status control. */}
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
  );
}
