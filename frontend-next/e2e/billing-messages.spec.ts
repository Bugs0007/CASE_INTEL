import { expect, test, type Page } from "@playwright/test";
import { mockMobileApi } from "./mobile-fixtures";
import { messageDrafts, mockFeeApi, sentMessages } from "./billing-fixtures";

// The Billing and Messages pages on a phone (390x844) and a desktop (1440x900):
// the way from an invoiced charge to paid, what each state offers, and that
// nothing scrolls sideways. The API is mocked in the browser (see
// billing-fixtures.ts); no backend is needed.
//
// Set SHOTS_DIR to also save a screenshot of each screen.

const SHOTS = process.env.SHOTS_DIR;
const PHONE = { width: 390, height: 844 };
const DESKTOP = { width: 1440, height: 900 };

async function openBilling(page: Page, viewport: { width: number; height: number }) {
  await page.setViewportSize(viewport);
  await mockMobileApi(page);
  const log = await mockFeeApi(page);
  await page.goto("/billing");
  await expect(page.getByRole("heading", { name: "Outstanding by client" })).toBeVisible();
  await expect(page.getByTestId("fee-group").first()).toBeVisible();
  return log;
}

async function openMessages(page: Page, viewport: { width: number; height: number }, query = "") {
  await page.setViewportSize(viewport);
  await mockMobileApi(page, { "/client-messages/": messageDrafts, "/sent-messages/": sentMessages });
  await page.goto(`/messages${query}`);
}

/** Anything sticking out to the right of the viewport. */
async function overflow(page: Page) {
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
    return {
      doc: document.documentElement.scrollWidth - vw,
      body: document.body.scrollWidth - vw,
      offenders,
    };
  });
}

async function expectNoSidewaysScroll(page: Page) {
  const o = await overflow(page);
  expect(o.doc).toBeLessThanOrEqual(0);
  expect(o.body).toBeLessThanOrEqual(0);
  expect(o.offenders).toEqual([]);
}

test.describe("Billing on a phone (390x844)", () => {
  test("an invoiced charge goes to paid through a confirmation, and shows paid", async ({ page }) => {
    const log = await openBilling(page, PHONE);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/billing-phone-list.png` });

    const row = page.getByTestId("fee-row").filter({ hasText: "INV-0007" });
    await expect(row).toContainText("Awaiting payment");
    await row.getByRole("button", { name: "Mark INV-0007 paid" }).click();

    // Nothing is paid until the confirmation is answered.
    const sheet = page.getByRole("dialog", { name: "Mark as paid" });
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText("Meera Nair");
    await expect(sheet).toContainText("CC/312/2026");
    await expect(sheet).toContainText("INV-0007");
    await expect(sheet).toContainText("₹15,000");
    await expect(sheet).toContainText("can't be undone");
    expect(log.calls).toEqual([]);
    await page.waitForTimeout(500); // the sheet has risen
    await expectNoSidewaysScroll(page);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/billing-phone-confirm.png` });

    const confirm = sheet.getByRole("button", { name: "Mark paid · ₹15,000" });
    expect((await confirm.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await confirm.click();

    await expect(sheet).toBeHidden();
    expect(log.calls).toEqual(["POST mark-paid 1"]);
    await expect(page.getByTestId("fee-row").filter({ hasText: "INV-0007" })).toHaveCount(0);

    // It is in the Paid list, as paid, with nothing left to press.
    await page.getByRole("tab", { name: /^Paid/ }).click();
    await page.waitForTimeout(700); // the list has changed and risen in
    const paid = page.getByTestId("fee-row").filter({ hasText: "INV-0007" });
    await expect(paid).toHaveAttribute("data-status", "paid");
    await expect(paid).toContainText("Paid");
    await expect(paid.getByRole("button", { name: /Mark/ })).toHaveCount(0);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/billing-phone-paid.png` });
  });

  test("a charge that is not invoiced yet offers Generate invoice, never Mark paid", async ({ page }) => {
    const log = await openBilling(page, PHONE);
    const pending = page.getByTestId("fee-row").filter({ hasText: "no invoice yet" });
    await expect(pending).toHaveCount(1);
    await expect(pending.getByRole("button", { name: /^Generate invoice/ })).toBeVisible();
    await expect(pending.getByRole("button", { name: /Mark/ })).toHaveCount(0);

    await pending.getByRole("button", { name: /^Generate invoice/ }).click();
    await expect(page.getByTestId("fee-row").filter({ hasText: "INV-0009" })).toBeVisible();
    expect(log.calls).toEqual(["POST invoice 2"]);
    // The next step is now Mark paid.
    await expect(page.getByRole("button", { name: "Mark INV-0009 paid" })).toBeVisible();
  });

  test("the unpaid clients are listed longest-unpaid first with a total, and every button is a 44px target", async ({ page }) => {
    await openBilling(page, PHONE);
    await expect(page.getByTestId("billing-hero")).toContainText("₹30,000");
    await expect(page.getByTestId("billing-hero")).toContainText("1 overdue");
    const titles = await page.getByTestId("fee-group").evaluateAll((els) => els.map((el) => el.getAttribute("aria-label")));
    expect(titles).toEqual(["Rao & Sons Builders", "Meera Nair"]);

    const buttons = page.getByTestId("fee-group").getByRole("button");
    const count = await buttons.count();
    expect(count).toBeGreaterThan(4);
    for (let i = 0; i < count; i++) {
      const box = await buttons.nth(i).boundingBox();
      expect(box!.height, `button ${i}`).toBeGreaterThanOrEqual(43.5);
    }
  });

  test("the filter tabs stay pinned under the top bar while the list scrolls", async ({ page }) => {
    await openBilling(page, PHONE);
    const tabs = page.getByRole("tablist", { name: "Show charges" });
    await expect(tabs).toBeVisible();
    await page.locator("[data-page-scroll]").evaluate((el) => el.scrollTo(0, 500));
    await page.waitForTimeout(500);
    await expect(tabs).toBeInViewport();
    expect((await tabs.boundingBox())!.y).toBeLessThan(60);
    await tabs.getByRole("tab", { name: /^Awaiting/ }).click();
    await expect(page.getByRole("heading", { name: "Awaiting payment, by client" })).toBeVisible();
    for (const row of await page.getByTestId("fee-row").all()) await expect(row).toHaveAttribute("data-status", "invoiced");
  });

  test("nothing scrolls sideways, with the list, the paid view and a search with no matches", async ({ page }) => {
    await openBilling(page, PHONE);
    await page.waitForTimeout(700);
    await expectNoSidewaysScroll(page);
    await page.getByRole("tab", { name: /^Paid/ }).click();
    await page.waitForTimeout(500);
    await expectNoSidewaysScroll(page);
    await page.getByRole("tab", { name: /^Unpaid/ }).click();
    await page.getByLabel("Search charges").fill("zzzz");
    await expect(page.getByText(/No charges match/)).toBeVisible();
    await expectNoSidewaysScroll(page);
  });

  test("Mark all paid lists the invoices and their total before it does anything", async ({ page }) => {
    const log = await openBilling(page, PHONE);
    await page.getByRole("button", { name: "Mark all 2 paid" }).click();
    const sheet = page.getByRole("dialog", { name: "Mark invoices as paid" });
    await expect(sheet).toContainText("INV-0003");
    await expect(sheet).toContainText("INV-0005");
    await expect(sheet).toContainText("₹12,000");
    await page.waitForTimeout(500);
    await expectNoSidewaysScroll(page);
    expect(log.calls).toEqual([]);
    await sheet.getByRole("button", { name: "Cancel" }).click();
    await expect(sheet).toBeHidden();
    expect(log.calls).toEqual([]);
  });
});

test.describe("Billing on a desktop (1440x900)", () => {
  test("the totals are tiles that filter the list, and Mark paid asks first in a centred dialog", async ({ page }) => {
    const log = await openBilling(page, DESKTOP);
    await expect(page.getByRole("button", { name: /^Outstanding/ })).toContainText("₹30,000");
    await expect(page.getByRole("button", { name: /^Awaiting payment/ })).toContainText("1 overdue");
    await expectNoSidewaysScroll(page);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/billing-desktop-list.png` });

    await page.getByRole("button", { name: /^To invoice/ }).click();
    await expect(page.getByRole("heading", { name: "To invoice, by client" })).toBeVisible();
    await expect(page.getByRole("button", { name: /^To invoice/ })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("button", { name: /^Awaiting payment/ }).click();

    await page.getByRole("button", { name: "Mark INV-0007 paid" }).click();
    const dialog = page.getByRole("dialog", { name: "Mark as paid" });
    await expect(dialog).toBeVisible();
    await page.waitForTimeout(500);
    const box = (await dialog.boundingBox())!;
    // A dialog in the middle of the screen, not a sheet on its bottom edge.
    expect(box.y + box.height).toBeLessThan(DESKTOP.height - 20);
    expect(Math.abs(box.x + box.width / 2 - DESKTOP.width / 2)).toBeLessThan(40);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/billing-desktop-confirm.png` });
    expect(log.calls).toEqual([]);

    await dialog.getByRole("button", { name: "Mark paid · ₹15,000" }).click();
    await expect(dialog).toBeHidden();
    expect(log.calls).toEqual(["POST mark-paid 1"]);
    await expect(page.getByRole("button", { name: /^Paid this month/ })).toContainText("₹21,000");
  });

  test("a search narrows the list by client, case or invoice number", async ({ page }) => {
    await openBilling(page, DESKTOP);
    await page.getByLabel("Search charges").fill("INV-0005");
    await expect(page.getByTestId("fee-group")).toHaveCount(1);
    await expect(page.getByTestId("fee-group")).toHaveAttribute("aria-label", "Rao & Sons Builders");
  });
});

test.describe("Messages on a phone (390x844)", () => {
  test("drafts are scannable rows under tabs pinned to the top, and open in place", async ({ page }) => {
    await openMessages(page, PHONE);
    const list = page.getByTestId("draft-list");
    await expect(list).toBeVisible();
    const rows = list.getByRole("button", { expanded: false });
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText("Update on your matter");
    await expect(rows.first()).toContainText("To Meera Nair");
    await expect(rows.first()).toContainText("Your matter was heard today");
    await expect(rows.first()).toContainText("2 days ago");
    await expect(rows.nth(1)).toContainText("Payment reminder");
    await expect(rows.nth(2)).toContainText("No email contact");
    await page.waitForTimeout(700);
    await expectNoSidewaysScroll(page);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/messages-phone-list.png` });

    // The tabs are pinned; a draft opens to its editor.
    const tabs = page.getByRole("tablist", { name: "Messages" });
    await expect(tabs).toBeVisible();
    expect((await tabs.boundingBox())!.y).toBeLessThan(60);
    await rows.first().click();
    await expect(page.getByLabel("Subject")).toHaveValue("Update on your matter");
    await expect(page.getByRole("button", { name: /^send$/i })).toBeVisible();
    await expectNoSidewaysScroll(page);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/messages-phone-open.png` });
  });

  test("the kind chips count and filter, and the sent log separates emailed from logged", async ({ page }) => {
    await openMessages(page, PHONE);
    const chips = page.getByRole("group", { name: "Filter drafts" });
    await expect(chips.getByRole("button", { name: "Payment reminders 1" })).toBeVisible();
    await chips.getByRole("button", { name: "Payment reminders 1" }).click();
    await expect(page.getByTestId("draft-list").getByRole("button", { expanded: false })).toHaveCount(1);

    await page.getByRole("tab", { name: /Sent log/ }).click();
    await expect(page).toHaveURL(/tab=sent/);
    const sent = page.getByRole("group", { name: "Filter sent messages" });
    await sent.getByRole("button", { name: "Logged, not emailed 1" }).click();
    await expect(page.getByTestId("sent-log-list").getByRole("listitem")).toHaveCount(1);
    await expect(page.getByTestId("sent-log-list")).toContainText("Invoice INV-0003");
    await expectNoSidewaysScroll(page);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/messages-phone-sent.png` });
  });
});

test.describe("Messages on a desktop (1440x900)", () => {
  test("renders the drafts with counts, and the sent log as a table", async ({ page }) => {
    await openMessages(page, DESKTOP);
    await expect(page.getByTestId("draft-list").getByRole("button", { expanded: false })).toHaveCount(3);
    await expect(page.getByRole("tab", { name: /Drafts \(3\)/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Case updates 2" })).toBeVisible();
    await expectNoSidewaysScroll(page);
    await page.waitForTimeout(700); // the rows have risen in
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/messages-desktop-list.png` });

    await page.getByRole("tab", { name: /Sent log/ }).click();
    await expect(page.locator("table")).toBeVisible();
    await expect(page.locator("table").getByText("Invoice INV-0003")).toBeVisible();
  });
});
