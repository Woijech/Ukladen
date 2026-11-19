import { expect, test } from "@playwright/test";
import { calendarEvent, mockWorkspace } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

const id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
for (const width of [390, 1440]) {
  test(`personal calendars persist visibility, assign events and delete safely at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const workspace = await mockWorkspace(page);
    workspace.timezone = "Europe/Minsk";
    workspace.events = [
      calendarEvent({ title: "Lecture", source: "official", id: "official:lecture", source_event_id: "lecture", lesson_type: "ЛК" }),
      calendarEvent({ title: "Lab", source: "official", id: "official:lab", source_event_id: "lab", lesson_type: "ЛР" }),
      calendarEvent({ title: "Unknown", source: "official", id: "official:other", source_event_id: "other", lesson_type: "unknown" }),
    ];
    let calendars: { id: string; name: string; color: string; version: number }[] = [];
    let visibility = { version: 0, default_visible: true, hidden_calendar_ids: [] as string[], hidden_lesson_types: [] as string[] };
    await page.route("**/api/v1/calendar/calendars**", async route => {
      const request = route.request(), method = request.method();
      if (method === "GET") return route.fulfill({ json: { items: calendars } });
      expect(request.headers()["x-csrf-token"]).toBe("c".repeat(43));
      if (method === "DELETE") {
        expect(request.postDataJSON().expected_version).toBe(calendars[0].version);
        calendars = [];
        workspace.events = workspace.events.map(event => ({ ...event, calendar_id: null }));
        return route.fulfill({ status: 204 });
      }
      calendars = [{ ...request.postDataJSON(), id, version: method === "POST" ? 1 : calendars[0].version + 1 }];
      return route.fulfill({ status: method === "POST" ? 201 : 200, json: calendars[0] });
    });
    await page.route("**/api/v1/calendar/visibility", async route => {
      if (route.request().method() === "PUT") visibility = { ...route.request().postDataJSON(), version: visibility.version + 1 };
      return route.fulfill({ json: visibility });
    });
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Неделя", exact: true }).click();
    if (width < 1100) await page.getByRole("button", { name: "Календари", exact: true }).click();
    await page.getByRole("button", { name: "Добавить календарь", exact: true }).click();
    const editor = page.getByRole("dialog", { name: "Новый календарь", exact: true });
    await editor.getByLabel("Название", { exact: true }).fill("Тренировки");
    await editor.getByLabel("Цвет", { exact: true }).fill("#246566");
    await editor.getByRole("button", { name: "Сохранить календарь", exact: true }).click();
    await expect(editor).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "Тренировки", exact: true })).toBeChecked();
    await page.getByRole("checkbox", { name: "Лекции", exact: true }).uncheck();
    await expect.poll(() => visibility.hidden_lesson_types).toEqual(["ЛК"]);
    if (width < 1100) await page.getByRole("button", { name: "Закрыть панель календарей" }).click();
    await expect(page.locator(".event-card").filter({ hasText: "Lecture" })).toHaveCount(0);
    await expect(page.locator(".event-card").filter({ hasText: "Lab" })).toHaveCount(1);
    await page.getByRole("button", { name: "Новое событие", exact: true }).click();
    await page.getByLabel("Название", { exact: true }).fill("Бег");
    await page.getByRole("dialog", { name: "Новое событие", exact: true }).getByLabel("Календарь", { exact: true }).selectOption(id);
    await page.getByRole("button", { name: "Добавить событие", exact: true }).click();
    await expect(page.locator(".event-modal")).toHaveCount(0);
    expect(workspace.writes.find(write => write.path === "/api/v1/calendar/personal-events")?.body?.calendar_id).toBe(id);
    await page.locator(".event-card-open").filter({ hasText: "Бег" }).click();
    await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
    await page.locator(".event-modal").getByLabel("Календарь", { exact: true }).selectOption("");
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(page.locator(".event-modal")).toHaveCount(0);
    expect(workspace.writes.filter(write => write.method === "PATCH").at(-1)?.body?.calendar_id).toBeNull();
    await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
    await page.locator(".event-modal").getByLabel("Календарь", { exact: true }).selectOption(id);
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(page.locator(".event-modal")).toHaveCount(0);
    expect(workspace.writes.filter(write => write.method === "PATCH").at(-1)?.body?.calendar_id).toBe(id);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
    if (width < 1100) await page.getByRole("button", { name: "Календари", exact: true }).click();
    await expect(page.getByRole("checkbox", { name: "Лекции", exact: true })).not.toBeChecked();
    await page.getByLabel("Действия календаря Тренировки").click();
    await page.getByRole("button", { name: "Название и цвет", exact: true }).click();
    await page.getByRole("dialog", { name: "Настройки календаря" }).getByLabel("Название", { exact: true }).fill("Пробежки");
    await page.getByRole("button", { name: "Сохранить календарь", exact: true }).click();
    await page.getByLabel("Действия календаря Пробежки").click();
    await page.keyboard.press("Escape");
    await expect(page.getByLabel("Действия календаря Пробежки")).toBeFocused();
    await expect(page.locator("#calendar-context")).toBeVisible();
    await page.getByLabel("Действия календаря Пробежки").click();
    await page.getByRole("button", { name: "Удалить календарь", exact: true }).click();
    const deletion = page.getByRole("dialog", { name: "Удалить календарь", exact: true });
    await expect(deletion).toContainText("События сохранятся");
    await deletion.getByRole("button", { name: "Удалить календарь", exact: true }).click();
    await expect(page.getByRole("checkbox", { name: "Пробежки", exact: true })).toHaveCount(0);
    expect(workspace.events.some(event => event.title === "Бег")).toBe(true);
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
      await page.screenshot({ path: info.outputPath(`calendars-${theme}-${width}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
    }
  });
}

test("Escape closes only the nested picker, protects event drafts and then closes event details", async ({ page }) => {
  const workspace = await mockWorkspace(page);
  workspace.events = [calendarEvent()];
  await page.goto("/workspace");
  await page.locator(".event-card-open").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Unsaved draft");
  await page.getByRole("button", { name: "Выбрать начало", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "Дата и время события", exact: true })).toHaveCount(0);
  await expect(page.locator(".event-modal")).toBeVisible();
  await expect(page.getByRole("button", { name: "Выбрать начало", exact: true })).toBeFocused();
  page.once("dialog", dialog => dialog.dismiss());
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Название", { exact: true })).toHaveValue("Unsaved draft");
  page.once("dialog", dialog => dialog.accept());
  await page.keyboard.press("Escape");
  await expect(page.locator(".event-modal")).toHaveCount(0);
  await page.getByRole("button", { name: /К календарю/ }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("article", { name: "Страница события" })).toHaveCount(0);
  expect(workspace.writes).toEqual([]);
});

test("a calendar directory outage retains the event assignment until retry", async ({ page }) => {
  const workspace = await mockWorkspace(page);
  workspace.events = [calendarEvent({ calendar_id: id })];
  let unavailable = true;
  await page.route("**/api/v1/calendar/calendars", route => unavailable
    ? route.fulfill({ status: 503, json: {} })
    : route.fulfill({ json: { items: [{ id, name: "Работа", color: "#246566", version: 1 }] } }));
  await page.goto("/workspace");
  await page.locator(".event-card-open").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  const select = page.locator(".event-modal").getByLabel("Календарь", { exact: true });
  await expect(select).toHaveValue(id);
  await expect(select).toBeDisabled();
  await page.clock.runFor(20000);
  await expect(page.locator(".event-modal").getByRole("alert")).toContainText("Не удалось загрузить календари");
  unavailable = false;
  await page.getByRole("button", { name: "Повторить загрузку", exact: true }).click();
  await expect(select).toBeEnabled();
  await expect(select).toHaveValue(id);
  await expect(select).toContainText("Работа");
  expect(workspace.writes).toEqual([]);
});
