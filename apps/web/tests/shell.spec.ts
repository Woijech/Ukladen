import { test, expect } from "@playwright/test";

test("shell renders and shows API connectivity", async ({ page, request }) => {
  await page.route("**/api/health/live", route => route.fulfill({ json: { status: "ok" } }));
  await page.goto("/");
  await expect(page).toHaveTitle("Ukladen");
  await expect(page.locator("header").getByText("Ukladen", { exact: true })).toBeVisible();
  await expect(page.locator("header").getByRole("link", { name: /Войти/ })).toHaveAttribute("href", "/workspace");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Соединение установлено");
  expect(await (await request.get("/health")).json()).toEqual({ status: "ok" });
});

test("shell reports API failures", async ({ page }) => {
  await page.route("**/api/health/live", route => route.fulfill({ status: 503, json: {} }));
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Сервис временно недоступен");
});


test("the home page opens the workspace sign-in flow", async ({ page }) => {
  await page.route("**/api/health/live", route => route.fulfill({ json: { status: "ok" } }));
  await page.route("**/api/v1/users/me", route => route.fulfill({ status: 401, json: { detail: "Invalid session." } }));
  await page.goto("/");
  await page.getByRole("link", { name: "Открыть календарь" }).click();
  await expect(page).toHaveURL("/workspace");
  await expect(page.getByRole("heading", { name: "Войти в Ukladen" })).toBeVisible();
});
