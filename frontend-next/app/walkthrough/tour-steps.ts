/**
 * The 9-step script for the /walkthrough guided tour. Each step names a
 * scene to render and a highlightKey that scene understands -- see the
 * `data-tour={highlightKey}` targets inside each scene component.
 */

export type SceneKey = "dashboard" | "search" | "case-detail" | "travel";

export interface TourStep {
  id: number;
  title: string;
  caption: string;
  scene: SceneKey;
  highlightKey: string;
  /** Passed to the scene so it can change what it shows (e.g. search
   * results only appear from step 3 onward). */
  sceneState?: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: 1,
    title: "Your dashboard",
    caption:
      "This is the first thing you see when you log in. It puts what needs your attention today front and centre — hearings coming up, updates from the court, anything that needs a second look — so you never have to go hunting for what's urgent.",
    scene: "dashboard",
    highlightKey: "attention",
  },
  {
    id: 2,
    title: "Find your cases by name or bar code",
    caption:
      "No manual data entry. Tell Case Intel your name or bar registration number and which state you practice in, and it searches the court's own records for every case filed under your name.",
    scene: "search",
    sceneState: "form",
    highlightKey: "search-form",
  },
  {
    id: 3,
    title: "Pick which cases to track",
    caption:
      "Case Intel brings back every matching case from the court. Tick the ones that are actually yours and add them all to Case Intel in one go — much faster than typing each one in by hand.",
    scene: "search",
    sceneState: "results",
    highlightKey: "results",
  },
  {
    id: 4,
    title: "Everything about the case, in one place",
    caption:
      "Every case gets its own page with the essentials: who your client is, who's on the other side, and — importantly — which side you're on. Case Intel uses this to always show you what matters to your side first.",
    scene: "case-detail",
    highlightKey: "case-overview",
  },
  {
    id: 5,
    title: "Orders open in one tap",
    caption:
      "Each hearing shows its date, court and judge. When the court has issued more than one order on the same date, they're kept as separate buttons — tap the exact one you need instead of digging through a combined file.",
    scene: "case-detail",
    highlightKey: "hearing-orders",
  },
  {
    id: 6,
    title: "A plain-English summary of the order",
    caption:
      "Instead of reading a long court order line by line, you get a short summary of what the court decided — with directions to YOUR side kept clearly separate from what the other side has to do.",
    scene: "case-detail",
    highlightKey: "order-overview",
  },
  {
    id: 7,
    title: "Know exactly where you stand on the list",
    caption:
      "The evening before a hearing, Case Intel checks the court's published cause list and tells you the exact item number and court hall — so you're not scrolling a 300-item PDF the morning of.",
    scene: "case-detail",
    highlightKey: "cause-list",
  },
  {
    id: 8,
    title: "Bill for your appearance",
    caption:
      "Record your fee for an appearance and Case Intel builds a proper invoice for you. Send it to your client's billing contact by email in one click, then mark it paid once you've been settled up.",
    scene: "case-detail",
    highlightKey: "fees",
  },
  {
    id: 9,
    title: "Keep travel bookings with the hearing",
    caption:
      "Travelling for an out-of-town hearing? Upload your train or flight ticket and hotel booking here — they stay attached to that hearing, so everything for the trip lives in one place.",
    scene: "travel",
    highlightKey: "travel-upload",
  },
];
