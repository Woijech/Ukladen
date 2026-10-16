import { test, expect } from "@playwright/test";
import { dateKey, dateTimeLocal, dayStart, localInstants, resolveLocalTime, shiftDate, startOfWeek } from "../src/app/workspace/calendar-time";
import { calendarEvent, mockWorkspace } from "./workspace-fixtures";

test("civil dates, day bounds and local input preserve timezone and DST semantics", () => {
  expect(dateKey(new Date("2026-10-18T22:30:00Z"), "Europe/Minsk")).toBe("2026-10-19");
  expect(startOfWeek("2026-10-19")).toBe("2026-10-19");
  expect(shiftDate("2026-03-01", -1)).toBe("2026-02-28");
  expect(localInstants("2026-02-31T10:00", "UTC")).toEqual([]);
  expect(localInstants("2026-03-08T02:30", "America/New_York")).toEqual([]);
  expect(localInstants("2026-11-01T01:30", "America/New_York")).toEqual(["2026-11-01T05:30:00.000Z", "2026-11-01T06:30:00.000Z"]);
  expect(() => resolveLocalTime("2026-11-01T01:30", "America/New_York", "")).toThrow("повторяется");
  expect(resolveLocalTime("2026-11-01T01:30", "America/New_York", "2026-11-01T06:30:37.000Z", "2026-11-01T06:30:37Z")).toBe("2026-11-01T06:30:37.000Z");
  expect(dateTimeLocal(new Date("2026-10-11T21:30:00Z"), "Europe/Minsk")).toBe("2026-10-12T00:30");
  expect(dayStart("2026-03-09", "America/New_York").getTime() - dayStart("2026-03-08", "America/New_York").getTime()).toBe(23 * 3_600_000);
  expect(dayStart("2026-11-02", "America/New_York").getTime() - dayStart("2026-11-01", "America/New_York").getTime()).toBe(25 * 3_600_000);
  expect(dayStart("2026-10-04", "Australia/Lord_Howe").toISOString()).toBe("2026-10-03T13:30:00.000Z");
  expect(localInstants("2026-01-01T10:00", "Asia/Kathmandu")).toEqual(["2026-01-01T04:15:00.000Z"]);
});

for (const browserZone of ["UTC", "America/Los_Angeles"]) {
  test.describe(`calendar timezone with a ${browserZone} browser`, () => {
    test.use({ timezoneId: browserZone });
    test("early Minsk events keep their date, clock time and saved instant", async ({ page }) => {
      const state = await mockWorkspace(page);
      state.timezone = "Europe/Minsk";
      state.events = [calendarEvent({ title: "Minsk midnight", starts_at: "2026-10-11T21:30:00Z", ends_at: "2026-10-11T22:00:00Z" })];
      await page.goto("/workspace");
      const card = page.locator(".event-card");
      await expect(card).toHaveCSS("top", "27px");
      await expect(card).toContainText("00:30");
      await card.click();
      await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-12T00:30");
      await page.getByRole("button", { name: "Сохранить", exact: true }).click();
      await expect(page.locator(".event-modal")).toHaveCount(0);
      expect(state.writes.find(write => write.method === "PATCH")?.body).toMatchObject({ starts_at: "2026-10-11T21:30:00.000Z", ends_at: "2026-10-11T22:00:00.000Z" });
      await expect(card).toHaveCSS("top", "27px");
    });
    test("today and week boundaries follow the profile instead of the device", async ({ page }) => {
      const state = await mockWorkspace(page);
      state.timezone = "Europe/Minsk";
      await page.clock.setSystemTime(new Date("2026-10-18T22:30:00Z"));
      const ranges: string[] = [];
      page.on("request", request => { if (request.url().includes("/calendar/events?")) ranges.push(new URL(request.url()).searchParams.get("date_from")!); });
      await page.goto("/workspace");
      await expect(page.locator(".week-title strong")).toContainText("19 октября");
      expect(ranges).toContain("2026-10-19");
      await page.getByRole("button", { name: "Предыдущая неделя" }).click();
      await expect(page.locator(".week-title strong")).toContainText("12 октября");
      await page.getByRole("button", { name: "Сегодня", exact: true }).click();
      await expect(page.locator(".week-title strong")).toContainText("19 октября");
      await page.getByRole("button", { name: "Новое событие", exact: true }).click();
      await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-19T10:00");
    });
  });
}

test.describe("daylight-saving input and layout", () => {
  test.use({ timezoneId: "UTC" });
  test("a spring gap is rejected instead of silently shifting the event", async ({ page }) => {
    const state = await mockWorkspace(page);
    state.timezone = "America/New_York";
    await page.clock.setSystemTime(new Date("2026-03-08T12:00:00Z"));
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Новое событие", exact: true }).click();
    await page.getByLabel("Название", { exact: true }).fill("Spring gap");
    await page.getByLabel("Начало", { exact: true }).fill("2026-03-08T02:30");
    await page.getByLabel("Окончание", { exact: true }).fill("2026-03-08T03:30");
    await page.locator(".event-modal").getByRole("button", { name: "Добавить событие" }).click();
    await expect(page.locator(".event-modal").getByRole("alert")).toContainText("не существует");
    expect(state.writes).toEqual([]);
  });
  test("repeated hours keep distinct positions and an explicit offset selects the intended instant", async ({ page }) => {
    const state = await mockWorkspace(page);
    state.timezone = "America/New_York";
    await page.clock.setSystemTime(new Date("2026-11-01T12:00:00Z"));
    state.events = [calendarEvent({ id: "first", title: "First 01:30", starts_at: "2026-11-01T05:30:00Z", ends_at: "2026-11-01T05:45:00Z" }), calendarEvent({ id: "second", title: "Second 01:30", starts_at: "2026-11-01T06:30:00Z", ends_at: "2026-11-01T06:45:00Z" })];
    await page.goto("/workspace");
    await expect(page.locator(".event-card").filter({ hasText: "First 01:30" })).toHaveCSS("top", "81px");
    await expect(page.locator(".event-card").filter({ hasText: "Second 01:30" })).toHaveCSS("top", "135px");
    await expect(page.locator(".day-canvas").last()).toHaveCSS("height", "1350px");
    await page.getByRole("button", { name: "Новое событие", exact: true }).click();
    await page.getByLabel("Название", { exact: true }).fill("Second occurrence");
    await page.getByLabel("Начало", { exact: true }).fill("2026-11-01T01:30");
    await page.getByLabel("Окончание", { exact: true }).fill("2026-11-01T02:30");
    await page.getByLabel("Смещение начала", { exact: true }).selectOption("2026-11-01T06:30:00.000Z");
    await page.locator(".event-modal").getByRole("button", { name: "Добавить событие" }).click();
    await expect(page.locator(".event-modal")).toHaveCount(0);
    expect(state.writes.find(write => write.method === "POST")?.body).toMatchObject({ starts_at: "2026-11-01T06:30:00.000Z", ends_at: "2026-11-01T07:30:00.000Z" });
  });
});
