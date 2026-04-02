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
  case_title?: string | null; // For backward compatibility
  filename: string;
  file_path: string;
  file_type: string | null;
  file_size: number | null;
  document_type: DocumentType | null;
  document_date: string | null;
  processing_status: ProcessingStatus;
  chunk_count: number | null;
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
