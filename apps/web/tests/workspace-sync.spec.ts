import { test, expect } from "@playwright/test";
import { calendarEvent, mockWorkspace, profile } from "./workspace-fixtures";

test("a running import is polled and completion refreshes the calendar", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.profile = profile;
  state.status = { ...state.status, status: "syncing", last_attempt_at: "2026-10-16T12:00:00Z" };
  await page.goto("/workspace");
  await expect(page.locator(".schedule-sync-notice")).toContainText("синхронизирует");
  state.events = [calendarEvent({ source: "official", kind: "lesson", title: "Imported lesson" })];
  state.status = { ...state.status, status: "ready", last_success_at: "2026-10-16T12:00:01Z" };
  await page.clock.fastForward(3100);
  await expect(page.locator(".event-card")).toContainText("Imported lesson");
  await expect(page.locator(".schedule-sync-notice")).toHaveCount(0);
});

for (const status of ["error", "unpublished", "unsupported"]) {
  test(`a stored ${status} source has an actionable notice`, async ({ page }) => {
    const state = await mockWorkspace(page);
    state.profile = profile;
    state.status.status = status;
    await page.goto("/workspace");
    await expect(page.locator(".schedule-sync-notice")).toBeVisible();
    await expect(page.getByRole("button", { name: "Повторить синхронизацию" })).toBeEnabled();
    await expect(page.locator(".schedule-sync-notice")).not.toHaveClass(/is-success/);
  });
}

test("reconnecting a previously imported group waits for a new result and recovers after a delayed worker", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.profile = profile;
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Настроить учебную группу" }).click();
  await page.getByRole("button", { name: "Сохранить группу" }).click();
  await expect(page.locator(".schedule-sync-notice")).toContainText("IIS загружает");
  await page.clock.fastForward(181_000);
  await expect(page.locator(".schedule-sync-notice")).toContainText("Продолжаем проверять статус");
  await expect(page.locator(".schedule-sync-notice")).not.toHaveClass(/is-success/);
  state.status = { ...state.status, last_attempt_at: "2026-10-16T12:03:02Z", last_success_at: "2026-10-16T12:03:03Z" };
  await page.clock.fastForward(3100);
  await expect(page.locator(".schedule-sync-notice")).toHaveClass(/is-success/);
  await expect(page.locator(".schedule-sync-notice")).toContainText("Расписание синхронизировано");
});

test("an import finishing before the sync POST returns is recognized without a later false timeout", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.profile = profile;
  state.status.status = "error";
  state.onSync = () => { state.status = { ...state.status, status: "ready", last_attempt_at: "2026-10-16T12:00:00Z", last_success_at: "2026-10-16T12:00:01Z" }; };
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Повторить синхронизацию" }).click();
  await expect(page.locator(".schedule-sync-notice")).toHaveClass(/is-success/);
  await page.clock.fastForward(181_000);
  await expect(page.locator(".schedule-sync-notice")).toHaveClass(/is-success/);
  expect(state.writes.filter(write => write.path === "/api/v1/schedule/me/sync")).toHaveLength(1);
});
