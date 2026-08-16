import type { Case, CaseCreateInput, UserPartyRole } from "./case";
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
  // Optional -- the backend detects district vs. high_court from the CNR
  // itself when this is omitted (see preview_case_tracking), trying the
  // other type automatically on a genuine not-found. Only set this
  // explicitly if bypassing detection on purpose.
  court_type?: "district" | "high_court";
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
  // Resolved court type -- either what the CNR-first request explicitly
  // passed, or what the backend auto-detected from the CNR when it
  // wasn't. See court_type_detected to tell the two apart in the UI.
  court_type: "district" | "high_court";
  court_type_detected: boolean;
  case_type: string | null;
  case_number: string | null;
  year: string | null;
  next_hearing_date: string | null;
  first_hearing_date: string | null;
  hearing_count: number;
}

/** Response from POST /api/cases/cnr-lookup/ -- the "Track by CNR"
 * quick-add flow's fetch step, on the manual case entry page. Unlike
 * TrackingPreview, no Case exists yet: case_number/title/user_party_role/
 * opposing_party are pre-fill SUGGESTIONS for the manual entry form, not
 * a display of an already-tracked case. The advocate reviews/edits them,
 * then submits via casesApi.createFromCnr() with this preview_token. */
export interface CnrLookupPreview {
  preview_token: string;
  cnr: string;
  case_number: string;
  title: string;
  user_party_role: UserPartyRole;
  opposing_party: string | null;
  petitioner: string;
  respondent: string;
  court_name: string;
  case_status: string;
  case_stage: string;
  court_type: "district" | "high_court";
  court_type_detected: boolean;
  next_hearing_date: string | null;
  first_hearing_date: string | null;
  hearing_count: number;
}

/** Body for POST /api/cases/cnr-lookup/create/ -- confirms a
 * CnrLookupPreview into a real Case (with tracking already configured),
 * using whatever the advocate reviewed/edited in the pre-filled form. */
export interface CaseCreateFromCnrInput extends CaseCreateInput {
  preview_token: string;
}

/** A same-user CNR duplicate, returned as a 409 by both
 * /cases/cnr-lookup/ and /cases/cnr-lookup/create/ (and by
 * /cases/<id>/tracking/refresh/ when it uncovers two of the same owner's
 * cases resolving to the same CNR). Carries enough to link straight to
 * the existing case instead of just reporting the conflict. */
export interface DuplicateCnrErrorData {
  detail: string;
  code: "duplicate_cnr";
  case_id: number;
  case_number: string;
}
