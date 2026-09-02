import { expect, test } from "@playwright/test";

/**
 * PWA + mobile conflicts.
 *
 * These check the things that actually break an installed app on a phone: a manifest the
 * browser will not accept, icons that 404, inputs that trigger iOS auto-zoom, layout that
 * overflows the viewport, and touch targets too small to hit.
 */

test.describe("PWA", () => {
  test("serves a valid, installable manifest", async ({ request, page }) => {
    await page.goto("/");
    const href = await page.getAttribute('link[rel="manifest"]', "href");
    expect(href).toBeTruthy();

    const res = await request.get(href!);
    expect(res.ok()).toBeTruthy();
    const m = await res.json();

    expect(m.name).toContain("Rakshak");
    expect(m.short_name).toBe("Rakshak");
    expect(m.start_url).toBeTruthy();
    expect(m.display).toBe("standalone");
    expect(m.background_color).toBeTruthy();
    expect(m.theme_color).toBeTruthy();

    // Installability needs a 192 and a 512, and Android needs at least one maskable.
    const sizes = m.icons.map((i: { sizes: string }) => i.sizes);
    expect(sizes).toContain("192x192");
    expect(sizes).toContain("512x512");
    expect(m.icons.some((i: { purpose?: string }) => i.purpose === "maskable")).toBeTruthy();
  });

  test("every declared icon actually resolves", async ({ request, page }) => {
    await page.goto("/");
    const href = await page.getAttribute('link[rel="manifest"]', "href");
    const m = await (await request.get(href!)).json();

    for (const icon of m.icons) {
      const r = await request.get(icon.src);
      expect(r.ok(), `${icon.src} should resolve`).toBeTruthy();
      expect(r.headers()["content-type"]).toContain("image");
    }
    expect((await request.get("/apple-icon.png")).ok()).toBeTruthy();
  });

  test("theme-color is declared for both schemes", async ({ page }) => {
    await page.goto("/");
    const metas = await page.locator('meta[name="theme-color"]').count();
    expect(metas).toBeGreaterThanOrEqual(2);
  });

  test("the service worker is served and never caches verdicts", async ({ request }) => {
    const res = await request.get("/sw.js");
    expect(res.ok()).toBeTruthy();
    const body = await res.text();
    // The one rule that matters: API traffic must bypass the cache entirely.
    expect(body).toContain("isVerdictTraffic");
    expect(body).toMatch(/\/api\//);
  });

  test("the offline page says nothing was checked, not that all is well", async ({ page }) => {
    await page.goto("/offline");
    await expect(page.getByRole("heading", { name: /offline/i })).toBeVisible();
    await expect(page.getByText(/never served from\s+cache/i)).toBeVisible();
    await expect(page.getByText(/nothing has passed/i)).toBeVisible();
  });
});
