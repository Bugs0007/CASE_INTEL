import { expect, test } from "@playwright/test";
import { CASE_ID, caseDetail, mockApi } from "./fixtures";

// The case page is one screen at 1280x760 and up: nothing scrolls, and the
// header, facts strip and rail have the sizes the design gives them.

const SIZES = [
  { width: 1920, height: 960 },
  { width: 1536, height: 864 },
  { width: 1280, height: 760 },
] as const;

for (const { width, height } of SIZES) {
  test(`the case page does not scroll at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await mockApi(page);
    await page.goto(`/cases/${CASE_ID}`);
    await expect(page.getByRole("heading", { name: /Butham Srinivas/ })).toBeVisible();
    await expect(page.getByRole("region", { name: "Hearings & orders" })).toBeVisible();
    await page.waitForTimeout(600);

    const heights = await page.evaluate(() => {
      const root = document.scrollingElement as HTMLElement;
      // The app scrolls an inner container, not the document: find every
      // element that could scroll and report the worst overflow.
      const overflowing = Array.from(document.querySelectorAll<HTMLElement>("body *")).filter(
        (el) =>
          el.scrollHeight > el.clientHeight + 1 &&
          ["auto", "scroll"].includes(getComputedStyle(el).overflowY) &&
          el.clientHeight > 0,
      );
      return {
        document: root.scrollHeight,
        inner: window.innerHeight,
        scrollers: overflowing.map((el) => `${el.tagName}.${el.className.toString().slice(0, 40)} ${el.scrollHeight}>${el.clientHeight}`),
      };
    });
    console.log(`${width}x${height}: scrollHeight ${heights.document} / innerHeight ${heights.inner}`);
    expect(heights.document).toBeLessThanOrEqual(heights.inner);
    expect(heights.scrollers).toEqual([]);
  });
}

// The order-check line sits at the foot of the Documents and Hearings & orders
// cards. Both are clipped (overflow hidden), so "the page does not scroll" is
// not enough: the line, and the Retry button on a failed check, must be seen.
const FAILED_CHECK = {
  ...caseDetail,
  order_sync: { state: "failed", last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: "court portal didn't answer" },
};

for (const { name, overrides, text } of [
  { name: "ok", overrides: {}, text: /Checked .*2 orders\./ },
  { name: "failed", overrides: { [`/cases/${CASE_ID}/`]: FAILED_CHECK }, text: /Last check failed \(court portal didn't answer\)/ },
]) {
  for (const { width, height } of SIZES) {
    test(`the ${name} order-check line is fully visible in both cards at ${width}x${height}`, async ({ page }) => {
      await page.setViewportSize({ width, height });
      await mockApi(page, overrides);
      await page.goto(`/cases/${CASE_ID}`);
      await expect(page.getByRole("region", { name: "Hearings & orders" })).toBeVisible();
      await page.waitForTimeout(500);

      for (const card of ["Hearings & orders", "Documents"]) {
        const region = page.getByRole("region", { name: card });
        const line = region.getByTestId("order-sync-status");
        await expect(line).toContainText(text);
        const box = (await region.boundingBox())!;
        const lineBox = (await line.boundingBox())!;
        expect(lineBox.y).toBeGreaterThanOrEqual(box.y);
        expect(lineBox.y + lineBox.height).toBeLessThanOrEqual(box.y + box.height + 0.5);
        if (name === "failed") {
          const retry = region.getByRole("button", { name: "Retry order check" });
          await expect(retry).toBeVisible();
          const retryBox = (await retry.boundingBox())!;
          expect(retryBox.y + retryBox.height).toBeLessThanOrEqual(box.y + box.height + 0.5);
          expect(retryBox.x + retryBox.width).toBeLessThanOrEqual(box.x + box.width + 0.5);
        }
        // Rows are not squeezed out: the card still lists at least one.
        expect(await region.getByRole("listitem").count()).toBeGreaterThan(0);
      }
    });
  }
}

test("at 1920 wide the header is 56px, the facts strip 46px and the rail 352px", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 960 });
  await mockApi(page);
  await page.goto(`/cases/${CASE_ID}`);
  const header = page.getByRole("heading", { name: /Butham Srinivas/ }).locator("xpath=ancestor::div[contains(@class,'h-14')][1]");
  await expect(header).toBeVisible();
  expect((await header.boundingBox())?.height).toBe(56);

  const facts = page.locator("div.h-\\[46px\\]").first();
  expect((await facts.boundingBox())?.height).toBe(46);

  const rail = page.getByRole("complementary", { name: "Case side panel" });
  expect((await rail.boundingBox())?.width).toBe(352);
});

test("below 1024px wide the page is an ordinary scrolling page and nothing is trapped", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await mockApi(page);
  await page.goto(`/cases/${CASE_ID}`);
  await expect(page.getByRole("region", { name: "Hearings & orders" })).toBeVisible();
  await page.waitForTimeout(500);

  // One column: the rail's cards sit under the main column's, and the page scrolls.
  const scrolls = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("body *")).some(
      (el) => el.scrollHeight > el.clientHeight + 40 && ["auto", "scroll"].includes(getComputedStyle(el).overflowY),
    ),
  );
  expect(scrolls).toBe(true);
  const hearings = await page.getByRole("region", { name: "Hearings & orders" }).boundingBox();
  const next = await page.getByRole("region", { name: "Next hearing" }).boundingBox();
  expect(next!.y).toBeGreaterThan(hearings!.y);

  // The last card can be reached by scrolling.
  const last = page.getByRole("region", { name: "Client updates" });
  await last.scrollIntoViewIfNeeded();
  await expect(last).toBeInViewport();
});
