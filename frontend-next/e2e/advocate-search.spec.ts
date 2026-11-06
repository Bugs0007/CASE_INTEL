import { expect, test, type Page, type Route } from "@playwright/test";
import path from "node:path";
import { mockApi } from "./fixtures";

// The five screens of the redesigned advocate search, with the API answered in
// the browser (no backend). Each must be one screen from 1280x720 up: the page
// does not scroll, only lists and the table body do. Placeholder names and numbers.
// Set SHOTS_DIR to keep a screenshot of every screen at every size.

const SIZES = [
  { width: 1280, height: 720 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
] as const;

const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };
const ago = (minutes: number) => new Date(Date.now() - minutes * 60_000).toISOString();

const profile = {
  id: 1,
  display_name: "Rambabu Samalla",
  bar_codes: ["TS/1234/2009"],
  name_forms: ["Rambabu", "Ram babu", "S Rambabu", "S Ram babu", "Rambabu S"],
  excluded_names: ["T Rambabu", "K Rambabu", "Rambabu Reddy"],
  queries: ["Rambabu", "Ram babu"],
  query_count: 2,
  query_warning: "",
  suggestions: ["Ram babu S", "Samalla Rambabu"],
  created_at: ago(5000),
  updated_at: ago(5),
};

const STATES = { "29": "Telangana", "27": "Maharashtra", "7": "Karnataka" };
const DISTRICTS = Object.fromEntries(
  ["Adilabad", "Nirmal", "Mancherial", "Nizamabad", "Karimnagar", "Hyderabad", "Ranga Reddy", "Warangal", "Khammam", "Medak", "Nalgonda", "Mahabubnagar", "Siddipet"].map((n, i) => [String(i + 1), n]),
);
const COMPLEX_COUNTS: Record<string, number> = { "1": 4, "2": 3, "3": 3, "6": 9 };

const HIGH_COURTS = [
  ["telangana", "Telangana High Court", "29", []],
  ["bombay", "Bombay High Court", "1", ["Nagpur", "Aurangabad", "Goa"]],
  ["delhi", "Delhi High Court", "26", []],
  ["madras", "Madras High Court", "10", []],
  ["kerala", "Kerala High Court", "4", []],
  ["karnataka", "Karnataka High Court", "3", []],
  ["allahabad", "Allahabad High Court", "13", ["Lucknow"]],
  ["calcutta", "Calcutta High Court", "16", []],
  ["gujarat", "Gujarat High Court", "17", []],
].map(([code, name, state, benches]) => ({
  code,
  name,
  state_code: state,
  registry_benches: (benches as string[]).map((b) => ({ code: `${code}-${b.toLowerCase()}`, name: b })),
  supported: code !== "calcutta",
  support_note: code === "calcutta" ? "Calcutta High Court runs its own portal; the court library can only search its orders by case number." : "",
}));

const BENCHES: Record<string, { code: string; name: string; default: boolean }[]> = {
  telangana: [{ code: "1", name: "Principal Bench at Hyderabad", default: true }],
  bombay: [
    { code: "1", name: "Appellate Side,Bombay", default: true },
    { code: "4", name: "Bench at Nagpur", default: true },
    { code: "3", name: "Bench at Aurangabad", default: true },
    { code: "5", name: "High court of Bombay at Goa", default: true },
    { code: "2", name: "Original Side,Bombay", default: false },
    { code: "7", name: "Bombay High Court,Bench at Kolhapur", default: false },
  ],
};

const row = (cnr: string, no: string, parties: [string, string], advocate: string, court: string, status: string, match: "matched" | "check" | "excluded" | "other", extra = {}) => ({
  case_number: no,
  case_type: no.split("/")[0],
  cnr_number: cnr,
  filing_number: "",
  registration_number: "",
  registration_date: null,
  petitioner: parties[0],
  respondent: parties[1],
  status,
  court_name: court,
  judges: [],
  next_hearing_date: null,
  advocate_match_verified: match === "matched",
  matched_advocate_text: advocate,
  listed_advocate_name: advocate,
  listed_advocates: [advocate],
  complex_name: court,
  dist_name: "Adilabad",
  match_status: match,
  match_label: { matched: "Your name", check: "Check name", excluded: "Hidden (Not me)", other: "Other name" }[match],
  case_year: Number(no.split("/")[2]),
  ...extra,
});

const RESULT_ROWS = [
  row("TSAD01", "OS/740/2015", ["Venkat Rao", "State Bank of India"], "S Rambabu", "Adilabad Court Complex", "Pending", "matched"),
  row("TSAD02", "CC/312/2019", ["State of Telangana", "M. Anil"], "Rambabu S", "Adilabad Court Complex", "Disposed", "matched"),
  row("TSAD03", "AS/55/2021", ["K. Lakshmi", "P. Reddy"], "S Ram babu", "Nirmal Court Complex", "Pending", "matched"),
  row("TSAD04", "WP/1709/2026", ["Butham Srinivas", "Respondent"], "Rambabu S", "Adilabad Court Complex", "Pending", "matched"),
  row("TSAD05", "CC/88/2020", ["State of Telangana", "D. Ramesh"], "S Rambabu", "Nirmal Court Complex", "Pending", "matched"),
  row("TSAD06", "OS/118/2018", ["G. Narsaiah", "Mandal Revenue Officer"], "Rambabu", "Mancherial Court Complex", "Pending", "check"),
  row("TSAD07", "MC/12/2022", ["A. Kumar", "Ravi Teja"], "Rambabu", "Khanapur Court Complex", "Disposed", "check"),
  row("TSAD08", "EP/9/2017", ["Rao Finance", "Y. Satish"], "S Ram babu", "Nirmal Court Complex", "Disposed", "matched"),
  row("TSAD09", "OS/301/2016", ["M. Prasad", "Gram Panchayat"], "S Rambabu", "Adilabad Court Complex", "Pending", "matched"),
  row("TSAD10", "CC/44/2023", ["State of Telangana", "R. Naik"], "Rambabu S", "Mancherial Court Complex", "Pending", "matched"),
  row("TSAD11", "AS/12/2019", ["T. Devi", "K. Mohan"], "S Ram babu", "Nirmal Court Complex", "Disposed", "matched"),
  row("TSAD12", "OS/87/2022", ["Sri Ram Finance", "B. Yadav"], "Rambabu", "Khanapur Court Complex", "Pending", "check"),
  row("TSAD13", "CC/230/2018", ["State of Telangana", "V. Goud"], "Rambabu S", "Adilabad Court Complex", "Disposed", "matched"),
  row("TSAD14", "EP/21/2020", ["P. Kumari", "A. Rao"], "S Rambabu", "Mancherial Court Complex", "Pending", "matched"),
  row("TSAD15", "OS/5/2014", ["X", "Y"], "T Rambabu", "Adilabad Court Complex", "Pending", "excluded"),
  row("TSAD16", "OS/6/2014", ["X", "Z"], "Rambabu Reddy", "Nirmal Court Complex", "Pending", "excluded"),
  row("TSAD17", "OS/7/2013", ["Q", "R"], "G Rambabu", "Nirmal Court Complex", "Pending", "other"),
];

const run = (id: number, dist: string, name: string, status: string, extra = {}) => ({
  id, dist_code: dist, dist_name: dist, complex_name: name, status, attempts: 1, error_code: "", reason: "", raw_count: 0, matched_count: 0,
  seconds: null, started_at: null, finished_at: null, ...extra,
});
const done = (id: number, dist: string, name: string, matched: number, seconds: number) =>
  run(id, dist, name, "done", { matched_count: matched, raw_count: matched, seconds, started_at: ago(5), finished_at: ago(4) });

const failedA = run(3, "Adilabad", "Bhainsa Court Complex", "failed", {
  attempts: 3, error_code: "portal_disconnect", reason: "Portal disconnected. 3 attempts.", finished_at: ago(2),
});
const failedB = run(4, "Adilabad", "Utnoor Court Complex", "failed", {
  attempts: 4, error_code: "captcha_failed", reason: "Captcha not solved. 4 attempts.", finished_at: ago(3),
});

const group = (name: string, runs: ReturnType<typeof run>[]) => ({
  dist_code: name, name, total: runs.length,
  done: runs.filter((r) => r.status === "done").length,
  failed: runs.filter((r) => r.status === "failed").length,
  running: runs.filter((r) => r.status === "running").length,
  runs,
});

const COURTS_RUNNING = {
  job: { id: 7, status: "running", cancel_requested: false, created_at: ago(3), started_at: ago(3), is_retrying: false, retry_job_id: null, can_retry: false },
  counts: { total: 10, done: 5, failed: 2, running: 1, pending: 2, raw: 40, matched: 13 },
  seconds_left: 120,
  needs_attention: [failedA, failedB],
  groups: [
    group("Adilabad", [done(1, "Adilabad", "Adilabad Court Complex", 6, 38), done(2, "Adilabad", "Khanapur Court Complex", 1, 12), failedA, failedB]),
    group("Nirmal", [done(5, "Nirmal", "Nirmal Court Complex", 5, 41), done(6, "Nirmal", "Bhainsa (Nirmal) Court Complex", 0, 9), done(7, "Nirmal", "Khanapur (Nirmal) Court Complex", 1, 14)]),
    group("Mancherial", [run(8, "Mancherial", "Mancherial Court Complex", "running", { reason: "Searching" }), run(9, "Mancherial", "Bellampalli Court Complex", "pending", { reason: "Waiting" }), run(10, "Mancherial", "Chennur Court Complex", "pending", { reason: "Waiting" })]),
  ],
  court_site_url: "https://services.ecourts.gov.in/ecourtindia_v6/",
};

const COURTS_DONE = {
  ...COURTS_RUNNING,
  job: { ...COURTS_RUNNING.job, id: 8, status: "succeeded", can_retry: true },
  counts: { total: 10, done: 8, failed: 2, running: 0, pending: 0, raw: 60, matched: 14 },
  seconds_left: null,
  groups: COURTS_RUNNING.groups.map((g) => ({ ...g, runs: g.runs.map((r) => (r.status === "failed" ? r : { ...r, status: "done", started_at: ago(8), finished_at: ago(3) })) })),
};

const jobResult = (status: string, rows: typeof RESULT_ROWS, extra = {}) => ({
  status, progress_current: 3, progress_total: 3, error: "", results: rows, results_total: rows.length, results_truncated: false, failures: [],
  districts_total: 3, districts_status: {}, complexes_searched: 8, complexes_done: 10, complexes_total_known: 10, current_district: "",
  mode: "districts", created_at: ago(8), started_at: ago(8), profile_id: 1, v2: true, court_type: "district", search_by: "names",
  queries: ["Rambabu", "Ram babu"], state_code: "29", hc_court_name: "",
  match_counts: {
    matched: rows.filter((r) => r.match_status === "matched").length,
    check: rows.filter((r) => r.match_status === "check").length,
    excluded: 9, other: 2,
  },
  ...extra,
});

async function mockSearchApi(page: Page) {
  await mockApi(page, {});
  // Registered after mockApi's catch-all, so these answer first.
  await page.route("http://localhost:8000/api/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname.replace(/^\/api/, "");
    const send = (data: unknown) => route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify(data) });
    if (route.request().method() === "OPTIONS") return route.fallback();
    if (p === "/advocate-search/features/") return send({ v2: true, seconds_per_call: 36 });
    if (p === "/advocate-profiles/") return send([profile]);
    if (p === "/cases/search-advocate/preference/")
      return send({ court_type: "district", hierarchy_config: { state_code: "29", dist_codes: ["1", "2", "3"] }, quick_search: null });
    if (p === "/cases/search-advocate/active/") return send([]);
    if (p === "/court-structure/") {
      const q = url.searchParams;
      if (q.get("dist_code")) {
        const n = COMPLEX_COUNTS[q.get("dist_code")!] ?? 3;
        return send({ options: Object.fromEntries(Array.from({ length: n }, (_, i) => [`c${i}@e@N`, `Complex ${i + 1}`])) });
      }
      return send({ options: q.get("state_code") ? DISTRICTS : STATES });
    }
    if (p === "/cases/high-courts/") return send({ courts: HIGH_COURTS });
    const benches = /^\/cases\/high-courts\/([a-z-]+)\/benches\/$/.exec(p);
    if (benches) return send({ court: HIGH_COURTS.find((c) => c.code === benches[1]), benches: BENCHES[benches[1]] ?? BENCHES.telangana });
    if (p === "/cases/search-advocate/7/") return send(jobResult("running", RESULT_ROWS.slice(0, 8), { match_counts: { matched: 6, check: 2, excluded: 9, other: 0 } }));
    if (p === "/cases/search-advocate/7/courts/") return send(COURTS_RUNNING);
    if (p === "/cases/search-advocate/8/") return send(jobResult("succeeded", RESULT_ROWS));
    if (p === "/cases/search-advocate/8/courts/") return send(COURTS_DONE);
    if (p === "/cases/") return send([{ id: 1, cnr_number: "TSAD04", case_number: "WP/1709/2026", title: "Butham Srinivas vs. Respondent" }]);
    return route.fallback();
  });
}

const SCREENS = [
  { name: "01_district_tab", url: "/cases/search?tab=district", ready: /Where to search/ },
  { name: "02_high_court_map_telangana", url: "/cases/search?tab=hc&court=telangana", ready: /Search Telangana High Court/ },
  { name: "03_high_court_map_bombay_group", url: "/cases/search?tab=hc&court=bombay", ready: /Search Bombay High Court/ },
  { name: "04_search_running_court_status", url: "/cases/search?tab=district&job=7", ready: /Needs attention/ },
  { name: "05_results_list", url: "/cases/search?tab=district&job=8", ready: /Advocate as listed/ },
] as const;

for (const screen of SCREENS) {
  for (const { width, height } of SIZES) {
    test(`${screen.name} is one screen at ${width}x${height}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await mockSearchApi(page);
      await page.goto(screen.url);
      await expect(page.getByText(screen.ready).first()).toBeVisible({ timeout: 20_000 });
      await page.waitForTimeout(700);

      const fit = await page.evaluate(() => {
        const main = document.querySelector("main > div") as HTMLElement;
        const doc = document.scrollingElement as HTMLElement;
        return {
          mainOverflow: main.scrollHeight - main.clientHeight,
          docOverflow: doc.scrollHeight - window.innerHeight,
          sideways: doc.scrollWidth - window.innerWidth,
        };
      });
      if (process.env.SHOTS_DIR) {
        await page.screenshot({ path: path.join(process.env.SHOTS_DIR, `${screen.name}_${width}x${height}.png`) });
      }
      console.log(`${screen.name} ${width}x${height}: page overflow ${fit.mainOverflow}px, document ${fit.docOverflow}px, sideways ${fit.sideways}px`);
      expect(fit.mainOverflow).toBeLessThanOrEqual(1);
      expect(fit.docOverflow).toBeLessThanOrEqual(1);
      expect(fit.sideways).toBeLessThanOrEqual(1);
    });
  }
}

test("Not me hides the row and its siblings at once, with no new search", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockSearchApi(page);
  let posted = 0;
  // After the Not me is saved the server answers the same search with those rows relabelled.
  await page.route("http://localhost:8000/api/cases/search-advocate/8/", async (route) => {
    const rows = RESULT_ROWS.map((r) => (posted > 0 && r.listed_advocate_name === "Rambabu" ? { ...r, match_status: "excluded", match_label: "Hidden (Not me)" } : r));
    await route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify(jobResult("succeeded", rows as typeof RESULT_ROWS)) });
  });
  await page.route("http://localhost:8000/api/advocate-profiles/1/exclude/", async (route) => {
    posted += 1;
    await route.fulfill({
      status: 200, contentType: "application/json", headers: CORS,
      body: JSON.stringify({ ...profile, name_forms: ["Ram babu"], excluded_names: [...profile.excluded_names, "Rambabu"] }),
    });
  });
  await page.goto("/cases/search?tab=district&job=8");
  await expect(page.getByText("Advocate as listed")).toBeVisible({ timeout: 20_000 });
  const before = await page.getByRole("row").filter({ hasText: "OS/118/2018" }).count();
  expect(before).toBe(1);
  await page.getByRole("button", { name: "Not me: Rambabu" }).first().click();
  await expect(page.getByRole("row").filter({ hasText: "OS/118/2018" })).toHaveCount(0); // moved at once
  await expect(page.getByRole("row").filter({ hasText: "MC/12/2022" })).toHaveCount(0); // so did the other row listing "Rambabu"
  await expect.poll(() => posted).toBe(1);
  // and it stays that way once the server's answer replaces the guess
  await page.waitForTimeout(500);
  await expect(page.getByRole("row").filter({ hasText: "OS/118/2018" })).toHaveCount(0);
});

test("Show hidden reveals the Not me rows, and the filters live in the URL", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockSearchApi(page);
  await page.goto("/cases/search?tab=district&job=8");
  await expect(page.getByText("Advocate as listed")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("row").filter({ hasText: "OS/5/2014" })).toHaveCount(0);
  await page.getByRole("button", { name: /Show hidden/ }).click();
  await page.getByLabel(/Not me list/).click(); // the state comes back from the URL a tick later
  await expect(page.getByRole("row").filter({ hasText: "OS/5/2014" })).toHaveCount(1);
  await expect(page).toHaveURL(/excl=1/);
  await page.getByRole("button", { name: "Needs a check" }).click();
  await expect(page).toHaveURL(/match=check/);
  await expect(page.getByRole("row").filter({ hasText: "OS/118/2018" })).toHaveCount(1);
  await expect(page.getByRole("row").filter({ hasText: "OS/740/2015" })).toHaveCount(0);
});

test("a district list that fails to load shows an error with Retry, not an empty list", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockSearchApi(page);
  let failing = true;
  await page.route(/\/api\/court-structure\/\?.*state_code=29$/, async (route) => {
    if (failing) return route.fulfill({ status: 502, contentType: "application/json", headers: CORS, body: JSON.stringify({ detail: "down" }) });
    return route.fallback();
  });
  await page.goto("/cases/search?tab=district");
  await expect(page.getByRole("alert").filter({ hasText: "didn't send the districts" })).toBeVisible({ timeout: 40_000 });
  failing = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Adilabad" }).first()).toBeVisible();
});

test("an unsupported High Court is greyed and cannot be chosen", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockSearchApi(page);
  await page.goto("/cases/search?tab=hc");
  const calcutta = page.getByRole("button", { name: /Calcutta/ });
  await expect(calcutta).toBeDisabled();
  await expect(calcutta).toHaveAttribute("title", /orders by case number/);
});

test("the High Court search box is a keyboard combobox", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockSearchApi(page);
  await page.goto("/cases/search?tab=hc");
  const box = page.getByRole("combobox", { name: "Search a High Court" });
  await box.click();
  await box.fill("bomb");
  await box.press("Enter");
  await expect(page).toHaveURL(/court=bombay/);
  await expect(page.getByText(/Search Bombay High Court/).first()).toBeVisible();
});

// The India map is off until its outline has been checked (NEXT_PUBLIC_HC_MAP).
// With it on, these show it and keep it to one screen. Run with
// NEXT_PUBLIC_HC_MAP=true; skipped otherwise.
for (const [court, name] of [["telangana", "02_high_court_map_telangana"], ["bombay", "03_high_court_map_bombay_group"]] as const) {
  for (const { width, height } of SIZES) {
    test(`with the map on, ${name} is one screen at ${width}x${height}`, async ({ page }) => {
      test.skip(process.env.NEXT_PUBLIC_HC_MAP !== "true", "the map is off by default");
      await page.setViewportSize({ width, height });
      await mockSearchApi(page);
      await page.goto(`/cases/search?tab=hc&court=${court}`);
      await expect(page.getByTestId("india-map")).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(new RegExp(`Search ${court === "bombay" ? "Bombay" : "Telangana"} High Court`)).first()).toBeVisible();
      await page.waitForTimeout(700);
      const fit = await page.evaluate(() => {
        const main = document.querySelector("main > div") as HTMLElement;
        return { overflow: main.scrollHeight - main.clientHeight, sideways: document.documentElement.scrollWidth - window.innerWidth };
      });
      if (process.env.SHOTS_DIR) await page.screenshot({ path: path.join(process.env.SHOTS_DIR, `MAP_${name}_${width}x${height}.png`) });
      expect(fit.overflow).toBeLessThanOrEqual(1);
      expect(fit.sideways).toBeLessThanOrEqual(1);
    });
  }
}
