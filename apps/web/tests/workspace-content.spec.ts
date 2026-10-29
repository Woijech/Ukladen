import { randomUUID } from "node:crypto";
import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import {
  mockWorkspace,
  navigateSection as section,
  calendarEvent,
  profile,
  task,
} from "./workspace-fixtures";

const pageId = "11111111-2222-4333-8444-555555555555";
const databaseId = "22222222-2222-4333-8444-555555555555";
const propertyId = "33333333-2222-4333-8444-555555555555";
const hiddenId = "44444444-2222-4333-8444-555555555555";
const recordId = "55555555-2222-4333-8444-555555555555";
const viewId = "66666666-2222-4333-8444-555555555555";
const organizationId = "77777777-2222-4333-8444-555555555555";
const materialId = "88888888-2222-4333-8444-555555555555";
const blockId = "99999999-2222-4333-8444-555555555555";

const testWrites = new WeakMap<
  Page,
  {
    writes: {
      path: string;
      method: string;
      body: Record<string, unknown> | null;
    }[];
  }
>();
test.afterEach(async ({ page }, info) => {
  const state = testWrites.get(page);
  if (state)
    await writeFile(
      info.outputPath("api-writes.json"),
      JSON.stringify(state.writes),
    );
});

async function contentWorkspace(page: Page) {
  const workspace = await mockWorkspace(page);
  workspace.events = [
    calendarEvent({
      title: "Подготовка к семинару",
      starts_at: "2026-10-16T14:00:00Z",
      ends_at: "2026-10-16T15:00:00Z",
    }),
    calendarEvent({
      id: "official:lesson",
      source_event_id: "aaaaaaaa-2222-4333-8444-555555555555",
      source: "official",
      title: "Математический анализ",
      starts_at: "2026-10-16T08:30:00Z",
      ends_at: "2026-10-16T09:55:00Z",
    }),
  ];
  workspace.profile = profile;
  const note = {
    id: pageId,
    parent_id: null as string | null,
    title: "Идеи для проекта",
    version: 3,
    updated_at: "2026-10-16T08:00:00Z",
    trashed_at: null as string | null,
    document: {
      schema_version: 1,
      blocks: [
        {
          id: blockId,
          type: "text",
          text: "Сохранённый текст",
          text_format: "markdown",
        },
      ],
    },
  };
  const database = {
    id: databaseId,
    name: "Учебные проекты",
    version: 3,
    schema_version: 3,
    color: null,
    trashed_at: null as string | null,
  };
  const properties: {
    id: string;
    name: string;
    kind: string;
    options: { id: string; name: string }[];
    version: number;
    trashed_at: string | null;
  }[] = [
    {
      id: propertyId,
      name: "Описание",
      kind: "text",
      options: [],
      version: 1,
      trashed_at: null,
    },
    {
      id: hiddenId,
      name: "Скрытое поле",
      kind: "checkbox",
      options: [],
      version: 1,
      trashed_at: null,
    },
  ];
  const record = {
    record: {
      id: recordId,
      version: 2,
      values: {
        [propertyId]: "Семестровая работа",
        [hiddenId]: null as boolean | null,
      },
      trashed_at: null,
    },
    page: note,
    schema_version: 3,
  };
  const organization = {
    id: organizationId,
    name: "Учёба",
    color: "#8971a9",
    version: 1,
  };
  const state = {
    note,
    pages: [note],
    conflict: false,
    failDocumentOnce: false,
    forbidden: false,
    writes: [] as {
      path: string;
      method: string;
      body: Record<string, unknown> | null;
    }[],
    materials: [] as Record<string, unknown>[],
    notifications: [
      {
        id: "notice-1",
        title: "Скоро семинар",
        starts_at: "2026-10-16T14:00:00Z",
        created_at: "2026-10-16T13:45:00Z",
        read_at: null as string | null,
      },
    ],
    members: [] as Record<string, unknown>[],
    uploadBody: "",
    uploadType: "",
    record,
    properties,
    views: [
      {
        id: viewId,
        name: "Краткий вид",
        layout: "table",
        date_property_id: null,
        calendar_layout: null,
        version: 1,
        query: { version: 1, columns: [propertyId], filters: [], sorts: [] },
      },
    ] as Record<string, unknown>[],
    entries: [] as Record<string, unknown>[],
    attachments: [] as Record<string, unknown>[],
  };
  testWrites.set(page, state);
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const ours =
      path.startsWith("/api/v1/notes/") ||
      path.startsWith("/api/v1/relations/") ||
      path.startsWith("/api/v1/workspace/") ||
      path.startsWith("/api/v1/materials") ||
      path.startsWith("/api/v1/notifications") ||
      path === "/api/v1/reminders" ||
      path === "/api/v1/search";
    if (!ours) return route.fallback();
    if (state.forbidden) return route.fulfill({ status: 401, json: {} });
    const body = request.headers()["content-type"]?.includes("json")
      ? (request.postDataJSON() as Record<string, unknown>)
      : null;
    if (method !== "GET") {
      expect(request.headers()["x-csrf-token"]).toBe("c".repeat(43));
      expect(request.headers().cookie).toContain("ukladen_csrf=");
      expect(request.headers().origin).toBe("http://127.0.0.1:3001");
      state.writes.push({ path, method, body });
    }
    const list = (items: unknown[]) =>
      route.fulfill({
        json: {
          items,
          limit: Number(url.searchParams.get("limit") ?? 50),
          offset: Number(url.searchParams.get("offset") ?? 0),
        },
      });
    if (path === "/api/v1/notes/pages") {
      if (method === "POST") {
        const created = {
          ...note,
          id: randomUUID(),
          title: String(body!.title),
          parent_id: body!.parent_id as string | null,
          version: 1,
          document: { schema_version: 1, blocks: [] },
        };
        state.pages.push(created);
        return route.fulfill({ status: 201, json: created });
      }
      const items = state.pages.filter(
        (item) =>
          (url.searchParams.get("trashed") === "true") === !!item.trashed_at,
      );
      const offset = Number(url.searchParams.get("offset") ?? 0);
      return list(
        items.slice(
          offset,
          offset + Number(url.searchParams.get("limit") ?? 50),
        ),
      );
    }
    const noteMatch = path.match(
      /^\/api\/v1\/notes\/pages\/([^/]+)(?:\/(document|trash|restore))?$/,
    );
    if (noteMatch) {
      const current = state.pages.find((item) => item.id === noteMatch[1]);
      if (!current) return route.fulfill({ status: 404, json: {} });
      if (method !== "GET") {
        if (state.conflict) return route.fulfill({ status: 409, json: {} });
        expect(body!.expected_version).toBe(current.version);
        if (noteMatch[2] === "document") {
          if (state.failDocumentOnce) {
            state.failDocumentOnce = false;
            return route.fulfill({ status: 503, json: {} });
          }
          current.document = body!.document as typeof note.document;
        } else if (noteMatch[2] === "trash" || noteMatch[2] === "restore") {
          current.trashed_at =
            noteMatch[2] === "trash" ? "2026-10-16T12:00:00Z" : null;
        } else Object.assign(current, body);
        current.version++;
      }
      return route.fulfill({
        json:
          noteMatch[2] === "document"
            ? {
                page_id: current.id,
                version: current.version,
                document: current.document,
              }
            : current,
      });
    }
    if (path === `/api/v1/relations/pages/${pageId}/materials`)
      return list(state.attachments);
    if (path === `/api/v1/relations/pages/${pageId}/materials/${materialId}`) {
      state.attachments = method === "PUT" ? [state.materials[0]] : [];
      return route.fulfill({
        status: method === "DELETE" ? 204 : 200,
        ...(method === "DELETE" ? {} : { json: state.materials[0] }),
      });
    }
    if (path.startsWith("/api/v1/relations/")) return list([]);
    if (path === "/api/v1/materials/storage")
      return route.fulfill({
        json: {
          used_bytes: 0,
          limit_bytes: 1073741824,
          max_file_bytes: 26214400,
          material_count: state.materials.length,
        },
      });
    if (path === "/api/v1/materials") return list(state.materials);
    if (
      path === "/api/v1/materials/uploads" ||
      path === "/api/v1/materials/links"
    ) {
      const material = {
        id: materialId,
        title: body!.title || body!.filename,
        kind: path.endsWith("links") ? "link" : "file",
        filename: body!.filename ?? null,
        size_bytes: body!.size_bytes ?? null,
        url: body!.url ?? null,
        status: path.endsWith("links") ? "ready" : "uploading",
        version: 1,
        error_code: null,
        trashed_at: null,
      };
      state.materials.push(material);
      return route.fulfill({ status: 201, json: material });
    }
    if (path === `/api/v1/materials/${materialId}`)
      return route.fulfill({ json: state.materials[0] });
    if (path === `/api/v1/materials/${materialId}/content`) {
      state.uploadBody = request.postData() ?? "";
      state.uploadType = request.headers()["content-type"];
      Object.assign(state.materials[0], { status: "ready", version: 2 });
      return route.fulfill({ json: state.materials[0] });
    }
    if (path === "/api/v1/search")
      return list([
        {
          id: pageId,
          source: "page",
          title: note.title,
          snippet: "Текст <script>не HTML</script>",
          version: note.version,
          kind: null,
        },
      ]);
    if (path === "/api/v1/notifications")
      return list(
        state.notifications.filter(
          (item) =>
            url.searchParams.get("unread_only") !== "true" || !item.read_at,
        ),
      );
    if (path === "/api/v1/notifications/notice-1/read") {
      state.notifications[0].read_at = "2026-10-16T12:00:00Z";
      return route.fulfill({ json: state.notifications[0] });
    }
    if (path === "/api/v1/reminders")
      return method === "GET"
        ? list([])
        : route.fulfill({ status: 201, json: { id: "reminder-1" } });
    const base = `/api/v1/workspace/databases/${databaseId}`;
    if (path === "/api/v1/workspace/databases") return list([database]);
    if (path === base) return route.fulfill({ json: database });
    if (path === `${base}/properties`)
      return route.fulfill({
        json: {
          items: properties.filter(
            (item) =>
              (url.searchParams.get("trashed") === "true") ===
              !!item.trashed_at,
          ),
          schema_version: database.schema_version,
        },
      });
    if (path === `${base}/properties/${propertyId}`) {
      expect(body!.expected_schema_version).toBe(database.schema_version);
      Object.assign(properties[0], body);
      properties[0].version++;
      database.schema_version++;
      return route.fulfill({
        json: {
          property: properties[0],
          schema_version: database.schema_version,
        },
      });
    }
    if (path === `${base}/views`) return list(state.views);
    if (path === `${base}/views/${viewId}`) {
      expect(body!.expected_version).toBe(state.views[0].version);
      expect(body!.expected_schema_version).toBe(database.schema_version);
      Object.assign(state.views[0], body);
      state.views[0].version = Number(state.views[0].version) + 1;
      return route.fulfill({ json: state.views[0] });
    }
    if (path === `${base}/views/${viewId}/entries`)
      return route.fulfill({
        json: {
          entries: state.entries,
          view: state.views[0],
          timezone: workspace.timezone,
        },
      });
    if (
      path === `${base}/records` ||
      path === `${base}/views/${viewId}/records`
    ) {
      if (method === "POST")
        return route.fulfill({ status: 201, json: record });
      return route.fulfill({
        json: {
          items: [
            path.includes("/views/")
              ? {
                  ...record,
                  record: {
                    ...record.record,
                    values: { [propertyId]: record.record.values[propertyId] },
                  },
                }
              : record,
          ],
          properties: path.includes("/views/") ? [properties[0]] : properties,
          schema_version: 3,
          total: 1,
          limit: 50,
          offset: 0,
        },
      });
    }
    if (path === `${base}/records/${recordId}`) {
      if (method === "PATCH") {
        expect(body!.expected_version).toBe(2);
        expect(body!.expected_schema_version).toBe(3);
        Object.assign(record.record.values, body!.values);
        record.record.version++;
      }
      return route.fulfill({ json: record });
    }
    if (
      path === "/api/v1/workspace/collections" ||
      path === "/api/v1/workspace/tags"
    )
      return list([organization]);
    if (path === `/api/v1/workspace/collections/${organizationId}/members`)
      return list(state.members);
    if (
      path ===
      `/api/v1/workspace/collections/${organizationId}/members/page/${pageId}`
    ) {
      state.members =
        method === "PUT"
          ? [
              {
                membership: {
                  id: "member-1",
                  target_type: "page",
                  target_id: pageId,
                },
                target: note,
              },
            ]
          : [];
      return route.fulfill({
        status: method === "DELETE" ? 204 : 200,
        ...(method === "DELETE" ? {} : { json: {} }),
      });
    }
    throw new Error(`Unexpected content request: ${method} ${path}`);
  });
  await page.goto("/workspace");
  await expect(
    page.getByRole("heading", { name: "Календарь", exact: true }),
  ).toBeVisible();
  return { workspace, state };
}


test("block editing preserves IDs and Markdown format, supports reorder, guards navigation and saves with versions", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 1").fill("Новый текст");
  await section(page, "Материалы");
  await expect(
    page.getByRole("dialog", { name: "Несохранённые изменения" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Остаться", exact: true }).click();
  await page
    .getByRole("button", { name: "Добавить блок", exact: true })
    .click();
  await page.getByLabel("Найти тип блока").fill("Чекбокс");
  await page.getByLabel("Найти тип блока").press("Enter");
  await page.getByLabel("Пункт 2", { exact: true }).fill("Проверить идею");
  await page.getByLabel("Отметить пункт 2").check();
  await page.getByLabel("Действия блока 2", { exact: true }).click();
  await page.getByRole("button", { name: "Поднять блок 2" }).click();
  await page.getByRole("button", { name: "Сохранить страницу" }).click();
  await expect(
    page.getByRole("button", { name: "Сохранить страницу" }),
  ).toBeDisabled();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  const saved = state.writes.find((item) =>
    item.path.endsWith("/document"),
  )!.body!;
  expect(saved.expected_version).toBe(3);
  const document = saved.document as {
    schema_version: number;
    blocks: Record<string, unknown>[];
  };
  expect(document.schema_version).toBe(1);
  expect(document.blocks[1]).toEqual({
    id: blockId,
    type: "text",
    text: "Новый текст",
    text_format: "markdown",
  });
  expect(document.blocks[0]).toMatchObject({
    type: "checkbox",
    text: "Проверить идею",
    checked: true,
  });
  expect(document.blocks[0].id).toMatch(/^[a-f0-9-]{36}$/);
  expect(document.blocks[0].id).not.toBe(blockId);
});

test("a conflicting note save retains the draft and explicit reload adopts the latest version", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  state.conflict = true;
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 1").fill("Несохранённая идея");
  await page.getByRole("button", { name: "Сохранить страницу" }).click();
  await expect(page.locator(".form-error")).toContainText("Данные изменились");
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Несохранённая идея",
  );
  state.note.document.blocks[0].text = "Изменение на сервере";
  state.note.version = 8;
  await page
    .getByRole("button", { name: "Загрузить последнюю версию" })
    .click();
  await page
    .getByRole("button", { name: "Загрузить версию", exact: true })
    .click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Изменение на сервере",
  );
  await expect(page.locator(".note-meta")).toContainText("v8");
});

test("note trash is confirmed and restoring refreshes the write version", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Действия страницы", { exact: true }).click();
  await page
    .locator(".note-topbar")
    .getByRole("button", { name: "В корзину", exact: true })
    .click();
  expect(state.writes).toHaveLength(0);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "В корзину", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Восстановить страницу" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Восстановить страницу" }).click();
  await expect(page.locator(".note-meta")).toContainText("v5");
  await page.getByLabel("Текст блока 1").fill("После восстановления");
  await page.getByRole("button", { name: "Сохранить страницу" }).click();
  await expect(page.locator(".note-meta")).toContainText("v6");
});

test("material upload reserves once, sends exact raw bytes and content type, then refreshes the library", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Материалы");
  await page
    .getByRole("button", { name: "Загрузить файл", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .locator('input[type="file"]')
    .setInputFiles({
      name: "конспект.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# Конспект\nТекст"),
    });
  await page.getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".resource-list")).toContainText("конспект.md");
  expect(state.uploadBody).toBe("# Конспект\nТекст");
  expect(state.uploadType).toBe("text/markdown");
  expect(
    state.writes.find((item) => item.path.endsWith("/uploads"))!.body,
  ).toMatchObject({
    filename: "конспект.md",
    size_bytes: Buffer.byteLength("# Конспект\nТекст"),
  });
});

test("unsupported files fail before reservation and bookmark creation uses the actual link endpoint", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Материалы");
  await page
    .getByRole("button", { name: "Загрузить файл", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .locator('input[type="file"]')
    .setInputFiles({
      name: "program.exe",
      mimeType: "application/octet-stream",
      buffer: Buffer.from("bad"),
    });
  await page.getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(page.locator(".form-error")).toContainText("Поддерживаются");
  expect(state.writes).toHaveLength(0);
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Ссылка", exact: false })
    .first()
    .click();
  await page.getByLabel("Название", { exact: true }).fill("Документация");
  await page.getByLabel("Адрес ссылки").fill("https://example.com/docs");
  await page
    .getByRole("button", { name: "Сохранить ссылку", exact: true })
    .click();
  await expect(page.getByRole("link", { name: "Открыть ↗" })).toHaveAttribute(
    "href",
    "https://example.com/docs",
  );
});

test("saved table edits fetch full records and patch only touched fields, preserving null and hidden values", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page.getByRole("button", { name: /Краткий вид/ }).click();
  await expect(page.locator(".records-table th")).toHaveCount(3);
  await page.getByRole("button", { name: "Изменить", exact: true }).click();
  await page.getByLabel("Описание", { exact: true }).fill("Новое описание");
  await page
    .getByRole("button", { name: "Сохранить запись", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const patch = state.writes.find((item) =>
    item.path.endsWith(`/records/${recordId}`),
  )!.body!;
  expect(patch.values).toEqual({ [propertyId]: "Новое описание" });
  expect(state.record.record.values[hiddenId]).toBeNull();
});

test("collection membership adds and removes references without deleting a page", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Коллекции и теги");
  await page.getByRole("button", { name: "Учёба", exact: true }).click();
  await page
    .getByRole("button", { name: "Добавить", exact: false })
    .first()
    .click();
  await page.getByLabel("Объект", { exact: true }).selectOption(pageId);
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Добавить", exact: true })
    .click();
  await expect(page.locator(".organization-layout")).toContainText(
    "Идеи для проекта",
  );
  await page.getByRole("button", { name: "Убрать связь", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Выбери, что здесь будет" }),
  ).toBeVisible();
  expect(state.writes.map((item) => item.method)).toEqual(["PUT", "DELETE"]);
  expect(state.note.trashed_at).toBeNull();
});

test("search treats snippets as text and opens the selected note", async ({
  page,
}) => {
  await contentWorkspace(page);
  await section(page, "Поиск");
  await page.getByLabel("Поисковый запрос").fill("идея");
  await page.getByRole("button", { name: "Найти", exact: true }).click();
  await expect(page.locator(".search-result")).toContainText(
    "<script>не HTML</script>",
  );
  await expect(page.locator(".search-result script")).toHaveCount(0);
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Сохранённый текст",
  );
});

test("notification marking uses CSRF and updates unread-only results", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Уведомления");
  await page.getByLabel("Только непрочитанные").check();
  await page.getByRole("button", { name: "Прочитано", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Всё спокойно" }),
  ).toBeVisible();
  expect(state.notifications[0].read_at).not.toBeNull();
});

test("expired sessions discard private note content and mounted editors", async ({
  page,
}) => {
  const { state, workspace } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 1").fill("Секретный черновик");
  state.forbidden = true;
  workspace.authenticated = false;
  await page.getByRole("button", { name: "Сохранить страницу" }).click();
  await expect(
    page.getByRole("heading", { name: "Войти в Ukladen" }),
  ).toBeVisible();
  await expect(page.locator(".note-editor")).toHaveCount(0);
  expect(
    await page.evaluate(() => JSON.stringify({ ...localStorage })),
  ).not.toContain("Секретный черновик");
});

for (const viewport of [
  { width: 1440, height: 1000 },
  { width: 834, height: 1112 },
  { width: 390, height: 844 },
]) {
  test(`responsive navigation, theme and modal fit at ${viewport.width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize(viewport);
    const { workspace } = await contentWorkspace(page);
    workspace.tasks = [
      task({
        title: "План проекта",
        description: "Задачи рядом с заметками и материалами",
      }),
    ];
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("calendar-light.png"),
      animations: "disabled",
    });
    await section(page, "Задачи");
    await page
      .getByRole("region", { name: "Список задач" })
      .getByRole("button", { name: /План проекта/ })
      .click();
    await expect(
      page.getByRole("region", { name: "Детали задачи" }),
    ).toContainText("Задачи рядом с заметками и материалами");
    await page.screenshot({
      path: info.outputPath("tasks-light.png"),
      animations: "disabled",
    });
    await page.getByRole("button", { name: "Новая задача" }).click();
    const taskDialog = page.getByRole("dialog", {
      name: "Новая задача",
      exact: true,
    });
    await expect(taskDialog).toBeVisible();
    const taskBox = await taskDialog.boundingBox();
    expect(taskBox!.width).toBeLessThan(viewport.width);
    expect(taskBox!.height).toBeLessThan(viewport.height);
    await page.screenshot({
      path: info.outputPath("task-dialog.png"),
      animations: "disabled",
    });
    await page.keyboard.press("Escape");
    await expect(taskDialog).toHaveCount(0);
    if (viewport.width > 900) {
      await page
        .getByRole("button", { name: "Свернуть боковую панель" })
        .click();
      await expect(page.locator(".sidebar")).toHaveCSS("width", "76px");
    }
    await section(page, "Заметки");
    await page
      .getByRole("button", { name: "Новая страница", exact: false })
      .click();
    const dialog = page.getByRole("dialog");
    await page.screenshot({
      path: info.outputPath("note-dialog.png"),
      animations: "disabled",
    });
    const box = await dialog.boundingBox();
    expect(box!.width).toBeLessThan(viewport.width);
    expect(box!.height).toBeLessThan(viewport.height);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await page
      .getByRole("button", { name: "Идеи для проекта", exact: true })
      .click();
    await expect(page.locator(".note-editor")).toBeVisible();
    await page.screenshot({
      path: info.outputPath("note-editor.png"),
      animations: "disabled",
    });
    const toggle = page.getByRole("button", { name: /Тема:/ }).first();
    await toggle.click();
    await toggle.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.locator(".calendar-card")).toBeVisible();
    await page.screenshot({
      path: info.outputPath("calendar-dark.png"),
      animations: "disabled",
    });
    await section(page, "Задачи");
    await expect(
      page.getByRole("region", { name: "Список задач" }),
    ).toContainText("План проекта");
    await expect(page.locator(".task-list-card")).toHaveCSS(
      "background-color",
      "rgb(32, 28, 38)",
    );
    await page.screenshot({
      path: info.outputPath("tasks-dark.png"),
      animations: "disabled",
    });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
  });
}

test("calendar source filters only change display, and day view keeps original event intervals", async ({
  page,
}) => {
  const { state, workspace } = await contentWorkspace(page);
  await page.getByLabel("Расписание IIS", { exact: true }).uncheck();
  await expect(page.locator(".event-card")).toHaveCount(1);
  await page.getByLabel("Личные события", { exact: true }).uncheck();
  await expect(page.locator(".empty-note")).toContainText("скрыты фильтрами");
  expect(state.writes).toHaveLength(0);
  expect(workspace.writes).toHaveLength(0);
  await page.getByLabel("Личные события", { exact: true }).check();
  await page.getByRole("button", { name: /Неделя/ }).click();
  await page.getByRole("menuitemradio", { name: /День/ }).click();
  await expect(page.locator(".day-column")).toHaveCount(1);
  await page.locator(".event-card").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue(
    "2026-10-16T14:00",
  );
});

test("event reminders bind to the original event and use the real one-shot API", async ({
  page,
}) => {
  const { state, workspace } = await contentWorkspace(page);
  await page.locator(".event-card.personal-event").click();
  await page.getByRole("button", { name: "Напомнить", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Напоминание создано");
  expect(
    state.writes.find((item) => item.path === "/api/v1/reminders")!.body,
  ).toEqual({
    source: "personal",
    event_id: workspace.events[0].source_event_id,
    minutes_before: 15,
  });
});

test("property option renaming preserves stable option IDs and checks schema versions", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  state.properties[0].kind = "select";
  state.properties[0].options = [{ id: blockId, name: "В работе" }];
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page.getByRole("button", { name: "Поля", exact: true }).click();
  await page
    .getByRole("dialog", { name: "Поля базы", exact: true })
    .locator(".property-row")
    .filter({ hasText: "Описание" })
    .getByRole("button", { name: "Изменить", exact: true })
    .click();
  await page.getByLabel("Вариант 1", { exact: true }).fill("Выполняется");
  await page
    .getByRole("button", { name: "Сохранить поле", exact: true })
    .click();
  await expect(
    page.getByRole("dialog", { name: "Изменить поле", exact: true }),
  ).toHaveCount(0);
  const patch = state.writes.find((item) =>
    item.path.endsWith(`/properties/${propertyId}`),
  )!.body!;
  expect(patch.expected_version).toBe(1);
  expect(patch.expected_schema_version).toBe(3);
  expect(patch.options).toEqual([{ id: blockId, name: "Выполняется" }]);
});

test("saved view editing keeps versions and sends typed filters, sorting and columns", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page.getByRole("button", { name: /Краткий вид/ }).click();
  await page
    .getByRole("button", { name: "Настроить вид", exact: true })
    .click();
  await page.getByRole("button", { name: "Фильтр", exact: false }).click();
  await page.getByLabel("Условие фильтра 1").selectOption("contains");
  await page.getByLabel("Значение фильтра 1", { exact: true }).fill("Семестр");
  await page.getByRole("button", { name: "Сортировка", exact: false }).click();
  await page
    .getByRole("button", { name: "Сохранить вид", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const patch = state.writes.find((item) =>
    item.path.endsWith(`/views/${viewId}`),
  )!.body!;
  expect(patch.expected_version).toBe(1);
  expect(patch.expected_schema_version).toBe(3);
  expect(patch.query).toEqual({
    version: 1,
    columns: [propertyId],
    filters: [
      { property_id: propertyId, operator: "contains", value: "Семестр" },
    ],
    sorts: [{ property_id: propertyId, direction: "asc" }],
  });
});

test("existing pages can join a database without creating a copied body", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page
    .getByRole("button", { name: "Запись", exact: false })
    .first()
    .click();
  await page
    .getByLabel("Страница записи", { exact: true })
    .selectOption("existing");
  await page
    .getByLabel("Выбрать страницу", { exact: true })
    .selectOption(pageId);
  await page
    .getByRole("button", { name: "Сохранить запись", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  const created = state.writes.find(
    (item) => item.method === "POST" && item.path.endsWith("/records"),
  )!.body!;
  expect(created.page_id).toBe(pageId);
  expect(created).not.toHaveProperty("title");
  expect(created).not.toHaveProperty("document");
});

test("month database calendars keep date-only values and exclude timed end midnight", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  Object.assign(state.views[0], {
    layout: "calendar",
    calendar_layout: "month",
    date_property_id: propertyId,
  });
  state.entries = [
    {
      id: "timed-entry",
      title: "До полуночи",
      page_id: pageId,
      record_id: recordId,
      date: {
        kind: "datetime",
        start: "2026-10-16T20:00:00Z",
        end: "2026-10-17T00:00:00Z",
      },
    },
    {
      id: "date-entry",
      title: "Дата без времени",
      page_id: pageId,
      record_id: recordId,
      date: { kind: "date", start: "2026-10-16", end: null },
    },
  ];
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page.getByRole("button", { name: /Краткий вид/ }).click();
  await expect(page.locator(".database-calendar-day")).toHaveCount(35);
  await expect(page.getByRole("button", { name: /До полуночи/ })).toHaveCount(
    1,
  );
  await expect(
    page.getByRole("button", { name: /Дата без времени/ }),
  ).toHaveCount(1);
});

test("page attachment removal preserves material and block content", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  state.materials = [
    {
      id: materialId,
      title: "Конспект",
      kind: "file",
      filename: "lecture.pdf",
      size_bytes: 1024,
      status: "ready",
      version: 1,
      trashed_at: null,
      url: null,
    },
  ];
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByRole("button", { name: /Связанные материалы/ }).click();
  await page.getByLabel("Добавить из библиотеки").selectOption(materialId);
  await expect(page.locator(".note-relations .relation-row")).toContainText(
    "Конспект",
  );
  await page.getByRole("button", { name: "Убрать связь", exact: true }).click();
  await expect(page.locator(".note-relations .relation-row")).toHaveCount(0);
  expect(state.materials).toHaveLength(1);
  expect(state.note.document.blocks[0].id).toBe(blockId);
  expect(state.writes.map((item) => item.method)).toEqual(["PUT", "DELETE"]);
});

test("profile edits refresh calendar timezone without changing event instants", async ({
  page,
}) => {
  const { state, workspace } = await contentWorkspace(page);
  const user = {
    id: workspace.userId,
    email: "test@example.com",
    display_name: null as string | null,
    timezone: "UTC",
    locale: "ru",
    avatar_url: null,
    updated_at: "2026-10-16T08:00:00Z",
  };
  await page.route("**/api/v1/users/me", async (route) => {
    if (route.request().method() === "PATCH") {
      expect(route.request().headers()["x-csrf-token"]).toBe("c".repeat(43));
      const body = route.request().postDataJSON();
      state.writes.push({ path: "/api/v1/users/me", method: "PATCH", body });
      Object.assign(user, body);
      workspace.timezone = user.timezone;
    }
    return route.fulfill({ json: user });
  });
  await section(page, "Настройки");
  await page.getByLabel("Имя", { exact: true }).fill("Александра");
  await page.getByLabel("Часовой пояс календаря").selectOption("Europe/Minsk");
  await page.getByRole("button", { name: "Сохранить профиль" }).click();
  await expect(
    page.getByRole("button", { name: "Профиль в боковой панели" }),
  ).toContainText("Александра");
  await page.locator(".event-card.personal-event").click();
  await page.getByRole("button", { name: "Изменить событие", exact: true }).click();
  await expect(page.locator(".calendar-timezone")).toContainText(
    "Europe/Minsk",
  );
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue(
    "2026-10-16T17:00",
  );
  expect(workspace.writes).toHaveLength(0);
  expect(state.writes).toEqual([
    {
      path: "/api/v1/users/me",
      method: "PATCH",
      body: { display_name: "Александра", timezone: "Europe/Minsk" },
    },
  ]);
});

test("avatar upload validates locally, sends raw bytes with CSRF and confirms deletion", async ({
  page,
}) => {
  const { workspace } = await contentWorkspace(page);
  const user = {
    id: workspace.userId,
    email: "test@example.com",
    display_name: null,
    timezone: "UTC",
    locale: "ru",
    avatar_url: null as string | null,
    updated_at: "2026-10-16T08:00:00Z",
  };
  const writes: string[] = [];
  await page.route("**/api/v1/users/me", (route) =>
    route.fulfill({ json: user }),
  );
  await page.route("**/api/v1/users/me/avatar*", async (route) => {
    const request = route.request();
    if (request.method() === "GET")
      return route.fulfill({
        contentType: "image/png",
        body: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/9N8AAAAASUVORK5CYII=",
          "base64",
        ),
      });
    expect(request.headers()["x-csrf-token"]).toBe("c".repeat(43));
    expect(request.headers().cookie).toContain("ukladen_csrf=");
    if (request.method() === "PUT") {
      expect(request.headers()["content-type"]).toBe("image/png");
      expect(request.postData()).toBe("image-bytes");
      user.avatar_url = "/api/v1/users/me/avatar";
    } else user.avatar_url = null;
    writes.push(request.method());
    return route.fulfill({ status: 204 });
  });
  await section(page, "Настройки");
  const file = page.getByLabel("Изменить фото");
  await file.setInputFiles({
    name: "invalid.svg",
    mimeType: "image/svg+xml",
    buffer: Buffer.from("<svg/>"),
  });
  await expect(page.locator(".form-error")).toContainText("до 2 МБ");
  expect(writes).toHaveLength(0);
  await file.setInputFiles({
    name: "avatar.png",
    mimeType: "image/png",
    buffer: Buffer.from("image-bytes"),
  });
  await expect(page.getByAltText("Ваш аватар")).toBeVisible();
  await page.getByRole("button", { name: "Удалить фото", exact: true }).click();
  expect(writes).toEqual(["PUT"]);
  await page
    .locator(".avatar-settings")
    .getByRole("button", { name: "Удалить", exact: true })
    .click();
  await expect(page.getByAltText("Ваш аватар")).toHaveCount(0);
  expect(writes).toEqual(["PUT", "DELETE"]);
});

test("mobile content panels and database view controls remain reachable", async ({
  page,
}, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await contentWorkspace(page);
  for (const name of [
    "Материалы",
    "Коллекции и теги",
    "Поиск",
    "Уведомления",
    "Настройки",
  ]) {
    await section(page, name);
    await expect(
      page.getByRole("heading", { level: 1, name, exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await section(page, "Материалы");
  await page
    .getByRole("button", { name: "Загрузить файл", exact: true })
    .click();
  await page.screenshot({
    path: info.outputPath("mobile-upload.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await section(page, "Базы данных");
  await page.getByRole("button", { name: /Учебные проекты/ }).click();
  await page.getByRole("button", { name: "+ Вид", exact: true }).click();
  await page.getByRole("button", { name: "Фильтр", exact: false }).click();
  const dialog = page.getByRole("dialog", { name: "Новый вид" });
  const box = await dialog.boundingBox();
  expect(box!.width).toBeLessThan(390);
  expect(box!.height).toBeLessThan(844);
  expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: info.outputPath("mobile-database-view.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await page.screenshot({
    path: info.outputPath("mobile-database-table.png"),
    animations: "disabled",
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("slash and plus share a searchable keyboard block menu and preserve IDs through conversion and deletion", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Новый блок", { exact: true }).press("/");
  const search = page.getByLabel("Найти тип блока");
  await search.fill("Заголовок");
  await search.press("ArrowUp");
  await search.press("Enter");
  await page.getByLabel("Заголовок блока 2").fill("Итоги");
  await expect(page.getByRole("heading", { level: 6 })).toBeVisible();
  const headingId = await page
    .locator(".block-heading")
    .getAttribute("data-block-id");
  await page.getByLabel("Действия блока 2", { exact: true }).click();
  await page.getByLabel("Тип блока 2", { exact: true }).selectOption("text");
  await expect(page.getByLabel("Текст блока 2")).toHaveValue("Итоги");
  await page.getByLabel("Действия блока 2", { exact: true }).press("Escape");
  await page.getByLabel("Текст блока 2").fill("");
  await page.getByLabel("Текст блока 2").press("/");
  await search.fill("несуществующий блок");
  await expect(page.getByText("Блок не найден")).toBeVisible();
  await search.press("Escape");
  await expect(page.getByLabel("Текст блока 2")).toBeFocused();
  await page.getByLabel("Текст блока 2").press("/");
  await search.fill("Нумерованный");
  await search.press("Enter");
  await page.getByLabel("Список 2, пункт 1").fill("Первый");
  await page.getByLabel("Список 2, пункт 1").press("Enter");
  await page.getByLabel("Список 2, пункт 2").fill("Второй");
  await expect(page.locator(".note-list")).toHaveJSProperty("tagName", "OL");
  await page.getByLabel("Действия блока 1", { exact: true }).click();
  await page.getByLabel("Удалить блок 1", { exact: true }).click();
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Сохранённый текст",
  );
  await page.getByLabel("Действия блока 1", { exact: true }).click();
  await page.getByLabel("Удалить блок 1", { exact: true }).click();
  await page
    .getByRole("dialog", { name: "Удалить блок", exact: true })
    .getByRole("button", { name: "Удалить блок", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Сохранить страницу", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Сохранить страницу", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  expect(state.note.document.blocks).toEqual([
    {
      id: headingId,
      type: "list",
      style: "numbered",
      items: ["Первый", "Второй"],
    },
  ]);
});

test("page hierarchy spans API batches, supports collapse, nested creation and guarded breadcrumb navigation", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  const rootId = "aaaaaaaa-2222-4333-8444-555555555555";
  state.pages.push(
    ...Array.from({ length: 199 }, (_, i) => ({
      ...state.note,
      id: randomUUID(),
      title: `Страница ${i}`,
      document: { schema_version: 1, blocks: [] },
    })),
  );
  state.pages.push({
    ...state.note,
    id: rootId,
    title: "Личное",
    document: { schema_version: 1, blocks: [] },
  });
  state.note.parent_id = rootId;
  await section(page, "Заметки");
  const tree = page.getByRole("list", { name: "Дерево страниц", exact: true });
  await expect(
    tree.getByRole("button", { name: "Идеи для проекта", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Свернуть Личное", exact: true })
    .click();
  await expect(
    tree.getByRole("button", { name: "Идеи для проекта", exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "Развернуть Личное", exact: true })
    .click();
  await tree
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 1").fill("Черновик родителя");
  await page
    .getByRole("button", {
      name: "Добавить страницу в Идеи для проекта",
      exact: true,
    })
    .click();
  await page
    .getByLabel("Название страницы", { exact: true })
    .last()
    .fill("Новая идея");
  await page.getByRole("button", { name: "Создать", exact: true }).click();
  const guard = page.getByRole("dialog", {
    name: "Несохранённые изменения",
    exact: true,
  });
  await expect(guard).toBeVisible();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Черновик родителя",
  );
  await guard
    .getByRole("button", { name: "Сохранить и перейти", exact: true })
    .click();
  await expect(
    page.getByLabel("Название страницы", { exact: true }),
  ).toHaveValue("Новая идея");
  await expect(
    page.getByLabel("Название страницы", { exact: true }),
  ).toBeFocused();
  const created = state.pages.find((item) => item.title === "Новая идея")!;
  expect(created.parent_id).toBe(pageId);
  expect(state.note.document.blocks[0].text).toBe("Черновик родителя");
  await expect(
    page.getByRole("navigation", { name: "Положение страницы" }),
  ).toContainText("Личное");
  await expect(
    page.getByRole("navigation", { name: "Положение страницы" }),
  ).toContainText("Идеи для проекта");
  await page.getByLabel("Новый блок", { exact: true }).fill("Новый черновик");
  await page
    .getByRole("navigation", { name: "Положение страницы" })
    .getByRole("button", { name: "Личное", exact: true })
    .click();
  await guard
    .getByRole("button", { name: "Продолжить редактирование", exact: true })
    .click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Новый черновик");
  await page
    .getByRole("navigation", { name: "Положение страницы" })
    .getByRole("button", { name: "Личное", exact: true })
    .click();
  await guard
    .getByRole("button", { name: "Перейти без сохранения", exact: true })
    .click();
  await expect(
    page.getByLabel("Название страницы", { exact: true }),
  ).toHaveValue("Личное");
});

test("metadata success followed by document failure retains the draft and retries with the advanced version", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page
    .getByLabel("Название страницы", { exact: true })
    .fill("Новое название");
  await page.getByLabel("Текст блока 1").fill("Важный черновик");
  state.failDocumentOnce = true;
  await page
    .getByRole("button", { name: "Сохранить страницу", exact: true })
    .click();
  await expect(page.locator(".note-meta")).toContainText("Ошибка сохранения");
  await expect(page.locator(".note-meta")).toContainText("v4");
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Важный черновик");
  await page.keyboard.press("Control+s");
  await expect(
    page.getByRole("button", { name: "Сохранить страницу", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  expect(state.note.document.blocks[0].text).toBe("Важный черновик");
  expect(state.note.title).toBe("Новое название");
  expect(state.writes.map((item) => item.body?.expected_version)).toEqual([
    3, 4, 4, 5,
  ]);
});

test("dragging blocks preserves their IDs and a copied page link opens the owned page", async ({
  page,
  context,
}) => {
  const { state } = await contentWorkspace(page);
  const secondId = randomUUID();
  state.note.document.blocks.push({
    id: secondId,
    type: "text",
    text: "Второй абзац",
    text_format: "plain",
  });
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 2").focus();
  await page
    .getByLabel("Действия блока 2", { exact: true })
    .dragTo(page.locator(".block-row").first());
  await page.keyboard.press("Control+s");
  await expect(
    page.getByRole("button", { name: "Сохранить страницу", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  expect(state.note.document.blocks.map((item) => item.id)).toEqual([
    secondId,
    blockId,
  ]);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByLabel("Действия страницы", { exact: true }).click();
  await page
    .getByRole("button", { name: "Копировать ссылку", exact: true })
    .click();
  await expect(
    page.getByText("Ссылка скопирована", { exact: true }),
  ).toBeVisible();
  const link = await page.evaluate(() => navigator.clipboard.readText());
  expect(link).toBe(`http://127.0.0.1:3001/workspace?page=${pageId}`);
  await page.goto(link);
  await expect(
    page.getByLabel("Название страницы", { exact: true }),
  ).toHaveValue("Идеи для проекта");
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Второй абзац");
  await page.getByLabel("Новый блок", { exact: true }).press("/");
  await page.getByLabel("Найти тип блока").fill("Ссылка");
  await page.getByLabel("Найти тип блока").press("Enter");
  await expect(page.getByLabel("Подпись ссылки 3")).toBeFocused();
  await page.getByLabel("Подпись ссылки 3").fill("Ресурс");
  await page.getByLabel("Адрес ссылки 3").fill("https://example.com/resource");
  await page.keyboard.press("Control+s");
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
  expect(state.note.document.blocks[2]).toMatchObject({
    type: "link",
    text: "Ресурс",
    url: "https://example.com/resource",
  });
  await page.reload();
  await expect(page.getByRole("link", { name: "Ресурс ↗" })).toHaveAttribute(
    "href",
    "https://example.com/resource",
  );
  await expect(page.getByLabel("Адрес ссылки 3")).toBeHidden();
  await page.locator(".note-link-edit > summary").click();
  await expect(page.getByLabel("Адрес ссылки 3")).toHaveValue(
    "https://example.com/resource",
  );
  await page.evaluate(() =>
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    }),
  );
  await page.getByLabel("Действия страницы", { exact: true }).click();
  await page
    .getByRole("button", { name: "Копировать ссылку", exact: true })
    .click();
  await expect(
    page.getByText("Не удалось скопировать ссылку", { exact: true }),
  ).toBeVisible();
});

test("saving blocks duplicate submits and navigation until the request completes", async ({
  page,
}) => {
  await contentWorkspace(page);
  let release!: () => void;
  const wait = new Promise<void>((resolve) => {
    release = resolve;
  });
  let submits = 0;
  await page.route("**/api/v1/notes/pages/*/document", async (route) => {
    submits++;
    await wait;
    await route.fallback();
  });
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Текст блока 1").fill("Сохранить один раз");
  await page.keyboard.press("Control+s");
  await expect(page.locator(".note-meta")).toContainText("Сохраняем");
  await page.keyboard.press("Control+s");
  await expect(
    page.getByRole("button", { name: "Сохранить страницу", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Идеи для проекта", exact: true }),
  ).toBeDisabled();
  await expect.poll(() => submits).toBe(1);
  release();
  await expect(page.locator(".note-meta")).toContainText("Сохранено");
});

test("page navigation retains a conflicting or invalid draft and moving excludes descendants", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  const childId = randomUUID();
  state.pages.push({
    ...state.note,
    id: childId,
    parent_id: pageId,
    title: "Дочерняя",
    document: { schema_version: 1, blocks: [] },
  });
  await section(page, "Заметки");
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await page.getByLabel("Действия страницы", { exact: true }).click();
  await page
    .locator(".note-topbar")
    .getByRole("button", { name: "Переместить", exact: true })
    .click();
  await expect(
    page
      .getByLabel("Родительская страница")
      .getByRole("option", { name: "Дочерняя", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Готово", exact: true }).click();
  await page.getByLabel("Текст блока 1").fill("Не терять");
  await page
    .getByRole("list", { name: "Дерево страниц", exact: true })
    .getByRole("button", { name: "Дочерняя", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Несохранённые изменения",
    exact: true,
  });
  state.conflict = true;
  await dialog
    .getByRole("button", { name: "Сохранить и перейти", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("Данные изменились");
  await dialog
    .getByRole("button", { name: "Продолжить редактирование", exact: true })
    .click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue("Не терять");
  state.conflict = false;
  await page.getByLabel("Название страницы", { exact: true }).fill("   ");
  await page
    .getByRole("list", { name: "Дерево страниц", exact: true })
    .getByRole("button", { name: "Дочерняя", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Сохранить и перейти", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText("Проверь название");
  expect(state.writes).toHaveLength(1);
  await dialog
    .getByRole("button", { name: "Продолжить редактирование", exact: true })
    .click();
  await page
    .getByLabel("Название страницы", { exact: true })
    .fill("Идеи для проекта");
  await page.getByLabel("Текст блока 1").fill("Сохранить перед закрытием");
  const closed = page.waitForEvent("dialog");
  const closing = page.close({ runBeforeUnload: true });
  const unload = await closed;
  expect(unload.type()).toBe("beforeunload");
  await unload.dismiss();
  await closing;
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Сохранить перед закрытием",
  );
  await page.route(`**/api/v1/notes/pages/${childId}`, (route) =>
    route.fulfill({ status: 503, json: {} }),
  );
  await page
    .getByRole("list", { name: "Дерево страниц", exact: true })
    .getByRole("button", { name: "Дочерняя", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Сохранить и перейти", exact: true })
    .click();
  await expect(page.locator(".note-canvas .ui-error")).toContainText(
    "Не удалось загрузить данные",
  );
  await expect(
    page.getByRole("button", { name: "Идеи для проекта", exact: true }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Идеи для проекта", exact: true })
    .click();
  await expect(page.getByLabel("Текст блока 1")).toHaveValue(
    "Сохранить перед закрытием",
  );
});

for (const width of [1440, 834, 390]) {
  test(`notes canvas and block menu fit light and dark themes at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const { state } = await contentWorkspace(page);
    state.pages.push({
      ...state.note,
      id: randomUUID(),
      parent_id: pageId,
      title: "Следующие шаги",
    });
    Object.assign(state.note, {
      document: {
        schema_version: 1,
        blocks: [
          { id: randomUUID(), type: "heading", level: 2, text: "План проекта" },
          {
            id: blockId,
            type: "text",
            text_format: "plain",
            text: "Все идеи начинаются с чистой страницы. Здесь можно собрать мысли, расставить акценты и наметить следующий шаг.",
          },
          {
            id: randomUUID(),
            type: "list",
            style: "bulleted",
            items: ["Исследовать задачу", "Собрать первые наброски"],
          },
          {
            id: randomUUID(),
            type: "checkbox",
            checked: true,
            text: "Обсудить идею",
          },
          {
            id: randomUUID(),
            type: "link",
            text: "Материалы проекта",
            url: "https://example.com/project",
          },
        ],
      },
    });
    await section(page, "Заметки");
    await page
      .getByRole("button", { name: "Идеи для проекта", exact: true })
      .click();
    if (width === 390) {
      await page.getByRole("button", { name: /^Страницы ↑$/ }).click();
      await expect(page.locator(".page-tree")).toBeHidden();
    }
    await expect(
      page.getByLabel("Название страницы", { exact: true }),
    ).toBeVisible();
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while ((await page.locator("html").getAttribute("data-theme")) !== theme)
        await toggle.click();
      await page.screenshot({
        path: info.outputPath(`notes-${theme}.png`),
        fullPage: true,
      });
      await page
        .getByRole("button", { name: "Добавить блок", exact: true })
        .click();
      await expect(page.getByLabel("Найти тип блока")).toBeFocused();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
      ).toBeLessThanOrEqual(width);
      const menu = await page
        .getByRole("dialog", { name: "Добавить блок", exact: true })
        .boundingBox();
      expect(menu!.x).toBeGreaterThanOrEqual(0);
      expect(menu!.x + menu!.width).toBeLessThanOrEqual(width);
      await page.screenshot({
        path: info.outputPath(`notes-menu-${theme}.png`),
        fullPage: true,
      });
      await page.keyboard.press("Escape");
    }
  });
}

test("deep page nesting scrolls within the sidebar without widening the document", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const { state } = await contentWorkspace(page);
  let parent = pageId;
  for (let depth = 0; depth < 30; depth++) {
    const id = randomUUID();
    state.pages.push({ ...state.note, id, parent_id: parent, title: `Уровень ${depth}`, document: { schema_version: 1, blocks: [] } });
    parent = id;
  }
  await section(page, "Заметки");
  await expect(page.getByRole("button", { name: "Уровень 29", exact: true })).toBeAttached();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1440);
  const tree = page.locator(".page-tree");
  expect(await tree.evaluate((element) => element.scrollWidth)).toBeGreaterThan(await tree.evaluate((element) => element.clientWidth));
});

test("dropping a material selects one file without uploading until confirmation", async ({ page }) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Материалы");
  const data = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["# Dropped note"], "dropped.md", { type: "text/markdown" }));
    return transfer;
  });
  await page.locator(".material-dropzone").dispatchEvent("drop", { dataTransfer: data });
  const dialog = page.getByRole("dialog", { name: "Загрузить файл", exact: true });
  await expect(dialog).toContainText("dropped.md");
  expect(state.writes).toEqual([]);
  await dialog.getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(state.uploadBody).toBe("# Dropped note");
  expect(state.uploadType).toBe("text/markdown");
  expect(state.writes.filter(write => write.path.endsWith("/uploads"))).toHaveLength(1);
  await page.getByRole("button", { name: "Загрузить файл", exact: true }).click();
  await expect(page.getByRole("dialog")).not.toContainText("dropped.md");
});

test("material drop rejects multiple files and keeps unsupported files local", async ({ page }) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Материалы");
  const multiple = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["one"], "one.txt"));
    transfer.items.add(new File(["two"], "two.txt"));
    return transfer;
  });
  await page.locator(".material-dropzone").dispatchEvent("drop", { dataTransfer: multiple });
  await expect(page.locator(".inline-error")).toContainText("один файл");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "Загрузить файл", exact: true }).click();
  const unsupported = await page.evaluateHandle(() => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["bad"], "bad.exe"));
    return transfer;
  });
  await page.locator(".upload-zone").dispatchEvent("drop", { dataTransfer: unsupported });
  await expect(page.getByRole("dialog")).toContainText("bad.exe");
  await page.getByRole("dialog").getByRole("button", { name: "Загрузить", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Поддерживаются");
  expect(state.writes).toEqual([]);
});

test("clicking blank note paper focuses the next block without changing existing content", async ({ page }) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page.getByRole("button", { name: "Идеи для проекта", exact: true }).click();
  const paper = page.locator(".note-sheet").first();
  await paper.click({ position: { x: 10, y: 10 } });
  await expect(page.getByRole("textbox", { name: "Новый блок", exact: true })).toBeFocused();
  await page.keyboard.type("Next thought");
  await expect(page.getByLabel("Текст блока 2", { exact: true })).toHaveValue("Next thought");
  await expect(page.getByLabel("Текст блока 1", { exact: true })).toHaveValue("Сохранённый текст");
  expect(state.writes).toEqual([]);
});
