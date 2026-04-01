export type ProcessingStatus =
  | "pending"
  | "processing"
  | "completed"
  | "failed";
export type DocumentType =
  | "contract"
  | "pleading"
  | "evidence"
  | "correspondence"
  | "brief"
  | "motion"
  | "order"
  | "other";

export interface Document {
  id: number;
  case_id: number | null;
  file_name: string;
  file_path: string;
  file_type: string | null;
  file_size: number | null;
  document_type: DocumentType | null;
  document_date: string | null;
  upload_date?: string;
  processing_status: ProcessingStatus;
  chunk_count: number | null;
  ai_summary?: string | null;
  created_at: string;
  case?: {
    id: number;
    title: string;
    case_number: string;
  };
}

export interface DocumentUploadInput {
  file: File;
  case_id?: number;
  document_type?: DocumentType;
}
