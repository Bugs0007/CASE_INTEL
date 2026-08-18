export type FeeStatus = "pending" | "invoiced" | "paid";
/** "logged" is the no-SMTP-configured path: the invoice was recorded as
 * delivered in the server log but no mail actually left the box. It is
 * deliberately distinct from "sent" -- never render it as delivered. */
export type FeeSendStatus = "not_sent" | "sent" | "logged";

export type BookingType = "travel" | "hotel" | "other";
export type BookingStatus = "pending" | "booked";

/** Compact fee shape embedded in a Hearing (see HearingSerializer). */
export interface NestedAppearanceFee {
  id: number;
  amount: string;
  status: FeeStatus;
  status_display: string;
  invoice_number: string;
  invoiced_at: string | null;
  paid_at: string | null;
  sent_at: string | null;
  send_status: FeeSendStatus;
}

export interface AppearanceFee extends NestedAppearanceFee {
  hearing: number;
  case_id: number;
  case_title: string;
  hearing_date: string;
  invoice_sequence: number | null;
  sent_to_email: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface AppearanceFeeCreateInput {
  hearing: number;
  /** Omit to fall back to the advocate profile's default_fee_amount. */
  amount?: string;
  notes?: string;
}

/** Compact booking shape embedded in a Hearing. */
export interface NestedTravelBooking {
  id: number;
  booking_type: BookingType;
  booking_type_display: string;
  status: BookingStatus;
  status_display: string;
  filename: string;
  created_at: string;
}

export interface TravelBooking extends NestedTravelBooking {
  hearing: number;
  case_id: number;
  file_type: string;
  file_size: number | null;
  notes: string;
  updated_at: string;
}

/** Amounts are decimal strings, not numbers -- the API serialises them
 * that way so money never round-trips through a float. */
export interface CaseFeeSummary {
  pending_amount: string;
  pending_count: number;
  invoiced_amount: string;
  invoiced_count: number;
  paid_amount: string;
  paid_count: number;
  /** pending + invoiced: money billed or billable but not yet received. */
  outstanding_amount: string;
  total_amount: string;
}

export interface AdvocateProfile {
  id: number;
  letterhead_name: string;
  address: string;
  bar_registration_number: string;
  /** Billing/contact email -- separate from the account's login email.
   * Used as Reply-To and Cc on invoice emails; empty is a valid state. */
  contact_email: string;
  default_fee_amount: string;
  invoice_prefix: string;
  last_invoice_sequence: number;
  created_at: string;
  updated_at: string;
}

export interface AdvocateProfileUpdateInput {
  letterhead_name?: string;
  address?: string;
  bar_registration_number?: string;
  contact_email?: string;
  default_fee_amount?: string;
  invoice_prefix?: string;
}

/** POST /api/appearance-fees/<id>/send/ -- returns 200 with sent=false
 * (not an error) when SMTP isn't configured. */
export interface SendInvoiceResult {
  sent: boolean;
  recipient: string;
  detail: string;
  /** Mail settings still blank on the server (empty when sent=true). */
  missing_env_vars: string[];
  /** The full env-var checklist for enabling real delivery. */
  required_env_vars: string[];
  fee: AppearanceFee;
}
