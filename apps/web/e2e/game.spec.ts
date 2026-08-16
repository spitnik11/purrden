import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("boots under the production CSP", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).not.toContain("'unsafe-eval'");
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.getByText("Failed to start Purrden")).toHaveCount(0);
});

test("keeps the game large and menus keyboard accessible on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const canvas = page.locator("canvas");
  await expect(canvas).toBeVisible();
  expect((await canvas.boundingBox())?.height).toBeGreaterThanOrEqual(500);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

  const focusButton = page.getByRole("button", { name: "Focus" });
  await focusButton.click();
  const dialog = page.getByRole("dialog", { name: "Focus" });
  await expect(dialog).toBeVisible();
  for (const button of await dialog.getByRole("button").all()) {
    expect((await button.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  }

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(focusButton).toBeFocused();
});

test("has no WCAG 2.2 A or AA violations", async ({ page }) => {
  await page.goto("/");
  for (const name of ["Focus", "World", "Cat dex", "Cloud save", "Save"]) {
    await page.getByRole("button", { name, exact: true }).click();
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(results.violations, `${name} menu accessibility violations`).toEqual([]);
  }
});

test.describe("accessibility preferences", () => {
  test("supports keyboard-only play in Windows high contrast", async ({ page }) => {
    await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
    await page.goto("/");
    await expect(page.getByRole("main")).toBeVisible();
    expect(await page.evaluate(() => matchMedia("(forced-colors: active)").matches)).toBe(true);
    expect(await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches)).toBe(true);

    await page.keyboard.press("Tab");
    const focusButton = page.getByRole("button", { name: "Focus", exact: true });
    await expect(focusButton).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog", { name: "Focus" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Close menu" })).toBeFocused();
    expect(parseFloat(await focusButton.evaluate((button) => getComputedStyle(button).transitionDuration))).toBeLessThanOrEqual(0.00001);
  });
});
