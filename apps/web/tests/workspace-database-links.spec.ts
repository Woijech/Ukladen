import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";

const databaseId = "11111111-1111-4111-8111-111111111111";
const viewId = "22222222-2222-4222-8222-222222222222";
const propertyId = "33333333-3333-4333-8333-333333333333";
const recordId = "44444444-4444-4444-8444-444444444444";
const base = `/api/v1/workspace/databases/${databaseId}`;
const href = `/workspace?section=databases&database=${databaseId}`;

async function mockDatabase(page: Page) {
  const workspace = await mockWorkspace(page);
  const state = {
    databaseCode: 200, viewCode: 200, viewDatabase: databaseId,
    requests: [] as string[],
    property: { id: propertyId, name: "Описание", kind: "text", version: 1, options: [], trashed_at: null },
    record: {
      record: { id: recordId, version: 1, values: { [propertyId]: "Сохранённое поле" }, trashed_at: null },
      page: { id: recordId, title: "Страница записи", version: 1, parent_id: null, updated_at: "2026-10-16T12:00:00Z", trashed_at: null },
      schema_version: 1,
    },
    view: { id: viewId, database_id: databaseId, name: "Дальний календарь", layout: "calendar", calendar_layout: "week", date_property_id: propertyId, version: 1 },
  };
  await page.route("**/api/v1/workspace/databases**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    state.requests.push(path);
    if (path === "/api/v1/workspace/databases" || path === `${base}/views`)
      return route.fulfill({ json: { items: [], limit: 50, offset: 0 } });
    if (path === base) return route.fulfill({ status: state.databaseCode, json: { id: databaseId, name: "База вне списка", version: 1, schema_version: 1, color: null, trashed_at: null } });
    if (path === `${base}/views/${viewId}`) return route.fulfill({ status: state.viewCode, json: { ...state.view, database_id: state.viewDatabase } });
    if (path === `${base}/properties`) return route.fulfill({ json: { items: [state.property], schema_version: 1 } });
    if (path.endsWith("/entries")) return route.fulfill({ json: { entries: [] } });
    if (path.endsWith(`/records/${recordId}`)) return route.fulfill({ json: state.record });
    if (path.endsWith("/records")) return route.fulfill({ json: { items: [state.record], properties: [state.property], schema_version: 1, total: 1, limit: 50, offset: 0 } });
    return route.fulfill({ status: 404, json: {} });
  });
  return { state, workspace };
}

test("database and calendar view links load independently of paginated lists and restore dates", async ({ page }) => {
  const { state, workspace } = await mockDatabase(page);
  await page.goto(`${href}&view=${viewId}&date=2026-11-13`);
  await expect(page.getByRole("heading", { name: "База вне списка", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "▦ Дальний календарь", exact: true })).toHaveClass(/selected/);
  await expect(page.locator(".database-calendar")).toBeVisible();
  await page.getByLabel("Следующая неделя базы", { exact: true }).click();
  await expect(page).toHaveURL(/date=2026-11-20/);
  await page.reload();
  await expect(page.locator(".panel-toolbar").filter({ hasText: "2026-11-16 — 2026-11-22" })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/date=2026-11-13/);
  await page.goForward();
  await expect(page).toHaveURL(/date=2026-11-20/);
  await page.getByRole("button", { name: "▦ Все записи", exact: true }).click();
  await expect(page).toHaveURL(href);
  await page.goBack();
  await expect(page.locator(".database-calendar")).toBeVisible();
  expect(state.requests).toContain(`${base}/views/${viewId}`);
  expect(workspace.writes).toEqual([]);
});

for (const reason of ["missing database", "missing view", "mismatched database"]) {
  test(`${reason} has a safe return to the list without showing foreign content`, async ({ page }) => {
    const { state } = await mockDatabase(page);
    if (reason === "missing database") state.databaseCode = 404;
    else if (reason === "missing view") state.viewCode = 404;
    else state.viewDatabase = recordId;
    await page.goto(`${href}&view=${viewId}`);
    await expect(page.getByText("Объект недоступен", { exact: true })).toBeVisible();
    await expect(page.locator(".database-calendar")).not.toBeVisible();
    await page.getByRole("button", { name: "К списку", exact: true }).click();
    await expect(page).toHaveURL(/\/workspace\?section=databases$/);
  });
}

test("a transient view read failure keeps its link and retries the direct read", async ({ page }) => {
  const { state } = await mockDatabase(page);
  state.viewCode = 503;
  await page.goto(`${href}&view=${viewId}&date=2026-11-13`);
  await expect(page.getByRole("button", { name: "Повторить", exact: true })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`view=${viewId}&date=2026-11-13`));
  state.viewCode = 200;
  await page.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(page.locator(".database-calendar")).toBeVisible();
});

test("history retains a dirty database cell on refusal and discards it only on approval", async ({ page }) => {
  await mockDatabase(page);
  await page.goto(`${href}&view=${viewId}&date=2026-11-13`);
  await page.getByRole("button", { name: "▦ Все записи", exact: true }).click();
  await page.getByRole("button", { name: "Изменить Описание: Страница записи", exact: true }).click();
  await page.getByLabel("Описание", { exact: true }).fill("Не потерять поле");
  page.once("dialog", dialog => dialog.dismiss());
  await page.goBack();
  await expect(page).toHaveURL(href);
  await expect(page.getByLabel("Описание", { exact: true })).toHaveValue("Не потерять поле");
  page.once("dialog", dialog => dialog.accept());
  await page.goBack();
  await expect(page.locator(".database-calendar")).toBeVisible();
});

test("history cannot leave a database cell while a versioned update is pending", async ({ page }) => {
  await mockDatabase(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  await page.route(`**${base}/records/${recordId}`, async route => {
    if (route.request().method() === "PATCH") await gate;
    await route.fallback();
  });
  await page.goto(`${href}&view=${viewId}&date=2026-11-13`);
  await page.getByRole("button", { name: "▦ Все записи", exact: true }).click();
  await page.getByRole("button", { name: "Изменить Описание: Страница записи", exact: true }).click();
  await page.getByLabel("Описание", { exact: true }).fill("Записываем поле");
  await page.getByRole("button", { name: "Сохранить запись", exact: true }).click();
  await expect(page.getByLabel("Описание", { exact: true })).toBeDisabled();
  await page.goBack();
  await expect(page).toHaveURL(href);
  release();
  await expect(page.locator(".cell-editor")).not.toBeVisible();
  await page.goBack();
  await expect(page.locator(".database-calendar")).toBeVisible();
});
