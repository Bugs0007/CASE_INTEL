export interface DashboardStats {
  active_cases: number;
  total_documents: number;
  email_threads: number;
  documents_by_status: Record<string, number>;
  cases_by_priority: Record<string, number>;
  cases_by_status: Record<string, number>;
}

export interface RecentEmail {
  id: number;
  subject: string | null;
  sender: string | null;
  sent_at: string;
  case_id: number | null;
  case_title: string | null;
}

export interface RecentActivity {
  id: number;
  activity_type: string | null;
  description: string | null;
  created_at: string;
  case_id: number | null;
}

export interface ActiveCaseSummary {
  id: number;
  case_number: string;
  title: string;
  document_count: number;
  priority: string;
  status: string;
}

export interface DashboardData {
  stats: DashboardStats;
  recent_emails: RecentEmail[];
  recent_activity: RecentActivity[];
  active_cases_summary: ActiveCaseSummary[];
}
