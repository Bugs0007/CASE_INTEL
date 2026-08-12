/**
 * Entirely fake data for the /walkthrough guided tour.
 *
 * Nothing here is fetched -- every value is a hardcoded literal so the tour
 * can render realistic-looking screens with zero network calls. Do not wire
 * this into any real hook, API client, or type shared with the live app;
 * keeping it self-contained is what makes the whole route removable by
 * deleting this directory.
 */

export const mockAdvocateName = "Adv. Meera Reddy";

// ---------------------------------------------------------------------------
// Step 1 -- Dashboard
// ---------------------------------------------------------------------------

export const mockAttentionItems = [
  {
    key: "hearing-1",
    title: "Ramesh Kumar vs. TSSPDCL",
    message: "has a Writ Petition hearing tomorrow — arguments on interim stay",
    meta: "12 Aug, 10:30 AM · WP/14562/2024",
    kind: "hearing" as const,
  },
  {
    key: "ecourts-1",
    title: "Lakshmi Traders vs. Union of India",
    message: "eCourts found a new hearing date since your last login",
    meta: "New date 18 Aug · CA/2231/2023",
    kind: "update" as const,
  },
  {
    key: "doc-1",
    title: "Suresh Chandra — Bail Application",
    message: "bail-order-scan.pdf failed processing",
    meta: "CRLP/887/2024",
    kind: "failed" as const,
  },
];

export const mockDensityDays = [0, 1, 0, 2, 1, 0, 0, 3, 1, 0, 0, 1, 2, 0];

export const mockUrgentCases = [
  { title: "Ramesh Kumar vs. TSSPDCL", number: "WP/14562/2024", days: "Tomorrow", priority: "High" as const },
  { title: "Lakshmi Traders vs. Union of India", number: "CA/2231/2023", days: "In 6 days", priority: "Medium" as const },
  { title: "Suresh Chandra — Bail Application", number: "CRLP/887/2024", days: "In 9 days", priority: "High" as const },
];

// ---------------------------------------------------------------------------
// Steps 2 & 3 -- Advocate search + bulk import
// ---------------------------------------------------------------------------

export const mockSearchResults = [
  { cnr: "TSHC010012342024", caseNumber: "WP/14562/2024", petitioner: "Ramesh Kumar", respondent: "TSSPDCL", court: "High Court for the State of Telangana", status: "Pending" },
  { cnr: "TSHC010045672023", caseNumber: "CA/2231/2023", petitioner: "Lakshmi Traders", respondent: "Union of India", court: "High Court for the State of Telangana", status: "Pending" },
  { cnr: "TSCC010098762024", caseNumber: "CRLP/887/2024", petitioner: "State of Telangana", respondent: "Suresh Chandra", court: "City Civil Court, Hyderabad", status: "Pending" },
  { cnr: "TSCC010011232021", caseNumber: "OS/556/2021", petitioner: "Bhavani Enterprises", respondent: "Narsimha Rao", court: "City Civil Court, Hyderabad", status: "Disposed" },
  { cnr: "TSHC010078902022", caseNumber: "WA/990/2022", petitioner: "K. Padma", respondent: "Municipal Corporation of Hyderabad", court: "High Court for the State of Telangana", status: "Pending" },
];

// ---------------------------------------------------------------------------
// Steps 4-8 -- Case detail page
// ---------------------------------------------------------------------------

export const mockCase = {
  title: "Ramesh Kumar vs. TSSPDCL",
  caseNumber: "WP/14562/2024",
  cnr: "TSHC010012342024",
  court: "High Court for the State of Telangana at Hyderabad",
  caseType: "Writ Petition",
  status: "Open",
  priority: "High",
  filingDate: "14 Mar 2024",
  opposingParty: "Telangana State Southern Power Distribution Company Ltd. (TSSPDCL)",
  yourSide: "Petitioner",
  notes:
    "Challenge to an arbitrary transfer/disconnection order issued without notice. Interim stay granted; matter listed for final arguments.",
};

export const mockClientContacts = [
  { id: 1, name: "Ramesh Kumar", role: "Client", email: "ramesh.kumar@example.com", phone: "+91 98480 12345", isBilling: true },
  { id: 2, name: "Priya Kumar (Power of Attorney)", role: "Family", email: "", phone: "+91 98480 99999", isBilling: false },
];

export const mockOrder = {
  orderDate: "29 Jul 2026",
  judge: "Justice K. Sarath",
  whatHappened:
    "The court heard arguments on the interim stay application and extended the stay on disconnection until the next hearing, on the condition that the petitioner clears 50% of the disputed arrears within four weeks.",
  yourSideLabel: "Petitioner (You)",
  yourSideDirections: [
    "Deposit 50% of the disputed arrears (Rs. 1,84,000) with the Registry within 4 weeks",
    "File proof of deposit before the next hearing",
  ],
  otherSideLabel: "Respondent",
  otherSideDirections: [
    "Shall not disconnect the power supply until the next date, subject to compliance above",
  ],
  nextDate: "2 Sep 2026",
  nextDatePurpose: "For final arguments",
};

export const mockHearings = [
  {
    id: 1,
    date: "12 Aug 2026, 10:30 AM",
    type: "Arguments",
    source: "eCourts" as const,
    location: "Court Hall 3, High Court of Telangana",
    judge: "Justice K. Sarath",
    status: "Scheduled" as const,
    causeList: { status: "listed" as const, item: 14, court: "3" },
    fee: { amount: "₹5,000", status: "pending" as const, label: "Fee recorded, not yet invoiced" },
    travel: null as null | { label: string; ok: boolean },
    orders: [] as { label: string }[],
  },
  {
    id: 2,
    date: "29 Jul 2026, 11:00 AM",
    type: "Interim Application",
    source: "eCourts" as const,
    location: "Court Hall 3, High Court of Telangana",
    judge: "Justice K. Sarath",
    status: "Completed" as const,
    causeList: { status: "listed" as const, item: 7, court: "3" },
    fee: { amount: "₹5,000", status: "paid" as const, label: "Paid (invoice INV-0006)" },
    travel: { label: "Travel booked", ok: true },
    orders: [{ label: "Order 1" }, { label: "Order 2" }],
  },
  {
    id: 3,
    date: "3 Jun 2026, 10:30 AM",
    type: "First Hearing",
    source: "eCourts" as const,
    location: "Court Hall 3, High Court of Telangana",
    judge: "Justice K. Sarath",
    status: "Completed" as const,
    causeList: { status: "listed" as const, item: 22, court: "3" },
    fee: { amount: "₹5,000", status: "paid" as const, label: "Paid (invoice INV-0004)" },
    travel: null as null | { label: string; ok: boolean },
    orders: [{ label: "Order" }],
  },
];

// ---------------------------------------------------------------------------
// Step 8 -- Invoicing
// ---------------------------------------------------------------------------

export const mockFeeSummary = {
  pending: { amount: "₹5,000", count: 1 },
  invoiced: { amount: "₹0", count: 0 },
  paid: { amount: "₹5,000", count: 1 },
  outstanding: "₹5,000",
  totalBilled: "₹10,000",
};

export const mockInvoice = {
  number: "INV-0007",
  amount: "₹5,000",
  hearingDate: "12 Aug 2026",
  billingContact: "Ramesh Kumar",
  billingEmail: "ramesh.kumar@example.com",
};

// ---------------------------------------------------------------------------
// Step 9 -- Travel booking
// ---------------------------------------------------------------------------

export const mockTravelBookings = [
  { type: "Train", label: "Secunderabad → Hyderabad Deccan, Chair Car", status: "Booked", file: "irctc-ticket-12aug.pdf" },
  { type: "Hotel", label: "Hotel Minerva Grand, Hyderabad — 1 night", status: "Booked", file: "hotel-confirmation.pdf" },
];
