import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace, task } from "./workspace-fixtures";

const firstId = "11111111-1111-4111-8111-111111111111";
const secondId = "22222222-2222-4222-8222-222222222222";

async function mockNotes(page: Page) {
  const state = await mockWorkspace(page);
  const notes = [firstId, secondId].map((id, index) => ({
    id, title: `Страница ${index + 1}`, parent_id: null, version: 1,
    updated_at: "2026-10-16T12:00:00Z", trashed_at: null,
    document: { schema_version: 1, blocks: [{ id: secondId, type: "text", text: `Текст ${index + 1}`, text_format: "plain" }] },
  }));
  await page.route("**/api/v1/notes/pages**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/pages")) return route.fulfill({ json: { items: notes, limit: 200, offset: 0 } });
    const note = notes.find(item => path.includes(item.id));
    if (!note) return route.fulfill({ status: 404, json: {} });
    if (route.request().method() === "PUT") {
      note.document = route.request().postDataJSON().document;
      note.version++;
    }
    return route.fulfill({ json: note });
  });
  return { state, notes };
}

test("calendar date and explicit layout survive reload, back and forward", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace?section=calendar&date=2026-11-13&view=day");
  await page.evaluate(() => window.history.replaceState({ ...window.history.state, testMarker: "retained" }, ""));
  await expect(page.getByRole("region", { name: "Календарь на день", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Следующий день", exact: true }).click();
  await expect(page).toHaveURL(/date=2026-11-14&view=day/);
  await page.getByRole("button", { name: "Неделя", exact: true }).click();
  await expect(page).toHaveURL(/date=2026-11-14&view=week/);
  expect(await page.evaluate(() => ({ marker: window.history.state.testMarker, next: window.history.state.__NA }))).toEqual({ marker: "retained", next: true });
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

test("an explicit week layout wins over the mobile default after reload", async ({ page }) => {
  await mockWorkspace(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace?section=calendar&date=2026-11-13&view=week");
  await expect(page.getByRole("region", { name: "Календарь на неделю", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Календарь на неделю", exact: true })).toBeVisible();
});

test("an invalid task identifier is replaced before an object request is issued", async ({ page }) => {
  await mockWorkspace(page);
  const detailReads: string[] = [];
  page.on("request", request => { if (/\/api\/v1\/tasks\/[^/?]+$/.test(new URL(request.url()).pathname)) detailReads.push(request.url()); });
  await page.goto("/workspace?section=tasks&task=not-a-uuid");
  await expect(page).toHaveURL(/\/workspace\?section=tasks$/);
  await expect(page.getByRole("alert").filter({ hasText: "Некорректные параметры ссылки" })).toBeVisible();
  expect(detailReads).toEqual([]);
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

test("a task outside the loaded list opens directly and selection follows history", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task({ id: secondId, title: "Вторая задача" })];
  await page.route(`**/api/v1/tasks/${firstId}`, route => route.fulfill({ json: task({ title: "Задача вне списка" }) }));
  await page.goto(`/workspace?section=tasks&task=${firstId}`);
  await expect(page.getByRole("heading", { name: "Задача вне списка", exact: true })).toBeVisible();
  await page.locator(".task-row").filter({ hasText: "Вторая задача" }).click();
  await expect(page).toHaveURL(new RegExp(`task=${secondId}`));
  await page.reload();
  await expect(page.getByRole("heading", { name: "Вторая задача", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Задача вне списка", exact: true })).toBeVisible();
  await page.goForward();
  await expect(page.getByRole("heading", { name: "Вторая задача", exact: true })).toBeVisible();
  expect(state.writes).toEqual([]);
});

test("missing tasks can return to the list while a transient failure keeps its link for retry", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto(`/workspace?section=tasks&task=${firstId}`);
  await expect(page.getByText("Объект недоступен", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "К списку", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\?section=tasks$/);
  let failed = true;
  state.tasks = [task()];
  await page.route(`**/api/v1/tasks/${firstId}`, async route => {
    if (failed) return route.fulfill({ status: 503, json: {} });
    return route.fallback();
  });
  await page.goto(`/workspace?section=tasks&task=${firstId}`);
  await expect(page.locator(".task-detail .task-error")).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`task=${firstId}`));
  failed = false;
  await page.locator(".task-detail").getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Prepare report", exact: true })).toBeVisible();
});

test("task-to-task navigation protects unsaved descriptions and history discards only after confirmation", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task(), task({ id: secondId, title: "Следующая задача" })];
  await page.goto(`/workspace?section=tasks&task=${firstId}`);
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  await page.getByLabel("Описание задачи", { exact: true }).fill("Черновик описания");
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator(".task-row").filter({ hasText: "Следующая задача" }).click();
  await expect(page).toHaveURL(new RegExp(`task=${firstId}`));
  await expect(page.getByLabel("Описание задачи", { exact: true })).toHaveValue("Черновик описания");
  page.once("dialog", dialog => dialog.accept());
  await page.locator(".task-row").filter({ hasText: "Следующая задача" }).click();
  await expect(page).toHaveURL(new RegExp(`task=${secondId}`));
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  await page.getByLabel("Описание задачи", { exact: true }).fill("Другой черновик");
  page.once("dialog", dialog => dialog.accept());
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Prepare report", exact: true })).toBeVisible();
  await expect(page.getByLabel("Описание задачи", { exact: true })).not.toBeVisible();
  expect(state.writes).toEqual([]);
});

test("legacy page links and page-to-page history retain a rejected dirty draft", async ({ page }) => {
  await mockNotes(page);
  await page.goto(`/workspace?page=${firstId}`);
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 1");
  await page.getByRole("button", { name: "Страница 2", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`section=notes&page=${secondId}`));
  await page.getByLabel("Текст блока 1").fill("Несохранённая мысль");
  page.once("dialog", dialog => dialog.dismiss());
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`page=${secondId}`));
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Несохранённая мысль");
  page.once("dialog", dialog => dialog.accept());
  await page.goBack();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 1");
  await page.goForward();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 2");
  await page.reload();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 2");
});

test("a page outside its loaded tree opens directly and forbidden reads return safely", async ({ page }) => {
  await mockNotes(page);
  await page.route("**/api/v1/notes/pages?**", route => route.fulfill({ json: { items: [], limit: 200, offset: 0 } }));
  await page.goto(`/workspace?section=notes&page=${firstId}`);
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 1");
  await page.route(`**/api/v1/notes/pages/${firstId}`, route => route.fulfill({ status: 403, json: {} }));
  await page.reload();
  await expect(page.getByText("Объект недоступен", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Текст блока 1")).not.toBeVisible();
  await page.getByRole("button", { name: "К списку", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\?section=notes$/);
});

test("a failed ownership recheck hides a previously cached page body", async ({ page }) => {
  await mockNotes(page);
  await page.goto(`/workspace?section=notes&page=${firstId}`);
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 1");
  await page.getByRole("button", { name: "Страница 2", exact: true }).click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 2");
  await page.route(`**/api/v1/notes/pages/${firstId}`, route => route.fulfill({ status: 404, json: {} }));
  await page.clock.fastForward(31_000);
  await page.goBack();
  await expect(page.getByText("Объект недоступен", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Текст блока 1")).not.toBeVisible();
});

test("browser history cannot leave a page while its explicit save is pending", async ({ page }) => {
  const { notes } = await mockNotes(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/notes/pages/*/document", async route => { await gate; await route.fallback(); });
  await page.goto(`/workspace?section=notes&page=${firstId}`);
  await page.getByRole("button", { name: "Страница 2", exact: true }).click();
  await page.getByLabel("Текст блока 1").fill("Сохранённая мысль");
  await page.keyboard.press("Control+s");
  await expect(page.locator(".note-meta")).toContainText("Сохраняем");
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`page=${secondId}`));
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Сохранённая мысль");
  release();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  expect(notes[1].document.blocks[0].text).toBe("Сохранённая мысль");
  await page.goBack();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Текст 1");
});

test("history waits for an in-flight task description update", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task(), task({ id: secondId, title: "Следующая задача" })];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**/api/v1/tasks/${secondId}`, async route => {
    if (route.request().method() === "PATCH") await gate;
    await route.fallback();
  });
  await page.goto(`/workspace?section=tasks&task=${firstId}`);
  await page.locator(".task-row").filter({ hasText: "Следующая задача" }).click();
  await page.getByRole("button", { name: "Добавить описание", exact: true }).click();
  await page.getByLabel("Описание задачи", { exact: true }).fill("Дождаться записи");
  await page.getByRole("button", { name: "Сохранить описание", exact: true }).click();
  await expect(page.getByLabel("Описание задачи", { exact: true })).toBeDisabled();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`task=${secondId}`));
  release();
  await expect(page.locator(".task-description")).toHaveText("Дождаться записи");
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`task=${firstId}`));
  expect(state.tasks[1].description).toBe("Дождаться записи");
});

test("history cannot leave a task planning dialog while work preferences are being saved", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task()];
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/tasks/planning/preferences", async route => {
    if (route.request().method() !== "PUT") return route.fallback();
    await gate;
    await route.fulfill({ json: { ...route.request().postDataJSON(), version: 1 } });
  });
  await page.goto("/workspace?section=tasks");
  await page.locator(".task-row").filter({ hasText: "Prepare report" }).click();
  await page.getByRole("button", { name: "Сессии и планирование задачи", exact: true }).click();
  await page.getByText("Часы работы и перерывы", { exact: true }).click();
  const save = page.getByRole("button", { name: "Сохранить часы работы", exact: true });
  await save.click();
  await expect(save).toBeDisabled();
  await page.goBack();
  await expect(page).toHaveURL(new RegExp(`task=${firstId}`));
  await expect(page.getByRole("dialog", { name: "Планирование задач", exact: true })).toBeVisible();
  release();
  await expect(save).toBeEnabled();
  await page.goBack();
  await expect(page).toHaveURL(/\/workspace\?section=tasks$/);
});
