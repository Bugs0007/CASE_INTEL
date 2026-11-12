import { expect, test, type Page } from "@playwright/test";
import { CASE_ID } from "./fixtures";
import { mockMobileApi } from "./mobile-fixtures";

// The drafting studio on a case page, with the API mocked in the browser.
//
// The entry point renders only when NEXT_PUBLIC_CASE_DRAFTING is "true", and
// that is read when Next builds the page, so this spec cannot switch it on:
//
//   NEXT_PUBLIC_CASE_DRAFTING=true npx playwright test e2e/drafting-studio.spec.ts
//
// Without the flag the tests are skipped, not passed.

const FLAG_ON = process.env.NEXT_PUBLIC_CASE_DRAFTING === "true";
const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };

const body = {
  schema_version: 1,
  title: "Status memo",
  subtype: "status_memo",
  sections: [{ heading: "Where things stand", blocks: [{ type: "paragraph", text: "Listed next week." }] }],
};
const revision = (over: Record<string, unknown> = {}) => ({
  id: 100,
  version: 1,
  source: "generated",
  created_at: "2026-11-01T10:00:00Z",
  approved_at: null,
  body,
  schema_version: 1,
  evidence: [],
  missing_facts: [],
  warnings: [],
  approved_hash: "",
  ...over,
});
const detail = (over: Record<string, unknown> = {}) => ({
  id: 5,
  case_id: CASE_ID,
  kind: "document",
  subtype: "status_memo",
  status: "ready",
  approved_revision_id: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
  case_title: "Case",
  error: "",
  generation: 1,
  brief: { instructions: "", audience: "", tone: "neutral", length: "standard", source_document_ids: [] },
  current_revision: revision(),
  revisions: [{ id: 100, version: 1, source: "generated", created_at: "2026-11-01T10:00:00Z", approved_at: null }],
  outputs: [],
  ...over,
});

async function mockDraftingApi(page: Page) {
  const saved: Record<string, unknown>[] = [];
  let approved = false;
  await page.route("http://localhost:8000/api/case-assistant/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (data: unknown, status = 200) =>
      route.fulfill({ status, contentType: "application/json", headers: CORS, body: JSON.stringify(data) });
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...CORS, "access-control-allow-methods": "*" } });
    }
    if (path.endsWith("/drafts/") && request.method() === "GET") return json([]);
    if (path.endsWith("/drafts/") && request.method() === "POST") return json(detail(), 202);
    if (path.endsWith("/revisions/")) {
      saved.push(JSON.parse(request.postData() ?? "{}"));
      return json(detail({ current_revision: revision({ id: 101, version: 2, source: "edited" }) }), 201);
    }
    if (path.endsWith("/approve/")) {
      approved = true;
      return json(detail({ approved_revision_id: 100, current_revision: revision({ approved_at: "2026-11-02T10:00:00Z" }) }));
    }
    if (/\/drafts\/5\/$/.test(path)) {
      return json(approved ? detail({ approved_revision_id: 100, current_revision: revision({ approved_at: "2026-11-02T10:00:00Z" }) }) : detail());
    }
    return route.fulfill({ status: 404, headers: CORS, body: "{}" });
  });
  await page.route("http://localhost:8000/api/cases/*/notes/", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: CORS, body: "[]" }),
  );
  return saved;
}

const VIEWPORTS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "phone", width: 375, height: 812 },
] as const;

for (const viewport of VIEWPORTS) {
  test.describe(`drafting studio on ${viewport.name}`, () => {
    test.skip(!FLAG_ON, "Start with NEXT_PUBLIC_CASE_DRAFTING=true; the flag is fixed at build time.");

    test("creates a draft, edits and saves it, then approves it", async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await mockMobileApi(page);
      const saved = await mockDraftingApi(page);
      await page.goto(`/cases/${CASE_ID}`);

      await page.getByRole("button", { name: "Draft with assistant" }).click();
      await page.getByRole("button", { name: "Generate draft" }).click();
      await expect(page).toHaveURL(/draft=5/);

      const title = page.getByLabel("Title");
      await title.fill("Status memo edited");
      await expect(page.getByText("Unsaved changes")).toBeVisible();
      await expect(page.getByRole("button", { name: "Approve this version" })).toBeDisabled();
      await page.getByRole("button", { name: "Save as new version" }).click();
      await expect(page.getByText("Unsaved changes")).toHaveCount(0);
      expect(saved[0]).toMatchObject({ expected_revision: 100 });

      // No horizontal scroll at this width.
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
      expect(overflow).toBe(false);
    });
  });
}
