// Mirrors core/services/limitation/ (LimitationRule.to_dict,
// LimitationComputation.to_dict) and core/views/limitation.py.

import type { CourtType } from "./case";
import type { Task } from "./task";

export interface LimitationRule {
  key: string;
  label: string;
  citation: string;
  period: number;
  period_unit: "days" | "years";
  period_text: string;
  runs_from: string;
  court_types: CourtType[];
  copy_time_excluded: boolean;
  condonable: boolean;
  note: string;
}

export interface LimitationComputation {
  rule: LimitationRule;
  /** YYYY-MM-DD */
  trigger_date: string;
  /** YYYY-MM-DD -- the earliest the deadline can be; see notes. */
  last_day: string;
  notes: string[];
}

export interface AddLimitationDeadlineInput {
  rule_key: string;
  trigger_date: string;
  source_order?: number | null;
}

export interface AddLimitationDeadlineResponse {
  task: Task;
  computation: LimitationComputation;
  outcome: "created" | "updated" | "unchanged" | "skipped";
}
