import { expect, test } from "@playwright/test";
import { mockWorkspace, task } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

async function setup(page: import("@playwright/test").Page) {
  const state = await mockWorkspace(page);
  state.tasks = [task(), task({ id: "22222222-2222-4222-8222-222222222222", title: "Read sources", priority: "urgent", deadline_at: "2026-10-17T09:37:00Z" })];
  await page.goto("/workspace?section=tasks");
  await expect(page.locator(".task-line")).toHaveCount(2);
  return state;
}
const row = (page: import("@playwright/test").Page) => page.locator(".task-line").filter({ hasText: "Prepare report" });

test("row status and priority change without opening a full form and Undo is versioned", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Изменить приоритет", exact: true }).click();
  await page.getByRole("dialog", { name: "Приоритет задачи" }).getByRole("button", { name: "Высокий", exact: false }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toEqual({ expected_version: 1, priority: "high" });
  await expect(page.locator(".task-detail")).toHaveCount(0);
  await page.getByRole("button", { name: "Отменить изменение", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1].body).toEqual({ expected_version: 2, priority: "normal" });
  await row(page).getByRole("button", { name: "Изменить статус", exact: true }).click();
  await page.getByRole("dialog", { name: "Статус задачи" }).getByRole("button", { name: "В работе", exact: false }).click();
  await expect.poll(() => state.tasks[0].status).toBe("in_progress");
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 3, status: "in_progress" });
});

test("inline title uses F2, Escape and Enter and keeps the draft through a conflict", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).focus();
  await page.keyboard.press("F2");
  const title = page.getByRole("textbox", { name: "Название задачи в строке" });
  await title.fill("Discard this");
  await title.press("Escape");
  expect(state.writes).toEqual([]);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).press("F2");
  await title.fill("My draft");
  state.taskConflictOnce = true;
  await title.press("Enter");
  await expect(page.locator(".task-error")).toContainText("изменилась");
  await expect(title).toHaveValue("My draft");
  await title.press("Enter");
  await expect(page.getByRole("button", { name: "My draft", exact: true })).toBeVisible();
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 1, title: "My draft" });
});

test("quick add preserves focus, supports repeated capture and transfers title to the full editor", async ({ page }) => {
  const state = await setup(page);
  const quick = page.getByRole("textbox", { name: "Быстро добавить задачу" });
  await quick.fill("First capture"); await quick.press("Enter");
  await expect(quick).toHaveValue(""); await expect(quick).toBeFocused();
  await quick.fill("More detail draft");
  await page.getByRole("button", { name: "Подробнее", exact: true }).click();
  await expect(page.getByLabel("Название", { exact: true })).toHaveValue("More detail draft");
  await page.keyboard.press("Escape");
  await expect(quick).toHaveValue("More detail draft");
  await quick.press("Escape");
  await expect(quick).toHaveValue("");
  expect(state.writes).toHaveLength(1);
});

test("display grouping and sorting apply to loaded tasks and load more uses the existing API", async ({ page }, info) => {
  const state = await mockWorkspace(page);
  state.tasks = Array.from({ length: 34 }, (_, index) => task({ id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`, title: `Task ${index}`, priority: index === 33 ? "urgent" : "normal" }));
  await page.goto("/workspace?section=tasks");
  await expect(page.locator(".task-loaded-scope")).toContainText("Загружено: 30");
  await page.locator(".task-display > summary").click();
  await page.getByLabel("Группировка", { exact: true }).selectOption("priority");
  await page.getByLabel("Сортировка", { exact: true }).selectOption("priority");
  await expect(page.locator(".task-display")).toContainText("Только загруженные задачи: 30");
  await page.locator(".task-display > summary").click();
  await page.getByRole("button", { name: "Загрузить ещё", exact: true }).click();
  await expect(page.locator(".task-loaded-scope")).toContainText("Загружено: 34");
  await expect(page.locator(".task-group").first()).toContainText("Срочный");
  await expect(page.locator(".task-group").first()).toContainText("Task 33");
  await page.locator(".task-rows-scroll").evaluate(element => { element.scrollTop = 0; });
  await expect(page.locator(".task-group").first().locator("summary")).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: info.outputPath("grouped.png"), animations: "disabled" });
  await page.getByRole("searchbox", { name: "Поиск среди загруженных задач" }).fill("Task 33");
  await expect(page.locator(".task-line")).toHaveCount(1);
  expect(state.writes).toEqual([]);
});

test("deadline editor preserves every minute and never writes on cancel", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Срок задачи", exact: true });
  await dialog.getByLabel("Точное время", { exact: true }).fill("09:37");
  await page.keyboard.press("Escape");
  expect(state.writes).toEqual([]);
  await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
  await dialog.getByLabel("Точное время", { exact: true }).fill("0937");
  await dialog.getByRole("button", { name: "Применить", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toEqual({ expected_version: 1, deadline_at: "2026-10-16T09:37:00.000Z" });
  await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
  await dialog.getByRole("button", { name: "Убрать срок", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1].body).toEqual({ expected_version: 2, deadline_at: null });
});

for (const transition of ["gap", "fold"] as const) {
  test(`deadline handles the DST ${transition} explicitly`, async ({ page }) => {
    const state = await mockWorkspace(page); state.timezone = "America/New_York";
    state.tasks = [task()];
    await page.clock.setSystemTime(new Date(transition === "gap" ? "2026-03-08T12:00:00Z" : "2026-11-01T12:00:00Z"));
    await page.goto("/workspace?section=tasks");
    await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Срок задачи", exact: true });
    await dialog.getByLabel("Точное время", { exact: true }).fill(transition === "gap" ? "02:30" : "01:30");
    await dialog.getByRole("button", { name: "Применить", exact: true }).click();
    if (transition === "gap") await expect(dialog.getByRole("alert")).toContainText("не существует");
    else {
      await expect(dialog.getByRole("alert")).toContainText("повторяется");
      await dialog.getByLabel("Смещение срока", { exact: true }).selectOption("2026-11-01T06:30:00.000Z");
      await dialog.getByRole("button", { name: "Применить", exact: true }).click();
      await expect.poll(() => state.writes.length).toBe(1);
      expect(state.writes[0].body).toEqual({ expected_version: 1, deadline_at: "2026-11-01T06:30:00.000Z" });
    }
  });
}

test("dirty inline edits guard filtering and workspace navigation", async ({ page }) => {
  await setup(page);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).press("F2");
  const title = page.getByRole("textbox", { name: "Название задачи в строке" });
  await title.fill("Keep this draft");
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator(".task-list-filters").getByLabel("Статус", { exact: true }).selectOption("done");
  await expect(title).toHaveValue("Keep this draft");
  await page.getByRole("link", { name: "Календарь", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Несохранённые изменения", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Остаться", exact: true }).click();
  await expect(title).toHaveValue("Keep this draft");
  await title.press("Escape");
  await page.getByRole("link", { name: "Календарь", exact: true }).click();
  await expect(page.locator(".calendar-card")).toBeVisible();
});

for (const width of [320, 390, 768, 834, 1440]) {
  test(`task queue, inspector and property editor fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: width <= 390 ? 844 : 1000 });
    const state = await setup(page);
    state.tasks.push(task({ id: "33333333-3333-4333-8333-333333333333", title: "Подготовить доклад по математическому анализу", status: "in_progress", priority: "high" }), task({ id: "44444444-4444-4444-8444-444444444444", title: "Разобрать замечания к лабораторной", priority: "low" }), task({ id: "55555555-5555-4555-8555-555555555555", title: "Отправить план курсовой", status: "done", priority: "normal" }));
    await page.reload();
    await expect(page.locator(".task-line")).toHaveCount(5);
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      await page.screenshot({ path: info.outputPath(`queue-${theme}.png`), animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await expect(page.getByRole("textbox", { name: "Быстро добавить задачу" })).toBeInViewport({ ratio: 1 });
      await row(page).getByRole("button", { name: "Prepare report", exact: true }).click();
      await expect(page.getByRole("region", { name: "Детали задачи" })).toBeVisible();
      if (width <= 1100) await expect(page.getByRole("region", { name: "Список задач" })).toBeHidden();
      await page.screenshot({ path: info.outputPath(`detail-${theme}.png`), animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await page.getByRole("button", { name: /К списку задач/ }).click();
      await expect(row(page).getByRole("button", { name: "Prepare report", exact: true })).toBeFocused();
      await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
      await page.screenshot({ path: info.outputPath(`deadline-${theme}.png`), animations: "disabled" });
      await checkWorkspaceVisuals(page);
      const dialog = page.getByRole("dialog", { name: "Срок задачи", exact: true });
      await expect(dialog.getByRole("button", { name: "Применить", exact: true })).toBeInViewport({ ratio: 1 });
      if (width <= 390) { const day = (await dialog.locator(".month-days button").first().boundingBox())!; expect(day.width).toBeGreaterThanOrEqual(44); expect(day.height).toBeGreaterThanOrEqual(44); }
      await page.keyboard.press("Escape");
    }
    expect(state.writes).toEqual([]);
  });
}

test("description and title-only subtasks save in context without replacing other fields", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).click();
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  await page.getByLabel("Описание задачи", { exact: true }).fill("Temporary description");
  await page.getByRole("button", { name: "Отменить описание", exact: true }).click();
  await expect(page.getByRole("button", { name: "Добавить описание", exact: true })).toBeFocused();
  expect(state.writes).toEqual([]);
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  await page.getByLabel("Описание задачи", { exact: true }).fill("Local plain text");
  await page.getByRole("button", { name: "Сохранить описание", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toEqual({ expected_version: 1, description: "Local plain text" });
  await expect(page.getByRole("button", { name: "Изменить описание", exact: true })).toBeFocused();
  const quick = page.getByRole("textbox", { name: "Быстро добавить подзадачу" });
  await quick.fill("Child from details"); await quick.press("Enter");
  await expect(quick).toHaveValue("");
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes[1].body).toEqual({ title: "Child from details", parent_id: state.tasks[0].id });
  await expect(page.getByRole("region", { name: "Детали задачи" }).getByRole("heading", { name: "Prepare report", exact: true })).toBeVisible();
});

test("stale Undo never overwrites a later task version", async ({ page }) => {
  const state = await setup(page);
  await page.getByRole("checkbox", { name: "Завершить: Prepare report", exact: true }).click();
  await expect(page.getByRole("button", { name: "Отменить изменение", exact: true })).toBeVisible();
  state.tasks[0].version = 5;
  await page.getByRole("button", { name: "Отменить изменение", exact: true }).click();
  await expect(page.locator(".task-error")).toContainText("изменилась");
  expect(state.tasks[0].status).toBe("done");
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 2, status: "todo" });
});

test("row context actions focus inline rename and scoped shortcuts leave typing alone", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Действия задачи", exact: true }).click();
  await page.getByRole("dialog", { name: "Действия задачи", exact: true }).getByRole("button", { name: /Переименовать/ }).click();
  const title = page.getByRole("textbox", { name: "Название задачи в строке" });
  await expect(title).toBeFocused();
  await title.fill("spdn typed title"); await title.press("Escape");
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).press("p");
  await expect(page.getByRole("dialog", { name: "Приоритет задачи", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(row(page).getByRole("button", { name: "Prepare report", exact: true })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("button", { name: "Read sources", exact: true })).toBeFocused();
  await page.keyboard.press("n");
  await expect(page.getByRole("textbox", { name: "Быстро добавить задачу" })).toBeFocused();
  expect(state.writes).toEqual([]);
});

test("applying an unchanged deadline preserves seconds", async ({ page }) => {
  const state = await setup(page);
  state.tasks[0].deadline_at = "2026-10-16T18:00:37Z";
  await page.reload();
  await row(page).getByRole("button", { name: "Изменить срок", exact: true }).click();
  await page.getByRole("dialog", { name: "Срок задачи", exact: true }).getByRole("button", { name: "Применить", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(1);
  expect(state.writes[0].body).toEqual({ expected_version: 1, deadline_at: "2026-10-16T18:00:37.000Z" });
});

for (const touchWidth of [390, 768]) test.describe(`task touch interactions at ${touchWidth}px`, () => {
  test.use({ viewport: { width: touchWidth, height: 844 }, hasTouch: true, isMobile: true });
  test("tap edits priority and focused details return to the same row", async ({ page }) => {
    const state = await setup(page);
    await row(page).getByRole("button", { name: "Изменить приоритет", exact: true }).tap();
    await page.getByRole("dialog", { name: "Приоритет задачи", exact: true }).getByRole("button", { name: "Высокий", exact: false }).tap();
    await expect.poll(() => state.writes.length).toBe(1);
    await row(page).getByRole("button", { name: "Prepare report", exact: true }).tap();
    await expect(page.getByRole("region", { name: "Список задач" })).toBeHidden();
    await page.getByRole("button", { name: /К списку задач/ }).tap();
    await expect(row(page).getByRole("button", { name: "Prepare report", exact: true })).toBeFocused();
  });
});

test("a conflicting property change keeps the picker open until an explicit reload", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Изменить приоритет", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Приоритет задачи", exact: true });
  state.tasks[0].version = 4;
  await dialog.getByRole("button", { name: "Высокий", exact: false }).click();
  await expect(dialog.getByRole("alert")).toContainText("изменилась");
  expect(state.tasks[0].priority).toBe("normal");
  await dialog.getByRole("button", { name: "Загрузить актуальную версию", exact: true }).click();
  await dialog.getByRole("button", { name: "Высокий", exact: false }).click();
  await expect(dialog).toHaveCount(0);
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 4, priority: "high" });
});

test("pending property edits submit once and cannot be dismissed mid-save", async ({ page }) => {
  const state = await setup(page);
  let release!: () => void;
  const wait = new Promise<void>(resolve => { release = resolve; });
  let count = 0;
  await page.route("**/api/v1/tasks/*", async route => {
    if (route.request().method() === "PATCH") { count++; await wait; }
    await route.fallback();
  });
  await row(page).getByRole("button", { name: "Изменить приоритет", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Приоритет задачи", exact: true });
  await dialog.getByRole("button", { name: "Высокий", exact: false }).click();
  await expect(dialog.getByRole("status")).toContainText("Сохраняем");
  await expect.poll(() => count).toBe(1);
  await page.keyboard.press("Enter"); await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible(); expect(count).toBe(1);
  release();
  await expect(dialog).toHaveCount(0); expect(state.writes).toHaveLength(1);
});

test("mobile Back restores list position and filter state", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await mockWorkspace(page);
  state.tasks = Array.from({ length: 29 }, (_, index) => task({ id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`, title: `Task ${index}` }));
  await page.goto("/workspace?section=tasks");
  await page.locator(".task-list-filters").getByLabel("Статус", { exact: true }).selectOption("todo");
  const target = page.getByRole("button", { name: "Task 28", exact: true });
  await target.scrollIntoViewIfNeeded();
  const before = await page.locator(".task-rows-scroll").evaluate(element => element.scrollTop);
  await target.click();
  await page.getByRole("button", { name: /К списку задач/ }).click();
  await expect(target).toBeFocused();
  expect(await page.locator(".task-rows-scroll").evaluate(element => element.scrollTop)).toBe(before);
  await expect(page.locator(".task-list-filters").getByLabel("Статус", { exact: true })).toHaveValue("todo");
  expect(state.writes).toEqual([]);
});

test("a newly captured task beyond the loaded page stays directly reachable", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = Array.from({ length: 30 }, (_, index) => task({ id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`, title: `Task ${index}` }));
  await page.goto("/workspace?section=tasks");
  const quick = page.getByRole("textbox", { name: "Быстро добавить задачу" });
  await quick.fill("New beyond page"); await quick.press("Enter");
  await expect(quick).toBeFocused();
  await page.getByRole("button", { name: "Открыть созданную задачу", exact: true }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("New beyond page");
  expect(state.writes).toHaveLength(1);
});

test("inline title keeps its starting version until an explicit reload", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).press("F2");
  const title = page.getByRole("textbox", { name: "Название задачи в строке" });
  await title.fill("Local title");
  Object.assign(state.tasks[0], { version: 3, title: "External title" });
  await title.press("Enter");
  await expect(page.getByRole("button", { name: "Загрузить актуальную версию названия", exact: true })).toBeVisible();
  await expect(title).toHaveValue("Local title");
  await title.press("Enter");
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes.map(write => write.body?.expected_version)).toEqual([1, 1]);
  expect(state.tasks[0].title).toBe("External title");
  await page.getByRole("button", { name: "Загрузить актуальную версию названия", exact: true }).click();
  await expect(title).toHaveValue("External title");
  await title.fill("Confirmed new title"); await title.press("Enter");
  await expect.poll(() => state.tasks[0].title).toBe("Confirmed new title");
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 3, title: "Confirmed new title" });
});

test("description retries never silently adopt a newly fetched version", async ({ page }) => {
  const state = await setup(page);
  await row(page).getByRole("button", { name: "Prepare report", exact: true }).click();
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  const text = page.getByLabel("Описание задачи", { exact: true });
  await text.fill("Local description");
  Object.assign(state.tasks[0], { version: 4, description: "External description" });
  await page.getByRole("button", { name: "Сохранить описание", exact: true }).click();
  await expect(page.getByRole("button", { name: "Загрузить актуальную версию описания", exact: true })).toBeVisible();
  await expect(text).toHaveValue("Local description");
  await page.getByRole("button", { name: "Сохранить описание", exact: true }).click();
  await expect.poll(() => state.writes.length).toBe(2);
  expect(state.writes.map(write => write.body?.expected_version)).toEqual([1, 1]);
  expect(state.tasks[0].description).toBe("External description");
  await page.getByRole("button", { name: "Загрузить актуальную версию описания", exact: true }).click();
  await expect(text).toHaveValue("External description");
  await text.fill("Confirmed new description");
  await page.getByRole("button", { name: "Сохранить описание", exact: true }).click();
  await expect.poll(() => state.tasks[0].description).toBe("Confirmed new description");
  expect(state.writes.at(-1)?.body).toEqual({ expected_version: 4, description: "Confirmed new description" });
});
