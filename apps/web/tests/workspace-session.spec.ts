import { test, expect } from "@playwright/test";
import { calendarEvent, login, mockWorkspace } from "./workspace-fixtures";

test("switching accounts discards cached weeks and private forms even while the new calendar is delayed", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  await page.goto("/workspace");
  await expect(page.locator(".event-card")).toContainText("Private plan");
  await page.locator(".event-card").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await expect(page.getByLabel("Описание", { exact: false })).toHaveValue("Private description");
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await page.getByRole("button", { name: /К календарю/ }).click();
  await page.getByRole("button", { name: "Следующая неделя" }).click();
  await page.locator(".account-button").click();
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  await expect(page.getByRole("heading", { name: "Войти в Ukladen" })).toBeVisible();
  state.userId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  state.events = [];
  let release!: () => void;
  state.holdCalendar = new Promise<void>(resolve => { release = resolve; });
  await login(page);
  await page.getByRole("button", { name: "Пока без группы" }).click();
  await page.getByRole("button", { name: "Предыдущая неделя" }).click();
  await expect(page.getByText("Private plan")).toHaveCount(0);
  release();
  await expect(page.getByText("На этой неделе пока нет событий")).toBeVisible();
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await expect(page.getByLabel("Название", { exact: true })).toBeEmpty();
  await expect(page.getByLabel("Описание", { exact: false })).toBeEmpty();
});

test("an expired session removes the workspace and its open private form", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  await page.goto("/workspace");
  await page.locator(".event-card").click();
  state.authenticated = false;
  await page.evaluate(() => window.dispatchEvent(new Event("visibilitychange")));
  await expect(page.getByRole("heading", { name: "Войти в Ukladen" })).toBeVisible();
  await expect(page.locator("#event-description")).toHaveCount(0);
  await expect(page.getByText("Private plan")).toHaveCount(0);
});
