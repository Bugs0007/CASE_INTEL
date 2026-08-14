import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    // Only our own specs -- without this, vitest walks node_modules and
    // tries to run vendored test files.
    include: ["**/__tests__/**/*.test.{ts,tsx}"],
  },
  resolve: {
    // Mirrors the "@/*" path alias in tsconfig.json; vitest doesn't read
    // tsconfig paths on its own.
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
