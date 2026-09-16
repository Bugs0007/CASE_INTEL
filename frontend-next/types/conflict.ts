// Mirrors ConflictHit.to_dict() in core/services/conflict_check.py.

/** adverse: the same party on opposite sides. role_unknown: a close match
 * where one case's party role isn't set, so the sides can't be compared. */
export type ConflictKind = "adverse" | "role_unknown";

export type ConflictBand = "likely" | "possible";

/** Relative to the advocate: their client's side, the other side, or unknown. */
export type ConflictSide = "own" | "other" | "unknown";

export interface ConflictHit {
  kind: ConflictKind;
  band: ConflictBand;
  score: number;
  new_party: string;
  new_side: ConflictSide;
  existing_party: string;
  existing_side: ConflictSide;
  case_id: number;
  case_number: string;
  case_title: string;
}
