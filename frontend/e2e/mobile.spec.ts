import { expect, test } from "@playwright/test";

/**
 * Mobile conflicts — the things that actually break an app on a phone.
 *
 * Only the viewport and touch properties are overridden, not the whole `devices[...]`
 * descriptor: that carries `defaultBrowserType: "webkit"`, which Playwright refuses to
 * switch inside a describe block and which would silently pull in a second browser.
 */
test.use({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
});


test("no horizontal overflow on any route", async ({ page }) => {
  for (const path of ["/", "/verify", "/rules"]) {
    await page.goto(path);
    await page.locator("[data-splash]").waitFor({ state: "detached", timeout: 10_000 });
    const [scrollW, clientW] = await page.evaluate(() => [
      document.documentElement.scrollWidth,
      document.documentElement.clientWidth,
    ]);
    expect(scrollW, `${path} must not overflow`).toBeLessThanOrEqual(clientW + 1);
  }
});

test("inputs are 16px so iOS does not auto-zoom the viewport", async ({ page }) => {
  await page.goto("/verify");
  await page.locator("[data-splash]").waitFor({ state: "detached", timeout: 10_000 });
  const size = await page
    .locator("#payload")
    .evaluate((el) => parseFloat(getComputedStyle(el).fontSize));
  expect(size).toBeGreaterThanOrEqual(16);
});

test("primary actions meet the 44px touch target", async ({ page }) => {
  await page.goto("/verify");
  await page.locator("[data-splash]").waitFor({ state: "detached", timeout: 10_000 });
  const box = await page.getByRole("button", { name: /Run verification/ }).boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44);
});

test("the action table scrolls itself rather than the page", async ({ page }) => {
  await page.goto("/verify");
  await page.locator("[data-splash]").waitFor({ state: "detached", timeout: 10_000 });
  await page.getByRole("button", { name: /Planted violations/ }).click();
  await page.getByRole("button", { name: /Run verification/ }).click();
  await page.waitForURL(/\/reports\/rep_/, { timeout: 30_000 });

  const overflowX = await page
    .locator("table")
    .evaluate((t) => getComputedStyle(t.parentElement!).overflowX);
  expect(overflowX).toBe("auto");

  const [scrollW, clientW] = await page.evaluate(() => [
    document.documentElement.scrollWidth,
    document.documentElement.clientWidth,
  ]);
  expect(scrollW).toBeLessThanOrEqual(clientW + 1);
});
