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
  is_connected?: boolean;
  email?: string;
  email_address?: string;
  last_sync?: string | null;
  last_sync_time?: string | null;
  total_emails_synced?: number;
}

export interface SyncConfig {
  labels?: string[] | string;
  max_results?: number;
  days_back?: number;
  start_date?: string;
  end_date?: string;
  keywords?: string;
}

export interface SyncResult {
  synced_count: number;
  emails: Array<{ id: number; subject: string }>;
}
