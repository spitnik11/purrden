import { expect, test } from "@playwright/test";

test("claims a guest into a named account and revokes it on logout", async ({ page }) => {
  test.skip(!process.env.PURRDEN_AUTH_E2E, "requires the local API and Keycloak stack");

  await expect.poll(async () => fetch("http://127.0.0.1:8081/realms/purrden/.well-known/openid-configuration").then((r) => r.status).catch(() => 0), { timeout: 60_000 }).toBe(200);
  await page.goto("http://localhost:8080");
  await page.getByRole("button", { name: "Cloud save" }).click();
  await page.getByRole("button", { name: "Claim local garden" }).click();

  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/bootstrap");
    return response.ok ? (await response.json()).player_id as string : "";
  })).not.toBe("");
  const playerId = await page.evaluate(async () => (await fetch("/api/v1/bootstrap")).json().then((body) => body.player_id as string));

  await page.getByRole("button", { name: "Sign in / claim account" }).click();
  await page.getByRole("link", { name: /register/i }).click();
  const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  await page.getByLabel("Username").fill(`purrden-${id}`);
  await page.getByLabel("Email").fill(`purrden-${id}@example.test`);
  await page.getByLabel("First name").fill("Purrden");
  await page.getByLabel("Last name").fill("Test");
  await page.getByLabel("Password", { exact: true }).fill(`Purrden-${id}!`);
  await page.getByLabel("Confirm password").fill(`Purrden-${id}!`);
  await page.getByRole("button", { name: "Register" }).click();

  await expect(page).toHaveURL("http://localhost:8080/");
  expect(await page.evaluate(async () => (await fetch("/api/v1/bootstrap")).json().then((body) => body.player_id))).toBe(playerId);

  await page.getByRole("button", { name: "Cloud save" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect.poll(() => page.evaluate(() => fetch("/api/v1/bootstrap").then((r) => r.status))).toBe(401);
});
