export type ProcessingStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";

// Status of the latest background ProcessingJob for a document (null when
// the document has never been queued, e.g. legacy rows).
export type JobStatus = "queued" | "running" | "succeeded" | "failed";
export type DocumentType =
  | "contract"
  | "pleading"
  | "evidence"
  | "correspondence"
  | "brief"
  | "motion"
  | "order"
  // Fetched automatically from the eCourts portal by order sync --
  // rendered with a "From eCourts" badge.
  | "court_order"
  | "other";

export interface Document {
  id: number;
  case_id: number | null;
  case_title?: string | null; // For backward compatibility
  filename: string;
  file_path: string;
  file_type: string | null;
  file_size: number | null;
  document_type: DocumentType | null;
  document_date: string | null;
  processing_status: ProcessingStatus;
  chunk_count: number | null;
  ocr_applied: boolean;
  job_status: JobStatus | null;
  job_progress_current: number | null;
  job_progress_total: number | null;
  job_error: string | null;
  folder?: number | null;
  folder_name?: string | null;
  ai_summary?: string | null;
  created_at: string;
  case?: {
    id: number;
    title: string;
    case_number: string;
    client_name?: string;
  };
}

export interface DocumentUploadInput {
  file: File;
  case_id?: number;
  folder_id?: number;
  document_type?: DocumentType;
}

export interface DocumentUpdateInput {
  filename?: string;
  case_id?: number | null;
  folder?: number | null;
  document_type?: DocumentType;
  document_date?: string | null;
  case?: {
    id: number;
    title: string;
  };
}
