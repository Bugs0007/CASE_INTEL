/**
 * Synthetic sample data for the landing page (and, later, the trailer).
 *
 * Every name, case number, CNR, amount and date below is invented. It reuses
 * the same fictional world as app/walkthrough/mock-data.ts (Adv. Meera Reddy,
 * Ramesh Kumar vs. TSSPDCL) but is copied, not imported, so the walkthrough
 * route stays removable by deleting its directory.
 *
 * Product claims live in the scene copy, and each one traces to CLAUDE.md.
 * Nothing here is a claim: it is what a sample screen looks like.
 */

export const ADVOCATE = "Adv. Meera Reddy";

/* ---------------------------------------------------------------- hero */

export type ListRow = { item: string; cn: string; parties: string; adv: string; mine?: boolean };

// The cause list the hero "reads". Telangana High Court is the only court
// whose cause lists Case Intel reads today (CLAUDE.md, Cause lists).
export const CAUSE_LIST = {
  court: "High Court for the State of Telangana",
  hall: "Court Hall 3",
  date: "02 Sep 2026",
  fetched: "19:02",
  rows: [
    { item: "9", cn: "WP/20417/2025", parties: "P. Srinivas vs. State of Telangana", adv: "Adv. K. Rao" },
    { item: "10", cn: "CRP/1182/2024", parties: "Sai Agencies vs. N. Laxmi", adv: "Adv. S. Begum" },
    { item: "11", cn: "WA/772/2025", parties: "GHMC vs. R. Venkatesh", adv: "Standing Counsel" },
    { item: "12", cn: "WP/9930/2026", parties: "A. Fathima vs. TSRTC", adv: "Adv. P. Naidu" },
    { item: "13", cn: "CMA/415/2023", parties: "United Insurance vs. B. Anjaiah", adv: "Adv. V. Kumar" },
    { item: "14", cn: "WP/14562/2024", parties: "Ramesh Kumar vs. TSSPDCL", adv: ADVOCATE, mine: true },
    { item: "15", cn: "WP/3318/2026", parties: "M. Rajitha vs. Union of India", adv: "Adv. D. Prasad" },
    { item: "16", cn: "AS/208/2022", parties: "K. Bhaskar vs. K. Sudha", adv: "Adv. R. Iyer" },
    { item: "17", cn: "WP/18840/2025", parties: "Telangana Dairy vs. State", adv: "Adv. A. Khan" },
    { item: "18", cn: "CA/2231/2023", parties: "Lakshmi Traders vs. Union of India", adv: ADVOCATE, mine: true },
    { item: "19", cn: "CRLP/5521/2026", parties: "S. Ravi vs. State of Telangana", adv: "Public Prosecutor" },
    { item: "20", cn: "WP/7004/2024", parties: "N. Gopal vs. HMDA", adv: "Adv. T. Reddy" },
  ] as ListRow[],
};

/* ------------------------------------------------------------ fan-out */

export type Complex = { name: string; fails?: boolean };
export type District = { name: string; x: number; y: number; complexes: Complex[] };

// Positions are abstract (a 1000x640 canvas), deliberately NOT a map.
// Array order is the scan order: districts with sample hits come early.
export const DISTRICTS: District[] = [
  { name: "Medchal", x: 300, y: 390, complexes: [{ name: "Kukatpally" }, { name: "Malkajgiri" }] },
  { name: "Hyderabad", x: 400, y: 430, complexes: [{ name: "City Civil Court" }, { name: "Nampally" }, { name: "CMM Courts" }, { name: "Secunderabad" }] },
  { name: "Nizamabad", x: 170, y: 170, complexes: [{ name: "Nizamabad" }, { name: "Bodhan" }, { name: "Armoor" }] },
  { name: "Siddipet", x: 380, y: 300, complexes: [{ name: "Siddipet" }, { name: "Gajwel", fails: true }, { name: "Husnabad" }] },
  { name: "Karimnagar", x: 450, y: 190, complexes: [{ name: "Karimnagar" }, { name: "Huzurabad" }] },
  { name: "Ranga Reddy", x: 260, y: 500, complexes: [{ name: "L.B. Nagar" }, { name: "Rajendranagar" }, { name: "Vikarabad" }] },
  { name: "Adilabad", x: 300, y: 70, complexes: [{ name: "Adilabad" }, { name: "Utnoor" }] },
  { name: "Warangal", x: 640, y: 250, complexes: [{ name: "Hanamkonda" }, { name: "Warangal" }, { name: "Narsampet" }] },
  { name: "Nalgonda", x: 560, y: 480, complexes: [{ name: "Nalgonda" }, { name: "Miryalaguda" }, { name: "Suryapet" }] },
  { name: "Sangareddy", x: 150, y: 330, complexes: [{ name: "Sangareddy" }, { name: "Zaheerabad" }] },
  { name: "Khammam", x: 780, y: 390, complexes: [{ name: "Khammam" }, { name: "Sathupalli" }] },
  { name: "Mahabubnagar", x: 360, y: 570, complexes: [{ name: "Mahabubnagar" }, { name: "Wanaparthy" }] },
];

export type SearchHit = { cn: string; court: string; parties: string; advocate: string; verified: boolean };

// Rows the fan-out "finds", revealed as the scan passes their district.
// `advocate` is the court-recorded advocate text shown for a human to judge.
export const SEARCH_HITS: (SearchHit & { district: string })[] = [
  { district: "Hyderabad", cn: "CRLP/887/2024", court: "City Civil Court, Hyderabad", parties: "State vs. Suresh Chandra", advocate: "MEERA REDDY", verified: true },
  { district: "Hyderabad", cn: "OS/556/2021", court: "City Civil Court, Hyderabad", parties: "Bhavani Enterprises vs. Narsimha Rao", advocate: "M. MEERA REDDY", verified: true },
  { district: "Ranga Reddy", cn: "OS/1120/2023", court: "L.B. Nagar", parties: "K. Padma vs. S. Anil", advocate: "", verified: false },
  { district: "Nalgonda", cn: "MC/64/2025", court: "Nalgonda", parties: "R. Kavitha vs. R. Mahesh", advocate: "MEERA REDDY K", verified: true },
];

/* -------------------------------------------------------------- order */

export const CASE = {
  title: "Ramesh Kumar vs. TSSPDCL",
  cn: "WP/14562/2024",
  cnr: "TSHC010012342024",
  side: "Petitioner",
};

export const ORDER = {
  file: "order_2026-07-29.pdf",
  date: "29 Jul 2026",
  bench: "Hon'ble Sri Justice K. Sarath",
  // Body text of the "scanned" order sheet.
  paragraphs: [
    "Heard the learned counsel for the petitioner and the learned Standing Counsel for the respondent on I.A. No. 2 of 2026.",
    "The interim order dated 03.06.2026 restraining the respondent from disconnecting the supply is extended until the next date of hearing, subject to the condition below.",
    "The petitioner is directed to deposit 50% of the disputed arrears, i.e. Rs. 1,84,000/-, with the Registry within four weeks from today, and shall file proof of such deposit before the next date of hearing.",
    "The respondent shall not disconnect the power supply in the meantime, subject to compliance with the above.",
    "List on 02.09.2026 for final arguments.",
  ],
  happened:
    "Stay on disconnection extended to the next date, on condition that the petitioner deposits half the disputed arrears.",
  yours: [
    { text: "Deposit 50% of disputed arrears (Rs. 1,84,000) with the Registry", rule: "within four weeks", due: "26 Aug", dueKey: "2026-08-26" },
    { text: "File proof of deposit", rule: "before the next date", due: "02 Sep", dueKey: "2026-09-02" },
  ],
  theirs: ["Shall not disconnect the power supply until the next date"],
  next: "02 Sep 2026 · final arguments",
};

// Two-week strip the tasks land on: Mon 24 Aug – Sun 6 Sep 2026.
export const CAL_DAYS = Array.from({ length: 14 }, (_, i) => {
  const d = new Date(Date.UTC(2026, 7, 24 + i));
  const key = d.toISOString().slice(0, 10);
  return {
    key,
    dow: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()],
    day: d.getUTCDate(),
  };
});

/* -------------------------------------------------------------- x-ray */

// The cause-list page under the beam. `sy` is where the S.No. glyph sits
// before pairing; its row's case number sits at `y` (both in px within the
// sheet). Pairing by vertical position is what the parser does.
export const XRAY_ROWS = [
  { sno: "12", cn: "WP/9930/2026", parties: "A. Fathima vs. TSRTC" },
  { sno: "13", cn: "CMA/415/2023", parties: "United Insurance vs. B. Anjaiah" },
  { sno: "14", cn: "WP/14562/2024", parties: "Ramesh Kumar vs. TSSPDCL", mine: true },
  { sno: "15", cn: "WP/3318/2026", parties: "M. Rajitha vs. Union of India" },
  { sno: "16", cn: "AS/208/2022", parties: "K. Bhaskar vs. K. Sudha" },
  { sno: "17", cn: "WP/18840/2025", parties: "Telangana Dairy vs. State" },
];

/* ----------------------------------------------------------- case bot */

export const BOT = {
  question: "What did the court direct my client to deposit, and by when?",
  docs: [
    { name: "order_2026-07-29.pdf", hit: "…directed to deposit 50% of the disputed arrears, i.e. Rs. 1,84,000/-, with the Registry within four weeks…", ref: 1 },
    { name: "writ_petition.pdf", hit: "…the disputed arrears of Rs. 3,68,000/- raised without notice…", ref: 2 },
    { name: "counter_affidavit.pdf", hit: null, ref: 0 },
    { name: "ia_2_of_2026.pdf", hit: null, ref: 0 },
  ],
  answer: [
    { t: "Deposit half of the disputed arrears, " },
    { t: "Rs. 1,84,000", b: true },
    { t: ", with the Registry within four weeks of 29 Jul 2026" },
    { t: "[1]", c: 1 },
    { t: ". The arrears in dispute total Rs. 3,68,000" },
    { t: "[2]", c: 2 },
    { t: ". Proof of deposit is due before the next date, 02 Sep 2026" },
    { t: "[1]", c: 1 },
    { t: "." },
  ],
};

/* ------------------------------------------------------------ toolkit */

export const INVOICE = {
  number: "INV-0007",
  amount: "₹5,000",
  hearing: "02 Sep 2026",
  billTo: "Ramesh Kumar",
};

export const TRAVEL = [
  { kind: "Train", label: "Secunderabad → Hyderabad Deccan", file: "irctc-ticket-02sep.pdf" },
  { kind: "Hotel", label: "Hotel Minerva Grand · 1 night", file: "hotel-confirmation.pdf" },
];
