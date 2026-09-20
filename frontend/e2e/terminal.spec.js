import { expect, test } from "@playwright/test";

test("overview supports deep navigation and overlay filters", async ({ page }) => {
  await page.goto("/terminal/?symbol=SPY&bucket=ALL");
  await expect(page.locator(".chart-canvas")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".chart-level-overlay").first()).toBeVisible();
  await expect(page.locator(".chart-tile")).toHaveCount(9, { timeout: 30_000 });
  const currentPriceLayer = page.getByRole("button", { name: "Current price" });
  await expect(currentPriceLayer).toHaveAttribute("aria-pressed", "true");
  await currentPriceLayer.click();
  await expect(currentPriceLayer).toHaveAttribute("aria-pressed", "false");
  await currentPriceLayer.click();
  await expect(currentPriceLayer).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Price", exact: true }).click();
  await expect(page.getByRole("button", { name: "Price", exact: true })).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("button", { name: "Price", exact: true }).click();
  await expect(page.getByRole("button", { name: "Price", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);

  await page.getByRole("button", { name: "Market Map" }).click();
  await expect(page.locator(".module-header h2")).toHaveText("Structure around spot");
  await expect(page).toHaveURL(/\/terminal\/map\?symbol=SPY&bucket=ALL/);
  await page.getByRole("button", { name: "Controls" }).click();
  await expect(page.getByLabel("Heatmap metric")).toBeVisible();
  await page.getByRole("button", { name: "Controls" }).click();

  await page.goBack();
  await expect(page.locator(".overview-page")).toBeVisible();
  await page.getByRole("button", { name: /Show controls/ }).click();
  await page.getByLabel("Heatmap metric").selectOption("oi");
  await expect(page).toHaveURL(/metric=oi/);
  await page.getByRole("button", { name: "Calls" }).click();
  await expect(page).toHaveURL(/flow=CALLS/);
  await expect(page.getByRole("button", { name: "Calls" })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "GEX & Gamma" }).click();
  await expect(page.locator(".chart-tile")).toHaveCount(4, { timeout: 30_000 });
  await expect(page.locator('[data-chart-id="expiry-exposure-map"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".expiry-map-cell").first()).toBeVisible();
  await page.getByLabel("Metric", { exact: true }).selectOption("oi");
  await expect(page).toHaveURL(/expiry_metric=oi/);
  await expect(page.getByLabel("Profile expiry")).toBeVisible();
  await page.getByLabel("Profile expiry").selectOption("0DTE");
  await page.getByRole("button", { name: "Absolute" }).click();
  await expect(page).toHaveURL(/profile_exp=0DTE/);
  await expect(page).toHaveURL(/profile_mode=ABSOLUTE/);

  await page.getByRole("button", { name: "Options Flow" }).click();
  await expect(page.locator(".chart-tile")).toHaveCount(3, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Net" })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("region", { name: "Flow chart controls" }).getByRole("button", { name: "Calls" }).click();
  await expect(page).toHaveURL(/series=puts/);
});

test("overview remains usable on mobile without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/terminal/?symbol=SPY&bucket=ALL");
  await expect(page.locator(".chart-canvas")).toBeVisible({ timeout: 30_000 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(page.locator(".terminal-sidebar")).toHaveClass(/is-mobile-open/);
});

test("direct terminal URL, language and real candle controls stay in the workspace", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await page.goto("/terminal?symbol=SPY&bucket=0DTE");
  await expect(page).toHaveURL(/\/terminal\/\?symbol=SPY&bucket=0DTE/);
  await expect(page.locator(".chart-canvas")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".chart-footer")).toContainText("5/5 real sessions", { timeout: 30_000 });
  await page.getByRole("button", { name: "ES", exact: true }).click();
  await expect(page).toHaveURL(/lang=es/);
  await expect(page.getByRole("button", { name: "Resumen", exact: true })).toBeVisible();
  await page.getByRole("button", { name: /Mostrar controles/ }).click();
  await page.getByLabel("Intervalo de velas").selectOption("15m");
  await page.getByLabel("Historico de precio").selectOption("3");
  await expect(page).toHaveURL(/interval=15m/);
  await expect(page).toHaveURL(/sessions=3/);
  await expect(page.locator(".chart-footer")).toContainText("3/3 sesiones reales", { timeout: 30_000 });
  await page.getByRole("button", { name: "Heatmaps", exact: true }).click();
  await expect(page.locator('[data-chart-id="options-exposure-heatmap"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".exposure-cell").first()).toBeVisible();
  await expect(page.locator('[data-chart-id="liquidity-heatmap"]')).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("canonicalizes duplicated terminal base paths", async ({ page }) => {
  await page.goto("/terminal/terminal?symbol=SPY&bucket=0DTE");
  await expect(page).toHaveURL(/\/terminal\/\?symbol=SPY&bucket=0DTE/);
  await expect(page.locator(".overview-page")).toBeVisible({ timeout: 30_000 });
  await page.goto("/terminal/terminal/map?symbol=SPY&bucket=0DTE");
  await expect(page).toHaveURL(/\/terminal\/map\?symbol=SPY&bucket=0DTE/);
  await expect(page.locator(".module-page")).toBeVisible({ timeout: 30_000 });
});

test("market report is readable in English and Spanish", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/terminal/report?symbol=SPY&bucket=ALL&lang=en");
  await expect(page.locator(".report-pro")).toContainText("NEGATIVE GAMMA", { timeout: 45_000 });
  await expect(page.locator(".report-pro")).toContainText("PUT HEAVY");
  await page.getByRole("button", { name: "ES", exact: true }).click();
  await expect(page).toHaveURL(/lang=es/);
  await expect(page.locator(".report-pro")).toContainText("GAMMA NEGATIVA", { timeout: 45_000 });
  await expect(page.locator(".report-pro")).toContainText("PREDOMINIO PUT");
});

test("chart figures localize their presentation text in Spanish", async ({ page }) => {
  await page.goto("/terminal/map?symbol=SPY&bucket=ALL&lang=es");
  await expect(page.locator(".chart-tile").first()).toContainText("Exposicion gamma", { timeout: 45_000 });
  await expect(page.locator(".chart-tile").first()).not.toContainText("Gamma exposure");
  await expect(page.locator(".chart-tile").nth(1)).toContainText("Fuerza deterministica");
  await expect(page.locator(".chart-tile").first().locator(".annotation-text")).toHaveCount(4);
});

test("all migrated modules keep a healthy deep link", async ({ page }) => {
  test.setTimeout(120_000);
  const routes = ["overview", "map", "heat", "profile", "chain", "levels", "scenarios", "positioning", "flow", "volatility", "report", "history", "session", "settings", "diagnostics"];
  const consoleErrors = [];
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  for (const route of routes) {
    const href = route === "overview" ? "/terminal/?symbol=SPY&bucket=ALL&lang=es" : `/terminal/${route}?symbol=SPY&bucket=ALL&lang=es`;
    await page.goto(href);
    await expect(page.locator(".overview-page,.module-page").first()).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".state-panel--error")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    expect(page.url()).toContain(`/terminal/${route === "overview" ? "" : route}`);
  }
  expect(consoleErrors).toEqual([]);
});
