import { defineConfig } from "@playwright/test";

// The e2e specs mock the API in the browser (page.route), so they need no
// backend: only the Next dev server. They drive the Chrome already on the
// machine (channel: "chrome"), so no browser is downloaded.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: "http://localhost:3100",
    channel: "chrome",
    headless: true,
  },
  webServer: {
    command: "npx next dev -p 3100",
    url: "http://localhost:3100/login",
    // .env.local points the app at a local backend; the specs mock the API
    // at this address instead, whatever that file says.
    env: { NEXT_PUBLIC_API_URL: "http://localhost:8000/api" },
    reuseExistingServer: true,
    timeout: 180_000,
  },
});
