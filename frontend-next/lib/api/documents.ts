import { apiClient, uploadFile } from "./client";
import type { Document, DocumentUploadInput } from "@/types";

export const documentsApi = {
  list: (caseId?: number) =>
    apiClient<Document[]>("/documents/", { params: { case_id: caseId } }),

  get: (id: number) => apiClient<Document>(`/documents/${id}/`),

  upload: ({ file, case_id, document_type }: DocumentUploadInput) => {
    const formData = new FormData();
    formData.append("file", file);
    if (case_id) formData.append("case_id", String(case_id));
    if (document_type) formData.append("document_type", document_type);
    return uploadFile<Document>("/documents/upload/", formData);
  },

  process: (id: number) =>
    apiClient<Document>(`/documents/${id}/process/`, { method: "POST" }),

  delete: (id: number) =>
    apiClient<void>(`/documents/${id}/`, { method: "DELETE" }),
};
