import { expect, test, type Page } from "@playwright/test";

/**
 * End-to-end coverage of the dashboard against the real backend.
 *
 * These assert the things a screenshot review would miss and a unit test cannot reach: that
 * the engine's clause citation survives all the way to the drill-down, that the FASTag row
 * reads as EXEMPT rather than merely absent from the failures, and that the evidence panel
 * can actually load a run.
 *
 * Requires the backend on :8000. Run: `npm run test:e2e`
 */

const API = "http://localhost:8000/api/v1";

test.beforeAll(async ({ request }) => {
  const health = await request.get(`${API}/health`);
  expect(
    health.ok(),
    "backend must be running on :8000 — start it with:\n" +
      "  cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000",
  ).toBeTruthy();
});

/** The splash covers the page for ~1.3s on a full load; wait it out before interacting. */
async function ready(page: Page) {
  await page.locator("[data-splash]").waitFor({ state: "detached", timeout: 10_000 });
}

async function runPlantedViolations(page: Page) {
  await page.goto("/verify");
  await ready(page);
  await page.getByRole("button", { name: /Planted violations/ }).click();
  await page.getByRole("button", { name: /Run verification/ }).click();
  await page.waitForURL(/\/reports\/rep_/, { timeout: 30_000 });
  await expect(page.getByRole("heading", { name: "Compliance report" })).toBeVisible();
}

test.describe("dashboard", () => {
  test("renders and links to a verification", async ({ page }) => {
    await page.goto("/");
    await ready(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("link", { name: /Run a verification/ })).toBeVisible();
  });

  test("surfaces unverified regulatory values rather than hiding them", async ({ page }) => {
    await page.goto("/");
    await ready(page);
    await expect(page.getByText(/pending verification/)).toBeVisible();
  });
});

test.describe("verify", () => {
  test("loads a sample and states what it should prove", async ({ page }) => {
    await page.goto("/verify");
    await ready(page);
    await page.getByRole("button", { name: /Planted violations/ }).click();

    const payload = page.locator("#payload");
    expect((await payload.inputValue()).length).toBeGreaterThan(1000);
    await expect(page.getByText(/^Expect:/)).toBeVisible();
    await expect(page.getByText(/✓ 10 actions/)).toBeVisible();
  });

  test("rejects malformed JSON before making a round trip", async ({ page }) => {
    await page.goto("/verify");
    await ready(page);
    await page.locator("#payload").fill("{ not json");
    await page.getByRole("button", { name: /Run verification/ }).click();
    await expect(page.getByText(/not valid JSON/)).toBeVisible();
  });
});

test.describe("report", () => {
  test("scores the planted batch and splits pass/fail/exempt", async ({ page }) => {
    await runPlantedViolations(page);

    const score = page.locator("section[aria-label='Compliance score']");
    await expect(score).toContainText("40.0");
    await expect(score).toContainText("4 pass");
    await expect(score).toContainText("6 fail");
    await expect(score).toContainText("1 exempt");
  });

  test("filters to failures", async ({ page }) => {
    await runPlantedViolations(page);
    await page.getByRole("button", { name: /^Fail/ }).click();
    await expect(page.locator("table tbody tr")).toHaveCount(6);
  });

  test("drill-down cites the clause and the offending value", async ({ page }) => {
    await runPlantedViolations(page);

    const expander = page.locator('button[aria-controls="detail-a_v03"]');
    await expander.click();
    await expect(expander).toHaveAttribute("aria-expanded", "true");

    const detail = page.locator("#detail-a_v03");
    await expect(detail).toContainText("AFA_ABOVE_THRESHOLD");
    await expect(detail).toContainText("RBI/DPSS/2026-27/396 §8(a)");
    await expect(detail).toContainText("amount 20000 > 15000 but afa_present=false");
  });

  test("the FASTag debit passes AS EXEMPT, not merely unflagged", async ({ page }) => {
    // The demo money-shot: a short-notice debit that must pass, and must say why.
    await runPlantedViolations(page);
    await page.locator('button[aria-controls="detail-a_v07"]').click();

    const detail = page.locator("#detail-a_v07");
    await expect(detail).toContainText("EXEMPT_MCC_SKIP_NOTICE");
    await expect(detail).toContainText("4784");
    await expect(detail).toContainText("RBI/DPSS/2026-27/396 §6(d)");
  });

  test("run evidence exposes the budget and the append-only audit trail", async ({ page }) => {
    await runPlantedViolations(page);
    await page.getByRole("button", { name: /Run & evidence/ }).click();

    const evidence = page.locator("#run-evidence");
    await expect(evidence).toContainText(/budget/i);
    await expect(evidence).toContainText(/append-only/i);
    await expect(evidence.getByRole("button", { name: /Replay this run/ })).toBeVisible();
  });
});

test.describe("rule-pack", () => {
  test("shows every rule with its citation and flags unverified values", async ({ page }) => {
    await page.goto("/rules");
    await ready(page);
    // By role, not by text: the source name also appears on every rule's citation line,
    // so a bare text locator matches four elements and trips strict mode.
    await expect(
      page.getByRole("heading", { name: "RBI Digital Payments E-mandate Framework 2026" }),
    ).toBeVisible();
    await expect(page.getByText(/pending verification/)).toBeVisible();
    await expect(page.locator("section[aria-labelledby='rules-heading'] article")).toHaveCount(7);
  });

  test("search narrows the rule list", async ({ page }) => {
    await page.goto("/rules");
    await ready(page);
    // "AFA" matches two of the seven rules, and the second one is the point: search covers
    // clause_text, so NO_DEBIT_AFTER_OPT_OUT is found via §6(c)'s own words ("validated by
    // the issuer using AFA") rather than only via our paraphrase of it.
    await page.locator("#rule-search").fill("AFA");
    await expect(page.locator("section[aria-labelledby='rules-heading'] article")).toHaveCount(2);

    await page.locator("#rule-search").fill("quiet");
    await expect(page.locator("section[aria-labelledby='rules-heading'] article")).toHaveCount(1);
  });

  test("a verified rule quotes the law it cites", async ({ page }) => {
    // A citation nobody can check is an assertion. The screen has to carry the sentence,
    // otherwise "cites the exact clause" rests on trusting a paragraph number.
    await page.goto("/rules");
    await ready(page);
    await expect(
      page.getByText("All recurring transactions may be authorised without AFA up to", {
        exact: false,
      }),
    ).toBeVisible();
  });

  test("a secondary-sourced value is not dressed up as quoted law", async ({ page }) => {
    // The failure this guards against is cosmetic and serious: an unverified value styled
    // like a quotation would assert exactly the authority the flag exists to deny.
    await page.goto("/rules");
    await ready(page);
    const warned = page.getByText(/Multiple consistent secondary sources report/).first();
    await expect(warned).toBeVisible();
    await expect(warned.locator("xpath=ancestor-or-self::blockquote")).toHaveCount(0);
  });

  test("search finds a rule by the wording of the law, not just our paraphrase", async ({
    page,
  }) => {
    await page.goto("/rules");
    await ready(page);
    await page.locator("#rule-search").fill("pre-transaction notification");
    await expect(
      page.locator("section[aria-labelledby='rules-heading'] article"),
    ).toHaveCount(1);
  });

  test("a category-only exemption explains itself without an empty MCC clause", async ({
    page,
  }) => {
    // §8(b) matches on category plus an amount ceiling and carries no MCC. The viewer used
    // to hard-code "MCC is {list}", rendering the literal text "MCC is ." for this one.
    await page.goto("/rules");
    await ready(page);
    const card = page
      .locator("section[aria-labelledby='exemptions-heading'] article")
      .filter({ hasText: "EXEMPT_HIGH_VALUE_CATEGORY_AFA" });
    await expect(card).toContainText("the category is");
    await expect(card).toContainText("at most");
    await expect(card).not.toContainText("MCC is .");
  });
});

test.describe("chrome", () => {
  test("theme toggles and survives navigation", async ({ page }) => {
    await page.goto("/rules");
    await ready(page);

    const toggle = page.locator('button[aria-label*="Theme"]');
    await toggle.click();
    await toggle.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.getByRole("link", { name: "Dashboard" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  });

  test("splash shows on load, clears itself, and does not re-fire on navigation", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "commit" });
    await expect(page.locator("[data-splash]")).toBeAttached();
    await ready(page);

    await page.getByRole("link", { name: "Verify" }).click();
    await expect(page.getByText("Load a sample batch")).toBeVisible();
    await expect(page.locator("[data-splash]")).toHaveCount(0);
  });

  test("no horizontal overflow on a phone viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/verify");
    await ready(page);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(391);
  });
});
