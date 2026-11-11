import { expect, test } from "@playwright/test";
import { calendarEvent, mockWorkspace } from "./workspace-fixtures";

async function grid(page: import("@playwright/test").Page) {
  await page.getByRole("button", { name: "День", exact: true }).click();
  await page.locator(".calendar-scroll").evaluate(element => { element.scrollTop = 8 * 54; });
  return (await page.locator(".day-canvas").boundingBox())!;
}

test("empty-space click stops its default duration before a neighbouring event", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T10:30:00Z", ends_at: "2026-10-16T11:30:00Z" })];
  await page.goto("/workspace");
  const box = await grid(page);
  await page.mouse.click(box.x + box.width / 2, box.y + 10.25 * 54 + 1);
  await expect(page.getByRole("dialog", { name: "Новое событие", exact: true })).toBeVisible();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T10:15");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T10:30");
  expect(state.writes).toEqual([]);
});

test("range selection cannot run underneath an existing event", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T11:00:00Z", ends_at: "2026-10-16T12:00:00Z" })];
  await page.goto("/workspace");
  const box = await grid(page);
  await page.mouse.move(box.x + box.width / 2, box.y + 10 * 54 + 1);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 11.5 * 54, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T10:00");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T11:00");
  expect(state.writes).toEqual([]);
});

test("non-quarter-hour neighbours bound both snapping and reverse selection", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T10:00:00Z", ends_at: "2026-10-16T11:07:00Z" })];
  await page.goto("/workspace");
  const box = await grid(page);
  await page.mouse.move(box.x + box.width / 2, box.y + 11.5 * 54);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2, box.y + 10.5 * 54, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T11:07");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T11:30");
  await page.keyboard.press("Escape");
  await page.mouse.click(box.x + box.width / 2, box.y + (11 + 8 / 60) * 54);
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T11:07");
  expect(state.writes).toEqual([]);
});

test("the narrow gutter beside an occupied card cannot create inside it", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T10:00:00Z", ends_at: "2026-10-16T11:00:00Z" })];
  await page.goto("/workspace");
  const box = await grid(page);
  await page.mouse.click(box.x + 1, box.y + 10.5 * 54);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.locator(".event-card-open").click();
  await expect(page.getByRole("heading", { name: "Private plan", exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("hidden IIS intervals still stop accidental empty-grid creation", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ source: "official", id: "official:class", starts_at: "2026-10-16T10:30:00Z", ends_at: "2026-10-16T11:30:00Z" })];
  await page.goto("/workspace");
  await page.getByLabel("Расписание IIS", { exact: true }).uncheck();
  const box = await grid(page);
  await page.mouse.click(box.x + box.width / 2, box.y + 10.25 * 54 + 1);
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T10:30");
  expect(state.writes).toEqual([]);
});

test("keyboard creation skips occupied time and clips duration at the next boundary", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T10:30:00Z", ends_at: "2026-10-16T11:30:00Z" })];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "День", exact: true }).click();
  const selection = page.locator(".calendar-selection");
  await selection.focus();
  await page.keyboard.press("Shift+ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T10:30");
  await page.keyboard.press("Escape");
  await selection.focus();
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T11:30");
  expect(state.writes).toEqual([]);
});

for (const width of [320, 390, 834, 1440]) {
  test(`calendar composition and contextual editing at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width < 400 ? 844 : 1000 });
    const state = await mockWorkspace(page);
    state.events = [
      calendarEvent({ id: "official:lecture", source: "official", title: "Математический анализ", starts_at: "2026-10-16T09:00:00Z", ends_at: "2026-10-16T10:30:00Z", location: "Аудитория 302" }),
      calendarEvent({ id: "personal:reading", source_event_id: "reading", title: "Подготовить конспект", starts_at: "2026-10-16T11:00:00Z", ends_at: "2026-10-16T12:00:00Z", location: "Библиотека" }),
      calendarEvent({ id: "personal:review", source_event_id: "review", title: "Разобрать задания", starts_at: "2026-10-16T11:30:00Z", ends_at: "2026-10-16T12:30:00Z", location: null }),
      calendarEvent({ id: "official:lab", source: "official", title: "Лабораторная работа", starts_at: "2026-10-15T13:00:00Z", ends_at: "2026-10-15T14:30:00Z", location: "Корпус 4" }),
      calendarEvent({ id: "personal:project", source_event_id: "project", title: "Учебный проект", starts_at: "2026-10-14T10:00:00Z", ends_at: "2026-10-14T12:00:00Z", location: null }),
    ];
    await page.goto("/workspace");
    const { checkWorkspaceVisuals } = await import("./design-checks");
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      await page.locator(".calendar-scroll").evaluate(element => { element.scrollTop = 8 * 54; });
      await page.screenshot({ path: info.outputPath(`workspace-${theme}.png`), fullPage: false, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      const left = (await page.locator(".event-card").filter({ hasText: "Подготовить конспект" }).boundingBox())!;
      const right = (await page.locator(".event-card").filter({ hasText: "Разобрать задания" }).boundingBox())!;
      expect(left.x + left.width).toBeLessThanOrEqual(right.x);
      if (width <= 834) {
        await page.getByRole("button", { name: "Календари", exact: true }).click();
        await expect(page.locator("#calendar-context")).toBeVisible();
        await page.screenshot({ path: info.outputPath(`sources-${theme}.png`), animations: "disabled" });
        await checkWorkspaceVisuals(page);
        if (width <= 390) {
          const day = (await page.locator("#calendar-context .month-days button").first().boundingBox())!;
          expect(day.width).toBeGreaterThanOrEqual(44);
          expect(day.height).toBeGreaterThanOrEqual(44);
        }
        await page.getByRole("button", { name: "Закрыть панель календарей", exact: true }).click();
      }
      await page.locator(".event-card-open").filter({ hasText: "Подготовить конспект" }).click();
      await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
      await expect(page.getByLabel("Название", { exact: true })).toBeFocused();
      await page.screenshot({ path: info.outputPath(`composer-${theme}.png`), animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: /К календарю/ }).click();
    }
    expect(state.writes).toEqual([]);
  });
}

test("compact calendar panel returns keyboard focus on Escape and mobile week scroll stays local", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockWorkspace(page);
  await page.goto("/workspace");
  const trigger = page.getByRole("button", { name: "Календари", exact: true });
  await trigger.click();
  await expect(page.locator('#calendar-context .month-days [aria-pressed="true"]')).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await expect(page.locator("#calendar-context")).toBeHidden();
  await page.getByRole("button", { name: "Неделя", exact: true }).click();
  const scroller = page.locator(".calendar-scroll");
  expect(await scroller.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
  expect(state.writes).toEqual([]);
});

test("the explicit editor still permits intentional overlaps without changing official facts", async ({ page }) => {
  const state = await mockWorkspace(page);
  const official = calendarEvent({ source: "official", id: "official:class", starts_at: "2026-10-16T10:00:00Z", ends_at: "2026-10-16T11:00:00Z" });
  state.events = [official];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "День", exact: true }).click();
  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Intentional overlap");
  await page.locator(".event-modal").getByRole("button", { name: "Добавить событие", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  await expect(page.locator(".event-card")).toHaveCount(2);
  expect(state.events.find(event => event.id === official.id)).toEqual(official);
  expect(state.writes[0].body).toMatchObject({ starts_at: "2026-10-16T10:00:00.000Z", ends_at: "2026-10-16T11:00:00.000Z" });
});

test("keyboard can reach morning free time when the rest of the day is occupied", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent({ starts_at: "2026-10-16T10:00:00Z", ends_at: "2026-10-17T00:00:00Z" })];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "День", exact: true }).click();
  await page.locator(".calendar-selection").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue("2026-10-16T09:45");
  await expect(page.getByLabel("Окончание", { exact: true })).toHaveValue("2026-10-16T10:00");
  expect(state.writes).toEqual([]);
});
