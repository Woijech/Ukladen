import { writeFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace, calendarEvent, profile } from "./workspace-fixtures";

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
    conflict: false,
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
        Object.assign(note, {
          title: body!.title,
          version: 1,
          document: { schema_version: 1, blocks: [] },
        });
        return route.fulfill({ status: 201, json: note });
      }
      return list(
        (url.searchParams.get("trashed") === "true") === !!note.trashed_at
          ? [note]
          : [],
      );
    }
    if (path === `/api/v1/notes/pages/${pageId}/document`) {
      if (state.conflict) return route.fulfill({ status: 409, json: {} });
      expect(body!.expected_version).toBe(note.version);
      note.document = body!.document as typeof note.document;
      note.version++;
      return route.fulfill({
        json: {
          page_id: pageId,
          version: note.version,
          document: note.document,
        },
      });
    }
    if (path === `/api/v1/notes/pages/${pageId}`) {
      if (method === "PATCH") {
        expect(body!.expected_version).toBe(note.version);
        Object.assign(note, body);
        note.version++;
      }
      return route.fulfill({ json: note });
    }
    if (
      path === `/api/v1/notes/pages/${pageId}/trash` ||
      path === `/api/v1/notes/pages/${pageId}/restore`
    ) {
      expect(body!.expected_version).toBe(note.version);
      note.version++;
      note.trashed_at = path.endsWith("trash") ? "2026-10-16T12:00:00Z" : null;
      return route.fulfill({ json: note });
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

async function section(page: Page, name: string) {
  if (
    await page
      .getByRole("button", { name: "Открыть навигацию", exact: true })
      .isVisible()
  ) {
    await page
      .getByRole("button", { name: "Открыть навигацию", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: "Навигация", exact: true })
      .getByRole("button", { name, exact: true })
      .click();
  } else
    await page
      .locator(".sidebar")
      .getByRole("button", { name, exact: true })
      .click();
}

test("block editing preserves IDs and Markdown format, supports reorder, guards navigation and saves with versions", async ({
  page,
}) => {
  const { state } = await contentWorkspace(page);
  await section(page, "Заметки");
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
  await page.getByLabel("Текст блока 1").fill("Новый текст");
  await section(page, "Материалы");
  await expect(
    page.getByRole("dialog", { name: "Несохранённые изменения" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Остаться", exact: true }).click();
  await page.getByLabel("Тип нового блока").selectOption("checkbox");
  await page
    .getByRole("button", { name: "Добавить блок", exact: false })
    .click();
  await page.getByLabel("Пункт 2", { exact: true }).fill("Проверить идею");
  await page.getByLabel("Отметить пункт 2").check();
  await page.getByRole("button", { name: "Поднять блок 2" }).click();
  await page.getByRole("button", { name: "Сохранить страницу" }).click();
  await expect(
    page.getByRole("button", { name: "Сохранить страницу" }),
  ).toBeDisabled();
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
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
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
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
  await page.getByRole("button", { name: "В корзину", exact: true }).click();
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
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
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
    await contentWorkspace(page);
    await expect(
      page.getByRole("button", {
        name: "Задачи · в разработке",
        exact: true,
        includeHidden: true,
      }),
    ).toBeDisabled();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await page.screenshot({
      path: info.outputPath("calendar-light.png"),
      animations: "disabled",
    });
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
    await page.getByRole("button", { name: /Идеи для проекта/ }).click();
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
  await expect(page.getByLabel("Начало", { exact: true })).toHaveValue(
    "2026-10-16T14:00",
  );
});

test("event reminders bind to the original event and use the real one-shot API", async ({
  page,
}) => {
  const { state, workspace } = await contentWorkspace(page);
  await page.locator(".event-card.personal-event").click();
  await page.getByRole("button", { name: /Заметки и напоминания/ }).click();
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
  await page.getByRole("button", { name: /Идеи для проекта/ }).click();
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
