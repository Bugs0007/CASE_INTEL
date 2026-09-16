// Mirrors core/serializers/task.py (TaskSerializer).

export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled";

export type TaskKind = "manual" | "order_direction" | "limitation";

/** How a system-generated due date was arrived at. Empty for a date the
 * advocate typed in. */
export type TaskDueDateBasis =
  | ""
  | "explicit_date"
  | "relative_to_order"
  | "next_hearing_fallback"
  | "limitation_rule";

export interface Task {
  id: number;
  case: number | null;
  case_title: string | null;
  case_number: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  kind: TaskKind;
  kind_display: string;
  /** Calendar date, YYYY-MM-DD. */
  due_date: string | null;
  due_date_basis: TaskDueDateBasis;
  due_date_basis_display: string;
  source_order: number | null;
  source_text: string;
  rule_key: string;
  trigger_date: string | null;
  /** Suggested by the system and not yet confirmed. */
  needs_review: boolean;
  user_modified: boolean;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Writable fields. Tasks created through the API are always manual. */
export interface TaskInput {
  case?: number | null;
  title: string;
  description?: string;
  due_date?: string | null;
  status?: TaskStatus;
  needs_review?: boolean;
}

export interface TaskFilters {
  case_id?: number;
  status?: TaskStatus | "open";
  kind?: TaskKind;
  /** YYYY-MM-DD, inclusive. */
  due_before?: string;
  overdue?: boolean;
  needs_review?: boolean;
}
