import { test, expect } from "@playwright/test";

test("shell renders and shows API connectivity", async ({ page, request }) => {
  await page.route("**/api/health/live", route => route.fulfill({ json: { status: "ok" } }));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("Соединение установлено");
  expect(await (await request.get("/health")).json()).toEqual({ status: "ok" });
});

test("shell reports API failures", async ({ page }) => {
  await page.route("**/api/health/live", route => route.fulfill({ status: 503, json: {} }));
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Сервис временно недоступен");
});
