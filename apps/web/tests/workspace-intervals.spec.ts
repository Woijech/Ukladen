import { test, expect } from "@playwright/test";
import { calendarEvent, mockWorkspace } from "./workspace-fixtures";

test.use({ timezoneId: "UTC" });

test("the whole day and overnight continuations occupy their actual intervals", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [
    calendarEvent({ id: "early", title: "Early plan", starts_at: "2026-10-12T00:30:00Z", ends_at: "2026-10-12T01:00:00Z" }),
    calendarEvent({ id: "overnight", title: "Overnight plan", starts_at: "2026-10-16T23:00:00Z", ends_at: "2026-10-17T01:00:00Z" }),
    calendarEvent({ id: "long", title: "Long plan", starts_at: "2026-10-13T09:00:00Z", ends_at: "2026-10-13T18:00:00Z" }),
  ];
  await page.goto("/workspace");
  const early = page.locator(".event-card").filter({ hasText: "Early plan" });
  await expect(early).toHaveCSS("top", "27px");
  await expect(early).toHaveCSS("height", "27px");
  const night = page.locator(".event-card").filter({ hasText: "Overnight plan" });
  await expect(night).toHaveCount(2);
  await expect(night.nth(0)).toHaveCSS("top", "1242px");
  await expect(night.nth(0)).toHaveCSS("height", "54px");
  await expect(night.nth(1)).toHaveCSS("top", "0px");
  await expect(night.nth(1)).toHaveCSS("height", "54px");
  await expect(page.locator(".event-card").filter({ hasText: "Long plan" })).toHaveCSS("height", "486px");
  await night.nth(1).click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T23:00");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-17T01:00");
});

test("an event starting before the week remains visible on Monday without navigating to the previous week", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ title: "Week continuation", starts_at: "2026-10-11T23:30:00Z", ends_at: "2026-10-12T01:00:00Z" })];
  await page.goto("/workspace");
  const card = page.locator(".event-card");
  await expect(card).toHaveCount(1);
  await expect(card).toHaveCSS("top", "0px");
  await expect(card).toHaveCSS("height", "54px");
  await card.click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await expect(page.getByLabel("Название", { exact: true })).toHaveValue("Week continuation");
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await page.getByRole("button", { name: /К календарю/ }).click();
  await expect(page.locator(".week-title strong")).toContainText("12 октября");
  await expect(page.locator(".agenda-row")).toContainText("Week continuation");
});

test("touching midnight does not duplicate an event on the next day", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-12T23:00:00Z", ends_at: "2026-10-13T00:00:00Z" })];
  await page.goto("/workspace");
  await expect(page.locator(".event-card")).toHaveCount(1);
});
