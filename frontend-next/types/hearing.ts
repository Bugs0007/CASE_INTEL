export type HearingType =
  | "preliminary"
  | "motion"
  | "trial"
  | "appeal"
  | "sentencing"
  | "arraignment"
  | "status"
  | "other";
export type HearingStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "postponed";

export type HearingSource = "manual" | "ecourts";

export interface Hearing {
  id: number;
  case: number;
  case_title: string;
  hearing_date: string;
  hearing_type: HearingType;
  hearing_type_display: string;
  location: string | null;
  judge: string | null;
  status: HearingStatus;
  status_display: string;
  notes: string | null;
  outcome: string | null;
  source: HearingSource;
  business_date: string | null;
  purpose: string | null;
  created_at: string;
  updated_at: string;
}

export interface HearingCreateInput {
  case: number;
  hearing_date: string;
  hearing_type: HearingType;
  location?: string;
  judge?: string;
  status?: HearingStatus;
  notes?: string;
  outcome?: string;
}

export interface HearingUpdateInput extends Partial<HearingCreateInput> {}
