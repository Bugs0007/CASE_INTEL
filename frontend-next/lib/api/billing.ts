import { apiBlob, apiClient, uploadFile } from "./client";
import type {
  AdvocateProfile,
  AdvocateProfileUpdateInput,
  AppearanceFee,
  AppearanceFeeCreateInput,
  BookingType,
  FeeStatus,
  SendInvoiceResult,
  TravelBooking,
} from "@/types";

export const advocateProfileApi = {
  get: () => apiClient<AdvocateProfile>("/advocate-profile/"),

  update: (data: AdvocateProfileUpdateInput) =>
    apiClient<AdvocateProfile>("/advocate-profile/", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

export const appearanceFeesApi = {
  list: (filters?: { case_id?: number; hearing_id?: number; status?: FeeStatus }) =>
    apiClient<AppearanceFee[]>("/appearance-fees/", {
      params: {
        case_id: filters?.case_id,
        hearing_id: filters?.hearing_id,
        status: filters?.status,
      },
    }),

  create: (data: AppearanceFeeCreateInput) =>
    apiClient<AppearanceFee>("/appearance-fees/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: { amount?: string; notes?: string }) =>
    apiClient<AppearanceFee>(`/appearance-fees/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiClient<void>(`/appearance-fees/${id}/`, { method: "DELETE" }),

  /** Generate (or re-render) the invoice PDF; moves the fee to INVOICED. */
  generateInvoice: (id: number) =>
    apiClient<AppearanceFee>(`/appearance-fees/${id}/invoice/`, { method: "POST" }),

  /** The invoice PDF itself. Fetched as a blob rather than linked: the
   * endpoint streams behind an ownership check and needs the auth
   * header, which a plain <a> can't send. */
  invoiceFile: (id: number) => apiBlob(`/appearance-fees/${id}/invoice/file/`),

  /** Email the invoice to the case's billing contact. Resolves (does not
   * throw) with sent=false when the server has no SMTP configured. */
  send: (id: number) =>
    apiClient<SendInvoiceResult>(`/appearance-fees/${id}/send/`, { method: "POST" }),

  markPaid: (id: number) =>
    apiClient<AppearanceFee>(`/appearance-fees/${id}/mark-paid/`, { method: "POST" }),
};

export const travelBookingsApi = {
  list: (filters?: { case_id?: number; hearing_id?: number }) =>
    apiClient<TravelBooking[]>("/travel-bookings/", {
      params: { case_id: filters?.case_id, hearing_id: filters?.hearing_id },
    }),

  /** Uploading the ticket/confirmation is what marks a booking BOOKED.
   * Pass hearing_id to create a booking in the same call, or booking_id
   * to attach the file to an existing PENDING one. */
  upload: ({
    file,
    hearing_id,
    booking_id,
    booking_type,
    notes,
  }: {
    file: File;
    hearing_id?: number;
    booking_id?: number;
    booking_type?: BookingType;
    notes?: string;
  }) => {
    const formData = new FormData();
    formData.append("file", file);
    if (hearing_id) formData.append("hearing_id", String(hearing_id));
    if (booking_id) formData.append("booking_id", String(booking_id));
    if (booking_type) formData.append("booking_type", booking_type);
    if (notes) formData.append("notes", notes);
    return uploadFile<TravelBooking>("/travel-bookings/upload/", formData);
  },

  file: (id: number) => apiBlob(`/travel-bookings/${id}/file/`),

  delete: (id: number) =>
    apiClient<void>(`/travel-bookings/${id}/`, { method: "DELETE" }),
};
