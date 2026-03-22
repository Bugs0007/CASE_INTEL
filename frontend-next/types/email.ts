export interface Email {
  id: number;
  subject: string | null;
  sender: string | null;
  sent_at: string | null;
  has_attachments: boolean;
  case_id: number | null;
  case_title: string | null;
}

export interface GmailStatus {
  connected: boolean;
  email?: string;
  last_sync?: string | null;
}

export interface SyncConfig {
  labels?: string[];
  max_results?: number;
  days_back?: number;
}

export interface SyncResult {
  synced_count: number;
  emails: Array<{ id: number; subject: string }>;
}
