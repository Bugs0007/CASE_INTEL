import { apiClient, uploadFile } from "./client";
import type {
  Document,
  DocumentUploadInput,
  DocumentUpdateInput,
  ProcessingStatus,
} from "@/types";

export const documentsApi = {
  list: (filters?: {
    case_id?: number;
    document_type?: string;
    processing_status?: ProcessingStatus;
  }) => apiClient<Document[]>("/documents/", { params: filters }),

  get: (id: number) => apiClient<Document>(`/documents/${id}/`),

  upload: ({ file, case_id, document_type }: DocumentUploadInput) => {
    const formData = new FormData();
    formData.append("file", file);
    if (case_id) formData.append("case_id", String(case_id));
    if (document_type) formData.append("document_type", document_type);
    return uploadFile<Document>("/documents/upload/", formData);
  },

  update: (id: number, data: DocumentUpdateInput) =>
    apiClient<Document>(`/documents/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  process: (id: number) =>
    apiClient<Document>(`/documents/${id}/process/`, { method: "POST" }),

  // Get processing status for real-time updates
  getStatus: (id: number) =>
    apiClient<{ status: string; progress?: number; error?: string }>(
      `/documents/${id}/status/`,
    ),

  delete: (id: number) =>
    apiClient<void>(`/documents/${id}/`, { method: "DELETE" }),
};
