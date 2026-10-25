import { test, expect } from "@playwright/test";
import { login, mockWorkspace, task } from "./workspace-fixtures";

test.use({ timezoneId: "UTC" });

test("tasks can be created, edited, filtered and nested without an academic group", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Задачи", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Задачи" })).toBeVisible();
  await expect(page.getByText("Пока нет задач. Создайте первую.")).toBeVisible();

  await page.getByRole("button", { name: "Новая задача" }).click();
  await page.getByLabel("Название").fill("Prepare report");
  await page.getByLabel("Описание").fill("Read the assignment");
  await page.getByRole("dialog").getByLabel("Приоритет", { exact: true }).selectOption("high");
  await page.getByLabel("Срок").fill("2026-10-30T18:00");
  await page.getByLabel("Оценка, минуты").fill("90");
  await page.getByRole("button", { name: "Создать задачу" }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("Prepare report");
  expect(state.writes.find(write => write.path === "/api/v1/tasks" && write.method === "POST")?.body).toMatchObject({ title: "Prepare report", priority: "high", deadline_at: "2026-10-30T18:00:00.000Z", estimated_minutes: 90, parent_id: null });

  await page.getByRole("button", { name: "Изменить" }).click();
  await page.getByRole("dialog").getByLabel("Статус", { exact: true }).selectOption("in_progress");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("В работе");
  expect(state.writes.find(write => write.method === "PATCH")?.body).toMatchObject({ expected_version: 1, status: "in_progress" });

  await page.getByRole("button", { name: "+ Подзадача" }).click();
  await page.getByLabel("Название").fill("Write outline");
  await page.getByRole("button", { name: "Создать задачу" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(state.tasks[1].parent_id).toBe(state.tasks[0].id);
  await page.getByRole("region", { name: "Детали задачи" }).getByRole("button", { name: "Prepare report" }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("Write outline");

  await page.getByRole("region", { name: "Список задач" }).getByLabel("Статус").selectOption("todo");
  await expect(page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Write outline/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Prepare report/ })).toHaveCount(0);
});

test("version and hierarchy conflicts are visible and a draft is not silently overwritten", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task()];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Задачи", exact: true }).click();
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Prepare report/ }).click();
  await page.getByRole("button", { name: "Изменить" }).click();
  await page.getByLabel("Название").fill("My local draft");
  state.tasks[0].version = 2;
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("изменилась в другой вкладке");
  await expect(page.getByLabel("Название")).toHaveValue("My local draft");
  await page.getByRole("button", { name: "Загрузить актуальную версию" }).click();
  await expect(page.getByLabel("Название")).toHaveValue("Prepare report");
  await page.getByLabel("Название").fill("Updated report");
  state.taskHierarchyConflictOnce = true;
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("иерархию или статус");
  await expect(page.getByLabel("Название")).toHaveValue("Updated report");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("Updated report");
});

test("moving a subtask and switching accounts discard private task state", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.tasks = [task(), task({ id: "22222222-2222-4222-8222-222222222222", title: "Child", parent_id: "11111111-1111-4111-8111-111111111111" })];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Задачи", exact: true }).click();
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Child/ }).click();
  await page.getByRole("button", { name: "Перенести" }).click();
  await page.getByRole("button", { name: /Без родителя/ }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).not.toContainText("Подзадача:");
  expect(state.tasks[1].parent_id).toBeNull();
  await page.locator(".account-button").click();
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  state.userId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  state.tasks = [];
  await login(page);
  await page.getByRole("button", { name: "Пока без группы" }).click();
  await page.getByRole("button", { name: "Задачи", exact: true }).click();
  await expect(page.getByText("Пока нет задач. Создайте первую.")).toBeVisible();
  await expect(page.getByText("Child")).toHaveCount(0);
});

test("mobile navigation exposes tasks", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockWorkspace(page);
  await page.goto("/workspace");
  await page.getByRole("navigation", { name: "Разделы пространства" }).getByRole("button", { name: "Задачи" }).click();
  await expect(page.getByRole("heading", { name: "Задачи" })).toBeVisible();
});

test("trash moves an active branch and restores only its batch root", async ({ page }) => {
  const state = await mockWorkspace(page);
  const root = task();
  const child = task({ id: "22222222-2222-4222-8222-222222222222", title: "Child", parent_id: root.id });
  const grandchild = task({ id: "33333333-3333-4333-8333-333333333333", title: "Grandchild", parent_id: child.id, trashed_at: "2026-10-15T12:00:00Z", trash_batch_id: "33333333-3333-4333-8333-333333333333", version: 2 });
  state.tasks = [root, child, grandchild];
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Задачи", exact: true }).click();
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Prepare report/ }).click();
  await page.getByRole("button", { name: "В корзину" }).click();
  await expect(page.getByRole("group", { name: "Подтверждение удаления" })).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить" }).click();
  await expect(page.getByRole("button", { name: "Корзина" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("region", { name: "Детали задачи" }).getByRole("button", { name: "Восстановить ветку" })).toBeVisible();
  expect(state.tasks.map(item => item.trash_batch_id)).toEqual([root.id, root.id, grandchild.id]);
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Child/ }).click();
  await expect(page.getByRole("region", { name: "Детали задачи" })).toContainText("Восстановление доступно через корень");
  await expect(page.getByRole("region", { name: "Детали задачи" }).getByRole("button", { name: "Восстановить ветку" })).toHaveCount(0);
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Prepare report/ }).click();
  await page.getByRole("button", { name: "Восстановить ветку" }).click();
  await expect(page.getByRole("button", { name: "Активные" })).toHaveAttribute("aria-pressed", "true");
  expect(state.tasks.map(item => item.trash_batch_id)).toEqual([null, null, grandchild.id]);
  expect(state.writes.filter(write => write.path.endsWith("/trash") || write.path.endsWith("/restore")).map(write => write.body?.expected_version)).toEqual([1, 2]);
  await page.getByRole("button", { name: "Корзина" }).click();
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Grandchild/ }).click();
  await page.getByRole("button", { name: "Восстановить ветку" }).click();
  await expect(page.getByRole("button", { name: "Активные" })).toHaveAttribute("aria-pressed", "true");
  expect(state.tasks.map(item => item.trash_batch_id)).toEqual([null, null, null]);
});
