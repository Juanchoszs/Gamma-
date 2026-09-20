import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45_000,
  outputDir: "/tmp/gamma-playwright-results",
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:5174",
    trace: "off",
  },
});
