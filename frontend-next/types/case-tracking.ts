import type { Case } from "./case";
import type { Hearing } from "./hearing";

export interface CourtStructureOption {
  label: string;
  complex_code?: string;
  est_code?: string;
}

export interface CourtStructureResponse {
  level: "state" | "district" | "complex" | "bench" | "court" | "case_type";
  // Districts/case-types/benches/states/courts return plain {code: label};
  // complexes return {rawValue: {label, complex_code, est_code}}.
  options: Record<string, string | CourtStructureOption>;
}

export interface TrackingConfigCnr {
  court_type: "district" | "high_court";
  cnr: string;
}

export interface TrackingConfigDistrict {
  court_type: "district";
  state_code: string;
  dist_code: string;
  court_complex_code: string;
  est_code: string;
  case_type: string;
  case_number: string;
  year: string;
}

export interface TrackingConfigHighCourt {
  court_type: "high_court";
  hc_court_code: string;
  bench_code: string;
  case_type: string;
  case_number: string;
  year: string;
}

export type TrackingConfig = TrackingConfigCnr | TrackingConfigDistrict | TrackingConfigHighCourt;

export interface CourtDataSnapshot {
  cnr: string;
  case_status: string;
  case_stage: string;
  court_and_judge: string;
  court_name: string;
  next_hearing_date: string | null;
  first_hearing_date: string | null;
  nature_of_disposal: string;
  hearing_count: number;
}

export interface TrackingResponse {
  case: Case;
  hearings: Hearing[];
  snapshot: CourtDataSnapshot | null;
  rate_limited?: boolean;
  retry_after?: string;
  new_hearing_dates?: string[];
}

export interface TrackingErrorResponse {
  detail: string;
  code: string;
}

export interface TrackingPreview {
  preview_token: string;
  case_title: string | null;
  cnr: string;
  petitioner: string;
  respondent: string;
  court_name: string;
  case_status: string;
  case_stage: string;
  case_type: string | null;
  case_number: string | null;
  year: string | null;
  next_hearing_date: string | null;
  first_hearing_date: string | null;
  hearing_count: number;
}
