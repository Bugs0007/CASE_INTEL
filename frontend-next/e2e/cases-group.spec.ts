import { expect, test, type Page } from "@playwright/test";
import { mobileCases, mockMobileApi } from "./mobile-fixtures";

// "Group by court / client" on the Cases page, on a desktop (1440x900) and a
// phone (390x844). The API is mocked in the browser (mobile-fixtures.ts); no
// backend is needed. Set SHOTS_DIR to also save screenshots.

const SHOTS = process.env.SHOTS_DIR;
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };

const HC = "Telangana High Court";
const MAGISTRATE = "XII Addl. Chief Metropolitan Magistrate, Hyderabad";
const SESSIONS = "Metropolitan Sessions Judge, Hyderabad";
const FAMILY = "Family Court, Secunderabad";

// The list API gives each case its court_name; the shared fixture keeps it in
// the snapshot, so lift it here. Two more cases: one at the High Court under a
// different spelling and for the same client as the first case, and one with no
// court and no client.
const withCourt = mobileCases.map((c) => ({
  ...c,
  court_name: (c.tracking_snapshot as { court_name: string }).court_name,
}));
const sameClientAtHighCourt = {
  ...withCourt[0],
  id: 21,
  title: "Butham Srinivas vs. GHMC",
  case_number: "WP/55/2026",
  court_name: "  telangana   high court ",
  needs_attention: false,
  next_hearing_date: null,
};
const nothingSet = {
  ...withCourt[0],
  id: 22,
  title: "Walk-in enquiry",
  case_number: "ENQ/1/2026",
  court_name: null,
  client_name: "",
  client_detail: null,
  needs_attention: false,
  next_hearing_date: null,
};
const cases = [...withCourt, sameClientAtHighCourt, nothingSet];

async function open(page: Page, viewport: { width: number; height: number }, url: string) {
  await page.setViewportSize(viewport);
  await mockMobileApi(page, { "/cases/": cases });
  await page.goto(url);
}

const groups = (page: Page) => page.getByTestId("case-group");
/** The grouped list only (the sidebar and other chrome may repeat a case title). */
const list = (page: Page) => page.getByTestId("case-groups");
const header = (page: Page, name: string) => page.locator("[data-testid=case-group] h3 button", { hasText: name });

/** Anything sticking out to the right of the screen (outside a deliberate sideways scroller). */
async function horizontalOverflow(page: Page) {
  return page.evaluate(() => {
    const vw = window.innerWidth;
    const offenders: string[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>("body *"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0 || r.right <= vw + 1) continue;
      if (el.closest(".ci-hscroll, [aria-hidden='true'], nextjs-portal, [data-nextjs-toast]")) continue;
      offenders.push(`${el.tagName.toLowerCase()}.${String(el.className).slice(0, 50)} right=${Math.round(r.right)}`);
      if (offenders.length >= 5) break;
    }
    return { doc: document.documentElement.scrollWidth - vw, body: document.body.scrollWidth - vw, offenders };
  });
}

test.describe("desktop 1440x900", () => {
  test("grouping None is the list as before: Needs Attention first, no group headers", async ({ page }) => {
    await open(page, DESKTOP, "/cases");
    await expect(page.getByText("Needs Attention This Week")).toBeVisible();
    await expect(page.getByText("All Other Cases")).toBeVisible();
    await expect(page.getByRole("button", { name: "View All" })).toBeVisible();
    await expect(groups(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "None", exact: true })).toHaveAttribute("aria-pressed", "true");
    // The three needs-attention cards are shown, the other five stay behind View All.
    await expect(page.getByText("Butham Srinivas vs. State of Telangana")).toBeVisible();
    await expect(page.getByText(/5 cases\s+with nothing due this week/)).toBeVisible();
    expect(await horizontalOverflow(page)).toMatchObject({ doc: 0, body: 0 });
    if (SHOTS) {
      await page.waitForTimeout(1000); // let the cards finish fading in
      await page.screenshot({ path: `${SHOTS}/desktop-none.png` });
    }
  });

  test("group by court shows a header per court with its count, soonest hearing first", async ({ page }) => {
    await open(page, DESKTOP, "/cases?group=court");
    await expect(groups(page)).toHaveCount(5);
    await expect(page.getByText("Cases by court")).toBeVisible();
    await expect(page.getByText("Needs Attention This Week")).toHaveCount(0);

    const headers = await page.locator("[data-testid=case-group] h3 button").allInnerTexts();
    // High Court (today; two spellings merged) -> Magistrate (tomorrow) -> Sessions (+2) -> Family (+9) -> none.
    expect(headers[0]).toContain(HC);
    expect(headers[0]).toMatch(/4\s*cases/i);
    expect(headers[0]).toContain("Next: Today");
    expect(headers[1]).toContain(MAGISTRATE);
    expect(headers[1]).toContain("Next: Tomorrow");
    expect(headers[2]).toContain(SESSIONS);
    expect(headers[3]).toContain(FAMILY);
    expect(headers[4]).toContain("No court set");
    expect(headers[4]).toMatch(/1\s*case/i);
    if (SHOTS) {
      await page.waitForTimeout(1000);
      await page.screenshot({ path: `${SHOTS}/desktop-grouped-court.png` });
    }
  });

  test("collapsing a group hides its cards; the rest stay; Expand all brings them back", async ({ page }) => {
    await open(page, DESKTOP, "/cases?group=court");
    const high = header(page, HC);
    const card = list(page).getByText("Butham Srinivas vs. GHMC");
    const other = list(page).getByText("Kavitha Reddy vs. Ramesh Reddy");
    await expect(card).toBeVisible();
    await expect(high).toHaveAttribute("aria-expanded", "true");

    await high.click();
    await expect(high).toHaveAttribute("aria-expanded", "false");
    await expect(card).toBeHidden();
    await expect(other).toBeVisible();

    await high.click();
    await expect(card).toBeVisible();

    await page.getByRole("button", { name: "Collapse all" }).click();
    await expect(card).toBeHidden();
    await expect(other).toBeHidden();
    await page.getByRole("button", { name: "Expand all" }).click();
    await expect(other).toBeVisible();
  });

  test("the choice and the folded groups survive a reload; the address bar carries ?group=", async ({ page }) => {
    await open(page, DESKTOP, "/cases");
    await page.getByRole("button", { name: "Court", exact: true }).click();
    await expect(page).toHaveURL(/[?&]group=court\b/);
    await expect(groups(page)).toHaveCount(5);

    await header(page, FAMILY).click();
    await expect(header(page, FAMILY)).toHaveAttribute("aria-expanded", "false");

    await page.reload();
    await expect(page).toHaveURL(/[?&]group=court\b/);
    await expect(groups(page)).toHaveCount(5);
    await expect(header(page, FAMILY)).toHaveAttribute("aria-expanded", "false");
    await expect(header(page, HC)).toHaveAttribute("aria-expanded", "true");

    // Folding the courts does not fold the clients.
    await page.getByRole("button", { name: "Client", exact: true }).click();
    await expect(page).toHaveURL(/[?&]group=client\b/);
    for (const h of await page.locator("[data-testid=case-group] h3 button").all()) {
      await expect(h).toHaveAttribute("aria-expanded", "true");
    }

    // None clears the address bar and the list is the plain one again.
    await page.getByRole("button", { name: "None", exact: true }).click();
    await expect(page).not.toHaveURL(/group=/);
    await expect(groups(page)).toHaveCount(0);
    await expect(page.getByText("Needs Attention This Week")).toBeVisible();
  });

  test("group by client uses the linked client, and opens the way it was left (URL wins)", async ({ page }) => {
    await open(page, DESKTOP, "/cases?group=client");
    await expect(groups(page)).toHaveCount(7); // 6 clients (one with two cases), plus "No client"
    await expect(header(page, "Butham Srinivas")).toContainText(/2\s*cases/i);
    await expect(header(page, "No client")).toContainText(/1\s*case/i);

    // What the reader picks is remembered: a bare /cases then opens grouped by client...
    await page.getByRole("button", { name: "Court", exact: true }).click();
    await page.getByRole("button", { name: "Client", exact: true }).click();
    await page.goto("/cases");
    await expect(page.getByText("Cases by client")).toBeVisible();
    // ...and the address bar wins over that.
    await page.goto("/cases?group=court");
    await expect(page.getByText("Cases by court")).toBeVisible();
  });

  test("a group header is a keyboard-operable button", async ({ page }) => {
    await open(page, DESKTOP, "/cases?group=court");
    const high = header(page, HC);
    await expect(high).toHaveAttribute("aria-controls", /.+/);
    await high.focus();
    await page.keyboard.press("Enter");
    await expect(high).toHaveAttribute("aria-expanded", "false");
    await page.keyboard.press("Space");
    await expect(high).toHaveAttribute("aria-expanded", "true");
  });
});

test.describe("phone 390x844", () => {
  test("grouping None is the plain list: Needs Attention first, no group headers", async ({ page }) => {
    await open(page, PHONE, "/cases");
    await expect(page.getByText("Needs Attention This Week")).toBeVisible();
    await expect(groups(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "View options" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Grouped by/ })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Open case Meera Nair/ })).toContainText("Tomorrow");
    const o = await horizontalOverflow(page);
    expect(o).toMatchObject({ doc: 0, body: 0, offenders: [] });
  });

  test("group by court: headers with counts, a chip names the grouping, nothing scrolls sideways", async ({ page }) => {
    await open(page, PHONE, "/cases?group=court");
    await expect(groups(page)).toHaveCount(5);
    await expect(page.getByRole("button", { name: /Grouped by court/ })).toBeVisible();
    await expect(header(page, HC)).toContainText(/4\s*cases/i);
    await expect(header(page, HC)).toContainText("Next: Today");
    await expect(header(page, "No court set")).toContainText(/1\s*case/i);
    await page.waitForTimeout(900); // let the cards finish rising
    expect(await horizontalOverflow(page)).toMatchObject({ doc: 0, body: 0, offenders: [] });

    // A touch target: at least 44px tall, edge to edge of the list.
    const box = (await header(page, HC).boundingBox())!;
    expect(box.height).toBeGreaterThanOrEqual(44);
    expect(box.width).toBeGreaterThan(300);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/phone-grouped-court.png` });
  });

  test("collapsing a group hides its cards", async ({ page }) => {
    await open(page, PHONE, "/cases?group=court");
    const butham = page.getByRole("link", { name: /Open case Butham Srinivas vs. State/ });
    await expect(butham).toBeVisible();
    await header(page, HC).click();
    await expect(header(page, HC)).toHaveAttribute("aria-expanded", "false");
    await expect(butham).toBeHidden();
    await expect(page.getByRole("link", { name: /Open case Kavitha Reddy/ })).toBeVisible();
    await page.getByRole("button", { name: "Collapse all" }).click();
    await expect(page.getByRole("link", { name: /Open case Kavitha Reddy/ })).toBeHidden();
    expect(await horizontalOverflow(page)).toMatchObject({ doc: 0, body: 0 });
  });

  test("the options sheet sets the grouping; it is in the URL and survives a reload", async ({ page }) => {
    await open(page, PHONE, "/cases");
    await page.getByRole("button", { name: "View options" }).click();
    const sheet = page.getByRole("dialog", { name: "View options" });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole("radio", { name: /None/ })).toHaveAttribute("aria-checked", "true");
    await page.waitForTimeout(500); // let it finish rising
    const rows = await sheet.getByRole("radio").all();
    expect(rows).toHaveLength(3);
    for (const row of rows) expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);

    await sheet.getByRole("radio", { name: /Client/ }).click();
    await expect(sheet).toBeHidden();
    await expect(page).toHaveURL(/[?&]group=client\b/);
    await expect(page.getByRole("button", { name: /Grouped by client/ })).toBeVisible();
    await expect(groups(page)).toHaveCount(7);

    // Fold one client, then reload: grouping and fold both stay.
    await header(page, "Meera Nair").click();
    await page.waitForTimeout(450);
    if (SHOTS) {
      await page.locator("[data-page-scroll]").evaluate((el) => el.scrollTo(0, 260));
      await page.waitForTimeout(700);
      await page.screenshot({ path: `${SHOTS}/phone-grouped-client-collapsed.png` });
    }
    await page.reload();
    await expect(groups(page)).toHaveCount(7);
    await expect(page.getByRole("button", { name: /Grouped by client/ })).toBeVisible();
    await expect(header(page, "Meera Nair")).toHaveAttribute("aria-expanded", "false");
    await expect(header(page, "Rao & Sons Builders")).toHaveAttribute("aria-expanded", "true");

    // The chip reopens the sheet; None puts the plain list back.
    await page.getByRole("button", { name: /Grouped by client/ }).click();
    await page.getByRole("dialog", { name: "View options" }).getByRole("radio", { name: /None/ }).click();
    await expect(page).not.toHaveURL(/group=/);
    await expect(groups(page)).toHaveCount(0);
    await expect(page.getByText("Needs Attention This Week")).toBeVisible();
  });

  test("a group header stays pinned under the top bar while its cards scroll, and follows the bar", async ({ page }) => {
    await open(page, PHONE, "/cases?group=court");
    await expect(groups(page)).toHaveCount(5);
    await page.waitForTimeout(900);
    const scroller = page.locator("[data-page-scroll]");
    const top = async () => (await header(page, HC).boundingBox())!.y;

    // Read down: the top bar slides away, the tabs (44px) stay, the header sits just under them.
    await scroller.evaluate((el) => el.scrollTo(0, 200));
    await page.waitForTimeout(100);
    await scroller.evaluate((el) => el.scrollTo(0, 520));
    await page.waitForTimeout(800);
    await expect(page.locator("html")).toHaveAttribute("data-chrome", "hidden");
    expect(Math.abs((await top()) - 44)).toBeLessThanOrEqual(2);

    // A little way back up: the bar returns and pushes the header down with it.
    await scroller.evaluate((el) => el.scrollTo(0, 440));
    await page.waitForTimeout(800);
    await expect(page.locator("html")).toHaveAttribute("data-chrome", "shown");
    expect(Math.abs((await top()) - 96)).toBeLessThanOrEqual(2);
  });

  test("prefers-reduced-motion switches the group animations off", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: PHONE });
    const page = await context.newPage();
    await mockMobileApi(page, { "/cases/": cases });
    await page.goto("/cases?group=court");
    await expect(groups(page)).toHaveCount(5);
    const names = await page.evaluate(() =>
      Array.from(document.querySelectorAll<HTMLElement>("*"))
        .map((el) => getComputedStyle(el))
        .filter((cs) => cs.animationName !== "none" && !cs.animationName.startsWith("ci-shimmer"))
        .map((cs) => cs.animationName),
    );
    expect(names).toEqual([]);
    // Folding is instant: no height transition is left running.
    await header(page, HC).click();
    await expect(page.getByRole("link", { name: /Open case Butham Srinivas vs. State/ })).toBeHidden({ timeout: 1000 });
    await context.close();
  });
});
