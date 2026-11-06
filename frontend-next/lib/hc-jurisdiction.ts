// Which High Court serves which state or union territory, for the High Courts
// tab. ONE table: the registry code of each High Court (the codes at
// GET /api/cases/high-courts/) -> the locations of @svg-maps/india it serves.
//
// Kept line-per-court on purpose: core/tests/test_hc_jurisdiction.py reads this
// file to check that every High Court in the library registry appears here, and
// __tests__/hc-jurisdiction.test.ts checks that every location the map draws
// belongs to exactly one court.
//
// Where it differs from the official picture:
//  - Ladakh is not drawn separately by the map: "jk" is one shape for Jammu and
//    Kashmir, and the one High Court serves both union territories.
//  - Dadra and Nagar Haveli and Daman and Diu became one union territory in 2020;
//    the map still draws them as two ("dn", "dd"). Both belong to Bombay.
//  - The library registry names the court "Jammu & Kashmir High Court"; its
//    official name is High Court of Jammu & Kashmir and Ladakh.
export const JURISDICTION: Record<string, string[]> = {
  allahabad: ["up"],
  andhra: ["ap"],
  bombay: ["mh", "ga", "dn", "dd"],
  calcutta: ["wb", "an"],
  chhattisgarh: ["ct"],
  delhi: ["dl"],
  gauhati: ["as", "ar", "nl", "mz"],
  gujarat: ["gj"],
  himachal: ["hp"],
  jammu: ["jk"],
  jharkhand: ["jh"],
  karnataka: ["ka"],
  kerala: ["kl", "ld"],
  mp: ["mp"],
  madras: ["tn", "py"],
  manipur: ["mn"],
  meghalaya: ["ml"],
  orissa: ["or"],
  patna: ["br"],
  punjab: ["pb", "hr", "ch"],
  rajasthan: ["rj"],
  sikkim: ["sk"],
  telangana: ["tg"],
  tripura: ["tr"],
  uttarakhand: ["ut"],
};

/** Location id -> the High Court that serves it. */
export const COURT_OF_LOCATION: Record<string, string> = Object.fromEntries(
  Object.entries(JURISDICTION).flatMap(([court, ids]) => ids.map((id) => [id, court])),
);

/** The small states and union territories that are hard to click on the map and
 * so also get a button in a column beside it. */
export const SMALL_LOCATIONS: { ids: string[]; label: string }[] = [
  { ids: ["dl"], label: "Delhi" },
  { ids: ["ch"], label: "Chandigarh" },
  { ids: ["ga"], label: "Goa" },
  { ids: ["py"], label: "Puducherry" },
  { ids: ["ld"], label: "Lakshadweep" },
  { ids: ["an"], label: "Andaman & Nicobar" },
  { ids: ["dn", "dd"], label: "D&NH · Daman & Diu" },
];

/**
 * The map is OFF until the outline has been checked by someone qualified (Indian
 * law requires map outlines to follow the Survey of India's official depiction;
 * see docs/advocate-search-redesign.md). Turn it on with
 * NEXT_PUBLIC_HC_MAP=true. Until then the High Courts tab uses the searchable
 * list and a plain tile grid, which do the same job.
 */
export const HC_MAP_ENABLED = process.env.NEXT_PUBLIC_HC_MAP === "true";

export const MAP_CREDIT = "Map: @svg-maps/india, CC BY 4.0. Not to scale; for choosing a court only.";

/** The names the map gives its locations (checked against the package in
 * __tests__/hc-jurisdiction.test.ts), so a court's states can be named without
 * loading the map. */
export const LOCATION_NAMES: Record<string, string> = {
  an: "Andaman and Nicobar Islands", ap: "Andhra Pradesh", ar: "Arunachal Pradesh", as: "Assam", br: "Bihar",
  ch: "Chandigarh", ct: "Chhattisgarh", dn: "Dadra and Nagar Haveli", dd: "Daman and Diu", dl: "Delhi", ga: "Goa",
  gj: "Gujarat", hr: "Haryana", hp: "Himachal Pradesh", jk: "Jammu and Kashmir", jh: "Jharkhand", ka: "Karnataka",
  kl: "Kerala", ld: "Lakshadweep", mp: "Madhya Pradesh", mh: "Maharashtra", mn: "Manipur", ml: "Meghalaya",
  mz: "Mizoram", nl: "Nagaland", or: "Odisha", py: "Puducherry", pb: "Punjab", rj: "Rajasthan", sk: "Sikkim",
  tn: "Tamil Nadu", tg: "Telangana", tr: "Tripura", up: "Uttar Pradesh", ut: "Uttarakhand", wb: "West Bengal",
};

/** "Maharashtra, Goa, Dadra and Nagar Haveli and Daman and Diu" for a court that
 * serves more than one state or territory; empty for a single-state court. */
export function coverageOf(courtCode: string): string {
  const ids = JURISDICTION[courtCode] ?? [];
  if (ids.length < 2) return "";
  const names = ids.map((id) => LOCATION_NAMES[id]).filter(Boolean);
  return names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : "";
}
