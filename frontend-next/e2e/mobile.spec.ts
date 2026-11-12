import { expect, test, type Page } from "@playwright/test";
import { mobileCases, mobileHearings, mockMobileApi } from "./mobile-fixtures";
import { mockFeeApi } from "./billing-fixtures";

// The phone layouts (< 768px wide): nothing scrolls sideways, the key content
// of each screen shows, the bottom bar works, and the sheets behave. The API
// is mocked in the browser (mobile-fixtures.ts); no backend is needed.
//
// Set SHOTS_DIR to also save a screenshot of each screen.

const SHOTS = process.env.SHOTS_DIR;
const WIDTHS = [360, 390, 430] as const;
const HEIGHT = 844;

interface Screen {
  name: string;
  url: string;
  /** Text that must be on screen once it has loaded. */
  ready: RegExp;
}

const SCREENS: Screen[] = [
  { name: "dashboard", url: "/dashboard", ready: /Today in court/ },
  { name: "cases", url: "/cases", ready: /Needs Attention This Week/ },
  { name: "case", url: "/cases/1", ready: /Next hearing/i },
  { name: "calendar", url: "/calendar", ready: /upcoming hearings across all cases/ },
  { name: "billing", url: "/billing", ready: /Outstanding by client/ },
  { name: "documents", url: "/documents", ready: /documents across all cases/ },
];

async function openScreen(page: Page, width: number, url: string) {
  await page.setViewportSize({ width, height: HEIGHT });
  await mockMobileApi(page);
  await page.goto(url);
}

/** Widest thing on the page vs the viewport: any element sticking out to the
 * right of it (and not inside a deliberate sideways scroller) is a bug. */
async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const vw = window.innerWidth;
    const scroller = document.querySelector<HTMLElement>("[data-page-scroll]");
    const offenders: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0 || r.right <= vw + 1) continue;
      // Inside a row that scrolls sideways on purpose, or off-canvas chrome.
      if (el.closest(".ci-hscroll, [aria-hidden='true'], nextjs-portal, [data-nextjs-toast]")) continue;
      if (getComputedStyle(el).position === "fixed" && el.closest("nextjs-portal")) continue;
      offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 50)} right=${Math.round(r.right)}`);
      if (offenders.length >= 5) break;
    }
    return {
      docOverflow: document.documentElement.scrollWidth - vw,
      bodyOverflow: document.body.scrollWidth - vw,
      scrollerOverflow: scroller ? scroller.scrollWidth - scroller.clientWidth : 0,
      offenders,
    };
  });
}

for (const width of WIDTHS) {
  for (const screen of SCREENS) {
    test(`${screen.name} does not scroll sideways at ${width}px`, async ({ page }) => {
      await openScreen(page, width, screen.url);
      await expect(page.getByText(screen.ready).first()).toBeVisible();
      await page.waitForTimeout(700);
      const o = await horizontalOverflow(page);
      expect(o.docOverflow).toBeLessThanOrEqual(0);
      expect(o.bodyOverflow).toBeLessThanOrEqual(0);
      expect(o.scrollerOverflow).toBeLessThanOrEqual(0);
      expect(o.offenders).toEqual([]);
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-${screen.name}-${width}.png` });
    });
  }
}

test("the bottom bar goes between screens and shows where you are", async ({ page }) => {
  await openScreen(page, 390, "/dashboard");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav).toBeVisible();
  await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");

  // Every tab is a 44px-plus target.
  for (const label of ["Home", "Cases", "Docs", "Calendar", "Inbox", "Billing"]) {
    const box = await nav.getByRole("link", { name: new RegExp(label) }).boundingBox();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    expect(box!.width).toBeGreaterThanOrEqual(44);
  }

  const before = await nav.getByTestId("nav-indicator").evaluate((el) => (el as HTMLElement).style.transform);
  await nav.getByRole("link", { name: "Calendar" }).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await expect(nav.getByRole("link", { name: "Calendar" })).toHaveAttribute("aria-current", "page");
  const after = await nav.getByTestId("nav-indicator").evaluate((el) => (el as HTMLElement).style.transform);
  expect(after).not.toEqual(before);
  await nav.getByRole("link", { name: "Cases" }).click();
  await expect(page).toHaveURL(/\/cases$/);
});

test("the dashboard leads with today in court and lets a task be ticked off", async ({ page }) => {
  await openScreen(page, 390, "/dashboard");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/Good (morning|afternoon|evening), Bhagath/);
  const today = page.getByRole("region", { name: "Today in court" });
  await expect(today.getByRole("link", { name: /Butham Srinivas/ })).toBeVisible();
  // What is due: the overdue task is flagged.
  const needs = page.getByRole("region", { name: "Needs you" });
  await expect(needs.getByText(/overdue/i).first()).toBeVisible();

  const tick = needs.getByRole("button", { name: /Mark done: File counter affidavit/ });
  await tick.click();
  // The row folds away (its height animates to 0, then it is clipped).
  await expect(needs.getByRole("button", { name: /Mark done: File counter affidavit/ })).toBeDisabled();
  await page.waitForTimeout(1100);
  const row = needs.getByRole("listitem").filter({ hasText: "File counter affidavit" });
  expect((await row.boundingBox())?.height ?? 0).toBeLessThan(4);
});

test("a section's open/closed state is remembered", async ({ page }) => {
  await openScreen(page, 390, "/dashboard");
  const toggle = page.getByRole("button", { name: /^Today in court/ });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await page.reload();
  await expect(page.getByRole("button", { name: /^Today in court/ })).toHaveAttribute("aria-expanded", "false");
});

test("cases: next hearing first, status tabs pinned, options in a sheet", async ({ page }) => {
  await openScreen(page, 390, "/cases");
  const card = page.getByRole("link", { name: /Open case Meera Nair/ });
  await expect(card).toContainText("Next hearing");
  await expect(card).toContainText("Tomorrow");
  // The status tabs sit in the top bar and stay when the list scrolls.
  const tabs = page.getByRole("tablist", { name: "Case status" });
  await expect(tabs).toBeVisible();
  await page.locator("[data-page-scroll]").evaluate((el) => el.scrollTo(0, 400));
  await page.waitForTimeout(500);
  await expect(tabs).toBeInViewport();
  expect((await tabs.boundingBox())!.y).toBeLessThan(60);

  await page.getByRole("button", { name: "Case options" }).first().click();
  const sheet = page.getByRole("dialog", { name: "Case options" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Delete case" })).toBeVisible();
  await page.waitForTimeout(600); // let it finish rising
  const box = (await sheet.boundingBox())!;
  // A sheet: full width, on the bottom edge.
  expect(Math.round(box.width)).toBe(390);
  expect(Math.round(box.y + box.height)).toBe(HEIGHT);
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
});

test("the case page: title in the bar, next hearing first, tabs, Case Bot sheet", async ({ page }) => {
  await openScreen(page, 390, "/cases/1");
  const summary = page.getByRole("region", { name: "Next hearing" });
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("Hearing on interim application");
  await expect(page.getByTestId("mobile-page-header")).toBeVisible();
  await expect(page.getByRole("link", { name: "Back to cases" })).toBeVisible();

  // Four tabs, pinned under the bar.
  const tabs = page.getByRole("tablist", { name: "Case sections" });
  await expect(tabs.getByRole("tab")).toHaveCount(4);
  await page.getByRole("tab", { name: "Hearings" }).click();
  await expect(page.getByRole("heading", { name: /Hearings & orders/ })).toBeVisible();
  // Tap a hearing: its details open as a sheet.
  await page.getByRole("button", { name: /Open details/ }).first().click();
  const sheet = page.getByRole("dialog", { name: "Hearing details" });
  await expect(sheet).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();

  await page.getByRole("tab", { name: "Documents" }).click();
  await expect(page.getByRole("region", { name: "Documents" })).toBeVisible();

  // The Case Bot is a button at the thumb and opens over the page.
  const bot = page.getByRole("button", { name: "Ask the Case Bot" });
  await expect(bot).toBeVisible();
  const botBox = (await bot.boundingBox())!;
  expect(botBox.height).toBeGreaterThanOrEqual(44);
  await bot.click();
  await expect(page.getByRole("dialog").or(page.getByText("Case Bot").first())).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-case-bot.png` });
});

test("a High Court case has no daily-status card: those courts publish order documents", async ({ page }) => {
  await openScreen(page, 390, "/cases/1");
  await expect(page.getByRole("region", { name: "Next hearing" })).toBeVisible();
  await expect(page.getByTestId("daily-status-slot")).toHaveCount(0);
});

test("a district case shows what the court recorded at the last hearing, under the next hearing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: HEIGHT });
  const day = (offset: number) => new Date(Date.now() + 330 * 60_000 + offset * 86_400_000).toISOString().slice(0, 10); // India date
  const mine = mobileCases[0];
  await mockMobileApi(page, {
    "/cases/1/": { ...mine, court_type: "district", cnr_number: "TSHS020000882016" },
    "/cases/1/daily-status/": [
      {
        business_date: day(-2),
        court_name: "IV Addl. Rent Controller-cum-XVI Junior Civil Judge",
        business_text: "Petitioner counsel present. Respondent counsel absent. Memo filed by the petitioner counsel stay is granted. Hence call on the next date.",
        next_purpose: "STAY",
        next_hearing_date: day(12),
        fetched_at: new Date().toISOString(),
      },
      {
        business_date: day(-30),
        court_name: "IV Addl. Rent Controller-cum-XVI Junior Civil Judge",
        business_text: "Both counsel present. Time granted for counter.",
        next_purpose: "COUNTER",
        next_hearing_date: day(-2),
        fetched_at: new Date().toISOString(),
      },
    ],
  });
  await page.goto("/cases/1");
  const slot = page.getByTestId("daily-status-slot");
  await expect(slot).toBeVisible({ timeout: 20_000 });
  await expect(slot).toContainText("Daily status");
  await expect(slot).toContainText("STAY");
  await expect(slot).toContainText("Petitioner counsel present");
  // it sits after the next-hearing card, not above it
  const [hearing, status] = await Promise.all([
    page.getByRole("region", { name: "Next hearing" }).boundingBox(),
    slot.boundingBox(),
  ]);
  expect(status!.y).toBeGreaterThan(hearing!.y);
  await page.waitForTimeout(700); // let the page-in animation settle before measuring
  const o = await horizontalOverflow(page);
  expect(o.scrollerOverflow).toBeLessThanOrEqual(0);
  expect(o.offenders).toEqual([]);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-case-daily-status-390.png` });
});

// What the court recorded at each hearing of a district case. Dates hang off
// the India day (like the app), never the UTC date.
const indiaDay = (offset: number) => new Date(Date.now() + 330 * 60_000 + offset * 86_400_000).toISOString().slice(0, 10);

function districtHearingMocks() {
  const mine = mobileCases[0];
  const passed = mobileHearings.find((h) => h.id === 107)!;
  return {
    "/cases/1/": { ...mine, court_type: "district", cnr_number: "TSHS020000882016" },
    "/hearings/": [
      ...mobileHearings.filter((h) => h.case === mine.id).map((h) => (h.id === 107 ? { ...h, business_date: indiaDay(-6) } : h)),
      // The court lists business for this one, but it is not saved yet.
      { ...passed, id: 108, hearing_date: `${indiaDay(-20)}T04:30:00Z`, business_date: indiaDay(-20), outcome: null, purpose: "Evidence" },
    ],
    "/cases/1/daily-status/": [
      {
        business_date: indiaDay(-6),
        court_name: "IV Addl. Rent Controller-cum-XVI Junior Civil Judge",
        business_text:
          "Petitioner counsel present. Respondent counsel absent.\nMemo filed by the petitioner counsel stay is granted. Hence call on 19.11.2026.",
        next_purpose: "STAY",
        next_hearing_date: indiaDay(12),
        fetched_at: new Date().toISOString(),
      },
    ],
    "/cases/1/orders/check/": {
      order_sync: { state: "queued", last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: null },
    },
  };
}

test("a district case's Hearings tab: a preview in the row, what happened in the sheet", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: HEIGHT });
  await mockMobileApi(page, districtHearingMocks());
  await page.goto("/cases/1");
  await page.getByRole("tab", { name: "Hearings" }).click();

  // The passed hearing with a record shows one preview line; the others none.
  const preview = page.getByTestId("hearing-business-preview");
  await expect(preview).toHaveCount(1, { timeout: 20_000 });
  await expect(preview).toContainText("Petitioner counsel present.");
  const previewBox = (await preview.boundingBox())!;
  expect(previewBox.height).toBeLessThan(20); // one line
  await page.waitForTimeout(700);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-hearings-preview-390.png` });

  // Tap it: the full text, the next purpose and the next hearing.
  await page.getByRole("button", { name: /What happened is saved/ }).click();
  const sheet = page.getByRole("dialog", { name: "Hearing details" });
  await expect(sheet).toBeVisible();
  const section = sheet.getByRole("region", { name: "What happened" });
  await expect(section).toContainText("Petitioner counsel present. Respondent counsel absent.");
  await expect(section).toContainText("Memo filed by the petitioner counsel stay is granted. Hence call on 19.11.2026.");
  await expect(section).toContainText("Next purpose");
  await expect(section).toContainText("STAY");
  await expect(section).toContainText("Next hearing");
  await expect(section).toContainText("In 12 days");
  await page.waitForTimeout(900); // the sheet and the section have settled
  const [sheetBox, sectionBox] = await Promise.all([sheet.boundingBox(), section.boundingBox()]);
  expect(sheetBox!.width).toBeLessThanOrEqual(390);
  expect(sectionBox!.x + sectionBox!.width).toBeLessThanOrEqual(390);
  const o = await horizontalOverflow(page);
  expect(o.docOverflow).toBeLessThanOrEqual(0);
  expect(o.scrollerOverflow).toBeLessThanOrEqual(0);
  expect(o.offenders).toEqual([]);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-hearings-sheet-390.png` });
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
});

test("a district hearing with no saved record offers Check now, which queues the order check", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: HEIGHT });
  await mockMobileApi(page, districtHearingMocks());
  await page.goto("/cases/1");
  await page.getByRole("tab", { name: "Hearings" }).click();
  // The 20-days-ago hearing: listed by the court, not saved.
  await page.getByRole("button", { name: /Open details/ }).nth(2).click();
  const section = page.getByRole("dialog", { name: "Hearing details" }).getByRole("region", { name: "What happened" });
  await expect(section).toContainText("What happened is not saved yet.");
  await page.waitForTimeout(900); // the sheet and the section have settled
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-hearings-sheet-not-saved-390.png` });
  const queued = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/cases/1/orders/check/"));
  await section.getByRole("button", { name: "Check now" }).click();
  await queued;
});

test("desktop: a district hearing row opens what happened under itself, and the layout holds", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMobileApi(page, districtHearingMocks());
  await page.goto("/cases/1");
  const card = page.getByRole("region", { name: "Hearings & orders" });
  await expect(card).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(700);

  const toggle = card.getByRole("button", { name: /^What happened on / }).first();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  // The collapsed row is the same 40px row.
  const rowBox = (await toggle.locator("xpath=..").boundingBox())!;
  expect(Math.round(rowBox.height)).toBe(40);
  const before = (await card.boundingBox())!;
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-hearings-desktop-collapsed-1440.png` });

  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const section = card.getByRole("region", { name: "What happened" });
  await expect(section).toContainText("Petitioner counsel present. Respondent counsel absent.");
  await expect(section).toContainText("Next purpose");
  await expect(section).toContainText("STAY");
  await expect(section).toContainText("In 12 days");
  await page.waitForTimeout(700);

  // The card keeps its size and the page still does not scroll.
  const after = (await card.boundingBox())!;
  expect(Math.round(after.height)).toBe(Math.round(before.height));
  expect(Math.round(after.width)).toBe(Math.round(before.width));
  const doc = await page.evaluate(() => ({
    scroll: (document.scrollingElement as HTMLElement).scrollHeight,
    inner: window.innerHeight,
  }));
  expect(doc.scroll).toBeLessThanOrEqual(doc.inner);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-hearings-desktop-expanded-1440.png` });

  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(section).toBeHidden();
});

test("the calendar is an agenda: pick a day from the week strip", async ({ page }) => {
  await openScreen(page, 390, "/calendar");
  const strip = page.getByRole("group", { name: "Week" });
  await expect(strip.getByRole("button")).toHaveCount(7);
  const selected = page.getByRole("region", { name: "Selected day" });
  await expect(selected).toContainText("Butham Srinivas");
  // Next week, then Today brings it back.
  await page.getByRole("button", { name: "Next week" }).click();
  await expect(selected).toContainText("Client call");
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await expect(selected).toContainText("Butham Srinivas");
  await page.getByRole("tab", { name: "Month" }).click();
  await expect(page.getByText("November 2026").first()).toBeVisible();
});

test("billing shows a card per client, not a table", async ({ page }) => {
  // The charges come from /appearance-fees/ (billing-fixtures.ts): two clients owe money.
  await page.setViewportSize({ width: 390, height: HEIGHT });
  await mockMobileApi(page);
  await mockFeeApi(page);
  await page.goto("/billing");
  await expect(page.getByRole("heading", { name: "Outstanding by client" })).toBeVisible();
  await expect(page.locator("table")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Statement for/ })).toHaveCount(2);
});

test("documents: filters fold away, actions are in a sheet", async ({ page }) => {
  await openScreen(page, 390, "/documents");
  const filters = page.getByRole("button", { name: /Filters/ });
  await expect(filters).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("combobox").first()).not.toBeVisible();
  await filters.click();
  await expect(page.getByRole("combobox").first()).toBeVisible();
  await page.getByRole("button", { name: "Document actions" }).first().click();
  const sheet = page.getByRole("dialog", { name: "Document actions" });
  await expect(sheet.getByRole("button", { name: /Delete/ })).toBeVisible();
});

test("the top bar slides away while reading down and returns on the way up", async ({ page }) => {
  await openScreen(page, 390, "/dashboard");
  await expect(page.getByText(/Today in court/).first()).toBeVisible();
  const header = page.locator(".ci-mobile-header");
  const scroller = page.locator("[data-page-scroll]");
  const top = async () => (await header.boundingBox())!.y;
  const max = await scroller.evaluate((el) => el.scrollHeight - el.clientHeight);
  expect(max).toBeGreaterThan(300); // long enough to read down
  expect(await top()).toBe(0);
  await scroller.evaluate((el, y) => el.scrollTo(0, y), 200);
  await page.waitForTimeout(100);
  await scroller.evaluate((el, y) => el.scrollTo(0, y), max);
  await page.waitForTimeout(700);
  expect(await top()).toBeLessThan(-40);
  await scroller.evaluate((el, y) => el.scrollTo(0, y), max - 120);
  await page.waitForTimeout(700);
  expect(await top()).toBe(0);
});

test("prefers-reduced-motion switches the animations off", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 390, height: HEIGHT } });
  const page = await context.newPage();
  await mockMobileApi(page);
  await page.goto("/dashboard");
  await expect(page.getByText(/Today in court/).first()).toBeVisible();
  const names = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("*"))
      .map((el) => getComputedStyle(el))
      .filter((cs) => cs.animationName !== "none" && !cs.animationName.startsWith("ci-shimmer"))
      .map((cs) => cs.animationName),
  );
  expect(names).toEqual([]);
  await context.close();
});

test("desktop is unchanged: sidebar, no bottom bar, the Briefing", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockMobileApi(page);
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard", level: 1 })).toBeVisible();
  await expect(page.locator("nav.fixed[aria-label='Main']")).toBeHidden();
  await expect(page.getByTestId("mobile-dashboard")).toHaveCount(0);
  await expect(page.getByText("Search cases, documents, clients")).toBeVisible();
  const header = await page.locator("header").first().boundingBox();
  expect(Math.round(header!.height)).toBe(67);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/spec-desktop-dashboard-1440.png` });
});
