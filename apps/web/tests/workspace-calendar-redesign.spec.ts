import { expect, test } from "@playwright/test";
import { calendarEvent, mockWorkspace } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

const picker = (page: import("@playwright/test").Page) => page.getByRole("dialog", { name: "Дата и время события", exact: true });

test("mini calendar changes the visible date without writes and supports keyboard selection", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/workspace");
  const month = page.locator(".sidebar-calendar");
  await month.getByRole("button", { name: /15 октября 2026/ }).click();
  await expect(page.locator(".week-title")).toContainText("15 октября");
  await month.getByRole("button", { name: /15 октября 2026/ }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(month.getByRole("button", { name: /16 октября 2026/ })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator(".week-title")).toContainText("16 октября");
  expect(state.writes).toEqual([]);
});

test("drag moves a personal interval across days with its duration and version", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:00Z", ends_at: "2026-10-16T15:00:00Z" })];
  await page.goto("/workspace");
  const card = page.locator(".event-card-open");
  await card.scrollIntoViewIfNeeded();
  const box = (await card.boundingBox())!;
  const target = (await page.locator(".day-canvas").nth(1).boundingBox())!;
  await page.mouse.move(box.x + 20, box.y + 20);
  await page.mouse.down();
  await page.mouse.move(target.x + target.width / 2, box.y + 74, { steps: 8 });
  await expect(page.locator(".calendar-move-preview")).toBeVisible();
  expect(state.writes).toEqual([]);
  await page.mouse.up();
  await expect.poll(() => state.writes.length).toBe(1);
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ expected_version: 1, starts_at: "2026-10-13T15:00:00.000Z", ends_at: "2026-10-13T16:00:00.000Z" });
  await expect(page.locator(".calendar-move-preview")).toHaveCount(0);
  await expect(page.locator(".event-detail")).toHaveCount(0);
});

test("keyboard move cancels or commits explicitly while IIS stays read-only", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:00Z", ends_at: "2026-10-16T15:00:00Z" }), calendarEvent({ id: "official:2", source: "official", title: "Official class", starts_at: "2026-10-16T16:00:00Z", ends_at: "2026-10-16T17:00:00Z" })];
  await page.goto("/workspace");
  const card = page.locator(".personal-event .event-card-open");
  await card.focus();
  await page.keyboard.press("Alt+ArrowDown");
  await expect(page.locator(".calendar-move-preview")).toBeVisible();
  await page.keyboard.press("Escape");
  expect(state.writes).toEqual([]);
  await page.keyboard.press("Alt+ArrowUp");
  await page.keyboard.press("Enter");
  await expect.poll(() => state.writes.length).toBe(1);
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ starts_at: "2026-10-16T13:45:00.000Z", ends_at: "2026-10-16T14:45:00.000Z" });
  await page.locator(".official-event .event-card-open").focus();
  await page.keyboard.press("Alt+ArrowDown");
  await expect(page.locator(".calendar-move-preview")).toHaveCount(0);
  expect(state.writes).toHaveLength(1);
});

test("time strip applies any minute only to the draft and cancellation is local", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Minute precision");
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("9:37");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T09:37");
  expect(state.writes).toEqual([]);
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("0937");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T09:37");
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("08:00");
  await picker(page).getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T09:37");
  await page.locator(".event-modal").getByRole("button", { name: "Добавить событие", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ starts_at: "2026-10-16T09:37:00.000Z" });
});

test("minute stepping rolls the end date over midnight without implicit writes", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByRole("button", { name: "Выбрать окончание", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("23:59");
  await picker(page).getByRole("button", { name: "На минуту позже", exact: true }).click();
  await expect(picker(page).getByLabel("Точное время")).toHaveValue("00:00");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-17T00:00");
  expect(state.writes).toEqual([]);
});

test("custom picker rejects a DST gap and preserves elapsed duration across it", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.timezone = "America/New_York";
  await page.clock.setSystemTime(new Date("2026-03-08T12:00:00Z"));
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("02:30");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(picker(page).getByRole("alert")).toContainText("не существует");
  await picker(page).getByLabel("Точное время").fill("01:30");
  await picker(page).getByRole("group", { name: "Длительность события" }).getByRole("button", { name: "60 мин", exact: true }).click();
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-03-08T03:30");
  expect(state.writes).toEqual([]);
});

test("custom picker requires an explicit repeated-hour occurrence", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.timezone = "America/New_York";
  await page.clock.setSystemTime(new Date("2026-11-01T12:00:00Z"));
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Second occurrence");
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByLabel("Точное время").fill("01:30");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await expect(picker(page).getByRole("alert")).toContainText("повторяется");
  await picker(page).getByLabel("Смещение выбранного времени").selectOption("2026-11-01T06:30:00.000Z");
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await page.locator(".event-modal").getByRole("button", { name: "Добавить событие", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ starts_at: "2026-11-01T06:30:00.000Z" });
});

for (const width of [320, 390, 834, 1440]) {
  test(`calendar and time strip fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 1000 });
    const state = await mockWorkspace(page);
    state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:00Z", ends_at: "2026-10-16T15:00:00Z" })];
    await page.goto("/workspace");
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      await page.screenshot({ path: info.outputPath(`calendar-${theme}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await page.getByRole("button", { name: "Новое событие", exact: true }).click();
      await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
      await expect(picker(page)).toBeVisible();
      await expect(picker(page).getByRole("button", { name: "Применить", exact: true })).toBeInViewport({ ratio: 1 });
      await page.screenshot({ path: info.outputPath(`time-strip-${theme}.png`), fullPage: false, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      if (width <= 390) {
        const day = (await picker(page).locator(".month-days button").first().boundingBox())!;
        expect(day.width).toBeGreaterThanOrEqual(44);
        expect(day.height).toBeGreaterThanOrEqual(44);
      }
      await page.keyboard.press("Escape");
      await expect(page.getByRole("button", { name: "Выбрать начало", exact: true })).toBeFocused();
      await page.keyboard.press("Escape");
    }
    expect(state.writes).toEqual([]);
  });
}

test("opening and applying an unchanged time preserves original seconds", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:37Z", ends_at: "2026-10-16T15:00:42Z" })];
  await page.goto("/workspace");
  await page.locator(".event-card-open").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await picker(page).getByRole("button", { name: "Применить", exact: true }).click();
  await page.locator(".event-modal").getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ starts_at: "2026-10-16T14:00:37.000Z", ends_at: "2026-10-16T15:00:42.000Z" });
});

test("move conflicts retain authoritative geometry and do not claim success", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  await page.route("**/api/v1/calendar/personal-events/*", route => route.fulfill({ status: 409, json: { code: "event_version_conflict" } }));
  await page.goto("/workspace");
  const card = page.locator(".personal-event .event-card-open");
  const original = await page.locator(".event-card").getAttribute("style");
  await card.focus();
  await page.keyboard.press("Alt+ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.locator(".inline-error")).toBeVisible();
  await expect(page.locator(".calendar-move-preview")).toHaveCount(0);
  await expect(page.locator(".event-card")).toHaveAttribute("style", original!);
  await expect(page.locator(".toast")).toHaveCount(0);
});

test.describe("touch placement", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test("touch uses an explicit destination preview and confirmation", async ({ page }) => {
    const state = await mockWorkspace(page);
    state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:00Z", ends_at: "2026-10-16T15:00:00Z" })];
    await page.goto("/workspace");
    await page.locator(".event-card-open").tap();
    await page.getByRole("button", { name: "Перенести событие", exact: true }).tap();
    await expect(page.getByRole("region", { name: "Перенос события", exact: true })).toBeVisible();
    await page.locator(".calendar-scroll").evaluate(element => { element.scrollTop = 8 * 54; });
    const box = (await page.locator(".day-canvas").boundingBox())!;
    await page.touchscreen.tap(box.x + box.width / 2, box.y + 10 * 54);
    await expect(page.locator(".calendar-move-preview")).toBeVisible();
    expect(state.writes).toEqual([]);
    await page.getByRole("button", { name: "Применить перенос", exact: true }).tap();
    await expect.poll(() => state.writes.length).toBe(1);
    await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ expected_version: 1, starts_at: "2026-10-16T10:00:00.000Z", ends_at: "2026-10-16T11:00:00.000Z" });
  });
});

test("keyboard movement across the repeated hour preserves elapsed duration", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.timezone = "America/New_York";
  await page.clock.setSystemTime(new Date("2026-11-01T12:00:00Z"));
  state.events = [calendarEvent({ starts_at: "2026-11-01T05:45:00Z", ends_at: "2026-11-01T06:15:00Z" })];
  await page.goto("/workspace");
  await page.locator(".event-card-open").focus();
  await page.keyboard.press("Alt+ArrowDown");
  await page.keyboard.press("Enter");
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toMatchObject({ expected_version: 1, starts_at: "2026-11-01T06:00:00.000Z", ends_at: "2026-11-01T06:30:00.000Z" });
});

for (const width of [390, 1440]) {
  test(`event inspection restores the time-grid scroll and focus at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const state = await mockWorkspace(page);
    state.events = [calendarEvent({ starts_at: "2026-10-16T14:00:00Z", ends_at: "2026-10-16T15:00:00Z" })];
    await page.goto("/workspace");
    await expect(page.locator(".event-card-open")).toHaveCount(1);
    await page.locator(".calendar-scroll").evaluate(element => { element.scrollTop = 11 * 54; });
    const before = await page.locator(".calendar-scroll").evaluate(element => element.scrollTop);
    await page.locator(".event-card-open").click();
    await expect(page.locator(".event-detail")).toBeVisible();
    if (width === 1440) await expect(page.locator(".calendar-card")).toBeVisible();
    await page.screenshot({ path: info.outputPath("inspector.png"), fullPage: true, animations: "disabled" });
    await page.getByRole("button", { name: /К календарю/ }).click();
    await expect(page.locator(".event-card-open")).toBeFocused();
    expect(await page.locator(".calendar-scroll").evaluate(element => element.scrollTop)).toBe(before);
    expect(state.writes).toEqual([]);
  });
}
