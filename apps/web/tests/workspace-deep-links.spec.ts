import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";

test("calendar date and explicit layout survive reload, back and forward", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace?section=calendar&date=2026-11-13&view=day");
  await expect(page.getByRole("region", { name: "Календарь на день", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Следующий день", exact: true }).click();
  await expect(page).toHaveURL(/date=2026-11-14&view=day/);
  await page.getByRole("button", { name: "Неделя", exact: true }).click();
  await expect(page).toHaveURL(/date=2026-11-14&view=week/);
  await page.reload();
  await expect(page.getByRole("region", { name: "Календарь на неделю", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("region", { name: "Календарь на день", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/date=2026-11-13&view=day/);
  await page.goForward();
  await expect(page).toHaveURL(/date=2026-11-14&view=day/);
  expect(state.writes).toEqual([]);
});

test("malformed calendar values are replaced with safe defaults without an extra history entry", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/workspace?section=tasks");
  await page.goto("/workspace?section=calendar&date=2026-02-30&view=invalid");
  await expect(page.getByRole("alert").filter({ hasText: "Некорректные параметры ссылки" })).toBeVisible();
  await expect(page).toHaveURL(/\/workspace\?section=calendar$/);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
});
