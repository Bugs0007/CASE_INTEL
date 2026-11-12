import { expect, test, type Page } from "@playwright/test";
import { mockMobileApi } from "./mobile-fixtures";

// The dashboard's practice block (compact week calendar, case summary and the
// read-only assistant) on a desktop and a phone viewport, with the API mocked
// in the browser.
//
// The block renders only when NEXT_PUBLIC_PORTFOLIO_BOT is "true", and that is
// read when Next builds the page, so this spec cannot switch it on itself.
// Run it with the flag set for the dev server Playwright starts (stop any dev
// server already on :3100 first, because it would be reused without the flag):
//
//   NEXT_PUBLIC_PORTFOLIO_BOT=true npx playwright test e2e/practice-assistant.spec.ts
//
// Without the flag the tests are skipped, not passed.

const FLAG_ON = process.env.NEXT_PUBLIC_PORTFOLIO_BOT === "true";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };

function todayKey(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
}

const ref = (kind: string, id: number, label: string) => ({ kind, id, case_id: 7, label, recorded_at: null });

async function mockPracticeApi(page: Page) {
  const chats: Record<string, unknown>[] = [];
  await page.route("http://localhost:8000/api/practice-assistant/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (data: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: JSON.stringify(data) });
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...CORS, "access-control-allow-methods": "*" } });
    }
    if (url.pathname.endsWith("/overview/")) {
      const day = todayKey();
      return json({
        calendar: {
          date_from: url.searchParams.get("from"),
          date_to: url.searchParams.get("to"),
          entries: [
            {
              kind: "hearing",
              id: 1,
              case_id: 7,
              case_title: "Rao vs State",
              day,
              start_time: null,
              end_time: null,
              status: "scheduled",
              label: "Hearing: for admission",
              provenance: "court portal",
              needs_review: false,
              ref: ref("hearing", 1, "Hearing: for admission"),
            },
          ],
          day_markers: { [day]: { hearing: 1, task: 0, event: 0 } },
          total: 1,
          truncated: false,
          as_of: new Date().toISOString(),
          timezone: "Asia/Kolkata",
        },
        portfolio: {
          status_counts: { open: 2 },
          total_cases: 2,
          active_cases: 2,
          active_with_next_hearing: 1,
          active_without_next_date: 1,
          cases: [
            { id: 7, title: "Rao vs State", case_number: "WP/1/2026", court: "Telangana High Court", status: "open", next_hearing_at: null },
          ],
          page: 1,
          page_size: 8,
          total: 2,
          as_of: new Date().toISOString(),
          timezone: "Asia/Kolkata",
        },
      });
    }
    if (url.pathname.endsWith("/chat/")) {
      chats.push(JSON.parse(request.postData() ?? "{}"));
      return json({
        conversation_id: 1,
        user_message_id: 10,
        assistant_message_id: 11,
        answer: "You have one hearing today, in Rao vs State.",
        intent: "calendar",
        status: "answer",
        sources: [ref("case", 7, "Rao vs State")],
        summary: null,
        case_candidates: [],
        action_card: null,
        as_of: new Date().toISOString(),
      });
    }
    return route.fulfill({ status: 404, headers: CORS, body: "{}" });
  });
  return chats;
}

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "phone", width: 390, height: 844 },
] as const;

for (const viewport of VIEWPORTS) {
  test.describe(`practice assistant on ${viewport.name}`, () => {
    test.skip(!FLAG_ON, "Start with NEXT_PUBLIC_PORTFOLIO_BOT=true; the flag is fixed at build time.");

    test("shows the section, asks about a day, and answers with a source link", async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await mockMobileApi(page);
      const chats = await mockPracticeApi(page);
      await page.goto("/dashboard");

      const section = page.getByRole("region", { name: "Your practice" });
      // On a phone the Briefing tab shows it below the other sections.
      await section.scrollIntoViewIfNeeded();
      await expect(section).toBeVisible();
      await expect(section.getByRole("heading", { name: "This week" })).toBeVisible();

      // Select today and read its agenda.
      await section.getByRole("button", { name: /today/ }).click();
      await expect(section.getByRole("link", { name: /Hearing: for admission/ })).toBeVisible();

      // "Ask about this day" fills the input and sends nothing.
      await section.getByRole("button", { name: "Ask about this day" }).click();
      const input = section.getByLabel("Your question");
      await expect(input).toHaveValue(/^What is on .+\?$/);
      expect(chats).toHaveLength(0);

      await section.getByRole("button", { name: "Send" }).click();
      await expect(section.getByText("You have one hearing today, in Rao vs State.")).toBeVisible();
      expect(chats).toHaveLength(1);
      expect(chats[0]).toMatchObject({ selected_day: todayKey() });
      expect(typeof chats[0].client_request_id).toBe("string");

      // The source chip links to the case.
      const chip = section.getByRole("list", { name: "Sources" }).getByRole("link", { name: "Rao vs State" });
      await expect(chip).toHaveAttribute("href", "/cases/7");
    });
  });
}
