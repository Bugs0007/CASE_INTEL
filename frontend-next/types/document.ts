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
  filename: string;
  file_path: string;
  file_type: string | null;
  file_size: number | null;
  document_type: DocumentType | null;
  document_date: string | null;
  processing_status: ProcessingStatus;
  chunk_count: number | null;
  created_at: string;
}

export interface DocumentUploadInput {
  file: File;
  case_id?: number;
  document_type?: DocumentType;
}
