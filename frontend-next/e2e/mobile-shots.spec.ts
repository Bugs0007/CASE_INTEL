import { test } from "@playwright/test";
import { mockMobileApi } from "./mobile-fixtures";

// Screenshot harness, not an assertion suite (those are in mobile.spec.ts):
// set SHOTS_DIR (and optionally SHOT_W / SHOT_H) to capture the main screens.
const DIR = process.env.SHOTS_DIR;
const WIDTH = Number(process.env.SHOT_W ?? 390);
const HEIGHT = Number(process.env.SHOT_H ?? 844);
const SCREENS: [string, string][] = [
  ["dashboard", "/dashboard"],
  ["cases", "/cases"],
  ["case", "/cases/1"],
  ["calendar", "/calendar"],
  ["billing", "/billing"],
  ["documents", "/documents"],
  ["messages", "/messages"],
];

test.skip(!DIR, "set SHOTS_DIR to take screenshots");

for (const [name, url] of SCREENS) {
  test(`shot ${name}`, async ({ page }) => {
    await page.setViewportSize({ width: WIDTH, height: HEIGHT });
    await mockMobileApi(page);
    await page.goto(url);
    await page.waitForTimeout(1800);
    await page.screenshot({ path: `${DIR}/${name}-${WIDTH}.png` });
  });
}

test("shot case tabs and sheets", async ({ page }) => {
  await page.setViewportSize({ width: WIDTH, height: HEIGHT });
  await mockMobileApi(page);
  await page.goto("/cases/1");
  await page.waitForTimeout(1500);
  for (const tab of ["Hearings", "Documents", "Fees & more"]) {
    await page.getByRole("tab", { name: tab }).click();
    await page.waitForTimeout(700);
    await page.screenshot({ path: `${DIR}/case-tab-${tab.split(" ")[0].toLowerCase()}-${WIDTH}.png` });
  }
  await page.getByRole("tab", { name: "Hearings" }).click();
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: /Open details/ }).first().click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${DIR}/case-hearing-sheet-${WIDTH}.png` });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(500);
  await page.getByRole("button", { name: "Ask the Case Bot" }).click();
  await page.waitForTimeout(900);
  await page.screenshot({ path: `${DIR}/case-bot-${WIDTH}.png` });
});

test("shot calendar modes and dialogs", async ({ page }) => {
  await page.setViewportSize({ width: WIDTH, height: HEIGHT });
  await mockMobileApi(page);
  await page.goto("/calendar");
  await page.waitForTimeout(1500);
  await page.getByRole("tab", { name: "Month" }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${DIR}/calendar-month-${WIDTH}.png` });
  await page.getByRole("tab", { name: "By court" }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${DIR}/calendar-court-${WIDTH}.png` });
  await page.goto("/cases");
  await page.waitForTimeout(1200);
  await page.getByRole("button", { name: "Case options" }).first().click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${DIR}/cases-sheet-${WIDTH}.png` });
});
