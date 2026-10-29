import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace, navigateSection, task } from "./workspace-fixtures";
import type { WorkPlan, WorkSession } from "../src/app/workspace/task-planning";

async function planning(page: Page) {
  const workspace = await mockWorkspace(page);
  workspace.tasks = [task({ remaining_minutes: 90 })];
  const state = { workspace, writes: [] as { path: string; body: Record<string, unknown> }[], preferences: { version: 0, windows: [] as { weekday: number; start_minute: number; end_minute: number }[], session_minutes: 45, break_minutes: 15 }, sessions: [] as WorkSession[], stale: false, conflict: false, verified: true, plan: null as WorkPlan | null };
  await page.route("**/api/v1/tasks/planning/**", async route => {
    const path = new URL(route.request().url()).pathname, method = route.request().method();
    const body = method === "GET" ? {} : route.request().postDataJSON();
    if (method !== "GET") { expect(route.request().headers()["x-csrf-token"]).toBe("c".repeat(43)); state.writes.push({ path, body }); }
    if (path.endsWith("/preferences")) {
      if (method === "PUT") { expect(body.expected_version).toBe(state.preferences.version); state.preferences = { ...body, version: state.preferences.version + 1 }; }
      return route.fulfill({ json: state.preferences });
    }
    if (path.endsWith("/calendar")) return route.fulfill({ json: { sessions: state.sessions.filter(item => !item.cancelled).map(item => ({ ...item, source_event_id: item.id, title: "Prepare report" })), deadlines: [] } });
    if (path.endsWith("/sessions/check")) return route.fulfill({ json: { snapshot: "a".repeat(64), occupied: state.conflict ? [{}] : [], verified: state.verified } });
    if (path.endsWith("/sessions")) {
      if (method === "POST") { expect(body.snapshot).toBe("a".repeat(64)); if (state.conflict) expect(body.acknowledge_conflicts).toBe(true); state.sessions.push({ id: "session-1", task_id: body.task_id, starts_at: body.starts_at, ends_at: body.ends_at, pinned: body.pinned, cancelled: false, version: 1 }); return route.fulfill({ status: 201, json: state.sessions[0] }); }
      return route.fulfill({ json: state.sessions });
    }
    if (method === "PATCH") {
      const current = state.sessions[0]; expect(body.expected_version).toBe(current.version); Object.assign(current, body.pinned === undefined ? { cancelled: body.cancel } : { pinned: body.pinned }, { version: current.version + 1 });
      return route.fulfill({ json: current });
    }
    if (path.endsWith("/plans")) {
      state.plan = { id: "plan-1", digest: "b".repeat(64), timezone: "UTC", verified: state.verified, status: "pending", expires_at: "2026-10-17T12:00:00Z", sessions: [{ task_id: workspace.tasks[0].id, starts_at: "2026-10-17T09:00:00Z", ends_at: "2026-10-17T09:45:00Z", retained_id: null }], cancelled_sessions: [], unplaced: [{ task_id: workspace.tasks[0].id, minutes: 45, reason: "not_placed_in_allowed_windows" }], warnings: state.verified ? [] : ["schedule_coverage_unknown"] };
      return route.fulfill({ json: state.plan });
    }
    if (path.endsWith("/apply")) {
      if (state.stale) return route.fulfill({ status: 409, json: {} });
      expect(body).toEqual({ digest: "b".repeat(64), accept_partial: true });
      state.plan!.status = "applied";
      return route.fulfill({ json: state.plan });
    }
    throw new Error(`Unexpected planning request ${path}`);
  });
  await page.goto("/workspace"); await expect(page.locator(".content-wrap")).toBeVisible(); await navigateSection(page, "Задачи");
  await page.getByRole("button", { name: "Планирование", exact: true }).click();
  return state;
}

async function prepare(page: Page) {
  const dialog = page.getByRole("dialog", { name: "Планирование задач" });
  await dialog.getByRole("checkbox", { name: /Prepare report/ }).check();
  await dialog.getByLabel("Планировать с", { exact: true }).fill("2026-10-17T09:00");
  await dialog.getByLabel("Планировать до", { exact: true }).fill("2026-10-17T11:00");
  await dialog.getByLabel("Разрешить весь этот интервал только для данного запроса").check();
  await dialog.getByRole("button", { name: "Подготовить план", exact: true }).click();
  return dialog;
}

test("weekly preferences, explicit partial confirmation and exact digest", async ({ page }) => {
  const state = await planning(page);
  const dialog = page.getByRole("dialog", { name: "Планирование задач" });
  await dialog.getByText("Часы работы и перерывы", { exact: true }).click();
  await dialog.getByRole("button", { name: "Добавить окно" }).click();
  await dialog.getByLabel("Сессия, мин").fill("30");
  await dialog.getByRole("button", { name: "Сохранить часы работы" }).click();
  await expect(dialog.getByText("Сохранённые настройки: версия 1", { exact: true })).toBeVisible();
  expect(state.preferences).toMatchObject({ version: 1, session_minutes: 30, break_minutes: 15, windows: [{ weekday: 0, start_minute: 540, end_minute: 1020 }] });
  await prepare(page);
  const confirm = dialog.getByRole("button", { name: "Подтвердить план целиком" });
  await expect(confirm).toBeDisabled();
  await expect(dialog.getByRole("region", { name: "Просмотр плана" })).toContainText("45 мин");
  await dialog.getByLabel("Подтверждаю частичный план и указанный остаток").check();
  await confirm.click();
  await expect(dialog.getByText("План применён.", { exact: true }).first()).toBeVisible();
  expect(state.writes.find(item => item.path.endsWith("/plans"))?.body).toMatchObject({ task_ids: [state.workspace.tasks[0].id], windows: [{ starts_at: "2026-10-17T09:00:00.000Z", ends_at: "2026-10-17T11:00:00.000Z" }] });
  expect(state.workspace.tasks[0].remaining_minutes).toBe(90);
});

test("stale plans clear the preview and manual conflicts require acknowledgement", async ({ page }) => {
  const state = await planning(page);
  const dialog = await prepare(page);
  state.stale = true;
  await dialog.getByLabel("Подтверждаю частичный план и указанный остаток").check();
  await dialog.getByRole("button", { name: "Подтвердить план целиком" }).click();
  await expect(dialog.getByRole("alert")).toContainText("Ничего не применено");
  await expect(dialog.getByRole("region", { name: "Просмотр плана" })).toHaveCount(0);
  state.conflict = true;
  await dialog.getByRole("button", { name: "Добавить сессию вручную" }).click();
  await dialog.getByLabel("Начало сессии", { exact: true }).fill("2026-10-17T09:00");
  await dialog.getByLabel("Конец сессии", { exact: true }).fill("2026-10-17T09:45");
  await dialog.getByRole("button", { name: "Проверить занятость" }).click();
  await expect(dialog.getByRole("button", { name: "Подтвердить сессию" })).toBeDisabled();
  await dialog.getByLabel("Разместить вручную с указанными ограничениями").check();
  await dialog.getByRole("button", { name: "Подтвердить сессию" }).click();
  await expect(dialog.getByRole("button", { name: "Закрепить", exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Закрепить", exact: true }).click();
  await expect(dialog.getByRole("button", { name: "Открепить", exact: true })).toBeVisible();
  expect(state.sessions[0].pinned).toBe(true);
  await dialog.getByRole("button", { name: "Отменить сессию", exact: true }).click();
  await expect(dialog.getByText(/· отменена/)).toBeVisible();
  expect(state.sessions[0].cancelled).toBe(true);
  expect(state.workspace.tasks[0].remaining_minutes).toBe(90);
});

test("unknown expected schedule coverage blocks even partial application", async ({ page }) => {
  const state = await planning(page); state.verified = false;
  const dialog = await prepare(page);
  await expect(dialog.getByText("Условный план. Применение недоступно.")).toBeVisible();
  await dialog.getByLabel("Подтверждаю частичный план и указанный остаток").check();
  await expect(dialog.getByRole("button", { name: "Подтвердить план целиком" })).toBeDisabled();
  expect(state.writes.some(item => item.path.endsWith("/apply"))).toBe(false);
});

test("task dependencies use current versions and page unlinking preserves endpoints", async ({ page }) => {
  const workspace = await mockWorkspace(page);
  const first = task({ remaining_minutes: 90 }), predecessor = task({ id: "22222222-2222-4222-8222-222222222222", title: "Read sources" });
  workspace.tasks = [first, predecessor];
  let linkedDependency = false, linkedPage = false;
  const savedPage = { id: "33333333-3333-4333-8333-333333333333", title: "Assignment" };
  const versions: number[] = [];
  await page.route("**/api/v1/tasks/*/dependencies**", async route => {
    const method = route.request().method();
    if (method !== "GET") { const body = route.request().postDataJSON(); expect(body.expected_version).toBe(first.version); versions.push(body.expected_version); first.version++; linkedDependency = method === "PUT"; }
    return route.fulfill({ json: method === "GET" ? { items: linkedDependency ? [predecessor] : [], has_unresolved_dependencies: linkedDependency } : first });
  });
  await page.route("**/api/v1/notes/pages?**", route => route.fulfill({ json: { items: [savedPage] } }));
  await page.route("**/api/v1/relations/tasks/**", async route => {
    const method = route.request().method();
    if (method !== "GET") linkedPage = method === "PUT";
    return route.fulfill({ status: method === "DELETE" ? 204 : 200, ...(method === "DELETE" ? {} : { json: method === "GET" ? { items: linkedPage ? [savedPage] : [] } : savedPage }) });
  });
  await page.goto("/workspace"); await expect(page.locator(".content-wrap")).toBeVisible(); await navigateSection(page, "Задачи");
  await page.getByRole("region", { name: "Список задач" }).getByRole("button", { name: /Prepare report/ }).click();
  await page.getByRole("button", { name: "Добавить предшественника" }).click();
  await page.getByRole("dialog", { name: "Выбрать предшественника" }).getByRole("button", { name: "Read sources", exact: true }).click();
  await expect(page.getByText("Есть незавершённые или недоступные предшественники.")).toBeVisible();
  await page.getByRole("button", { name: "Убрать зависимость" }).click();
  await expect(page.getByRole("button", { name: "Убрать зависимость" })).toHaveCount(0);
  expect(versions).toEqual([1, 2]);
  await page.getByRole("button", { name: "Связать страницу" }).click();
  await page.getByRole("dialog", { name: "Выбрать страницу" }).getByRole("button", { name: "Assignment", exact: true }).click();
  await expect(page.getByRole("region", { name: "Связи задачи" }).getByRole("button", { name: "Assignment", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Убрать связь", exact: true }).click();
  await expect(page.getByRole("button", { name: "Убрать связь", exact: true })).toHaveCount(0);
  expect(linkedPage).toBe(false);
  expect(workspace.tasks).toHaveLength(2);
  expect(savedPage.title).toBe("Assignment");
});

test("task work sessions are visible in the calendar and open their controls", async ({ page }) => {
  const state = await planning(page);
  state.sessions = [{ id: "calendar-session", task_id: state.workspace.tasks[0].id, starts_at: "2026-10-17T09:00:00Z", ends_at: "2026-10-17T09:45:00Z", pinned: true, cancelled: false, version: 1 }];
  await page.getByRole("dialog", { name: "Планирование задач" }).getByRole("button", { name: "Закрыть", exact: true }).click();
  await page.reload();
  await navigateSection(page, "Календарь");
  const calendar = page.getByRole("region", { name: "Рабочие сессии задач" });
  await expect(calendar).toContainText("закреплена");
  await calendar.getByRole("button", { name: "Открыть сессию задачи" }).click();
  await expect(page.getByRole("dialog", { name: "Планирование задач" }).getByRole("button", { name: "Открепить", exact: true })).toBeVisible();
});

test("planning controls fit a mobile dialog", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await planning(page);
  const dialog = page.getByRole("dialog", { name: "Планирование задач" });
  await dialog.getByText("Часы работы и перерывы", { exact: true }).click();
  await dialog.getByRole("button", { name: "Добавить окно" }).click();
  expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  await page.screenshot({ path: test.info().outputPath("task-planning-mobile.png"), fullPage: true });
});
