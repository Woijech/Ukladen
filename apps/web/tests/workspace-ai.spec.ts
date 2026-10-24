import { expect, test, type Page } from "@playwright/test";
import { login, mockWorkspace } from "./workspace-fixtures";

const chatId = "11111111-2222-4333-8444-555555555555";
const pageId = "22222222-2222-4333-8444-555555555555";
const connectionId = "33333333-2222-4333-8444-555555555555";
const reference = {
  source: "page",
  id: pageId,
  title: "Моя заметка",
  version: 1,
  locator: "chars:0:100",
  parent_id: null,
};
const chat = {
  id: chatId,
  title: "Подготовка",
  provider: "openrouter",
  model: "synthetic/model",
  offering_id: "flash",
  connection_id: null,
};
const frame = (event: string, data: unknown) =>
  `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const metrics = {
  runs: 1,
  attempts: 2,
  input_tokens: null,
  output_tokens: 40,
  known_input_tokens: 10,
  known_output_tokens: 40,
  unknown_input_attempts: 1,
  unknown_output_attempts: 0,
  unpriced_attempts: 2,
  estimated_costs: {},
};

async function mockAi(page: Page) {
  const workspace = await mockWorkspace(page);
  const owner = workspace.userId;
  const state = {
    workspace,
    chats: [{ ...chat }],
    messages: [] as {
      id: string;
      sequence: number;
      role: string;
      content: string;
      sources: (typeof reference)[];
    }[],
    run: null as null | Record<string, unknown>,
    writes: [] as { path: string; body: Record<string, unknown> | null }[],
    preferences: { instructions: "Отвечай кратко", version: 1 },
    previewMissing: false,
    disconnect: false,
    connections: [
      {
        id: connectionId,
        label: "Мой OpenRouter",
        key_mask: "********",
        disconnected_at: null as string | null,
      },
    ],
  };
  await page.route("**/api/v1/notes/pages?**", (route) =>
    route.fulfill({ json: { items: [{ id: pageId, title: "Моя заметка" }] } }),
  );
  await page.route("**/api/v1/ai/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname,
      method = request.method();
    const body =
      method === "GET" || !request.postData()
        ? null
        : (request.postDataJSON() as Record<string, unknown>);
    if (!workspace.authenticated)
      return route.fulfill({ status: 401, json: {} });
    if (method !== "GET") {
      expect(request.headers()["x-csrf-token"]).toBe("c".repeat(43));
      state.writes.push({ path, body });
    }
    if (path.endsWith("/models"))
      return route.fulfill({
        json: [
          {
            id: "flash",
            name: "Test Flash",
            provider: "openrouter",
            model: "synthetic/model",
            streaming: true,
            tools: true,
            free_only: true,
            personal_allowed: true,
          },
        ],
      });
    if (path.endsWith("/preferences")) {
      if (method === "PUT")
        state.preferences = {
          instructions: String(body!.instructions),
          version: state.preferences.version + 1,
        };
      return route.fulfill({ json: state.preferences });
    }
    if (path.endsWith(`/connections/${connectionId}`) && method === "DELETE") {
      state.connections[0].disconnected_at = "2026-10-24T12:00:00Z";
      return route.fulfill({ status: 204 });
    }
    if (path.endsWith("/connections")) {
      if (method === "POST") {
        const connection = {
          id: "66666666-2222-4333-8444-555555555555",
          label: String(body!.label),
          key_mask: "********",
          disconnected_at: null,
        };
        state.connections.push(connection);
        return route.fulfill({ status: 201, json: connection });
      }
      return route.fulfill({ json: { items: state.connections } });
    }
    if (path.endsWith("/sources/read"))
      return route.fulfill({
        json: state.previewMissing
          ? {
              status: "not_found",
              sources: [],
              warnings: [],
              data: null,
              coverage: "none",
              next_offset: null,
            }
          : {
              status: "ok",
              sources: [{ ...reference, version: 2 }],
              data: {
                text: "Текущий текст <script>window.injected=true</script>",
              },
              warnings: [],
              coverage: "partial",
              next_offset: null,
            },
      });
    if (path.endsWith("/conversations")) {
      if (method === "POST") {
        const created = {
          ...chat,
          title: String(body!.title),
          connection_id: body!.connection_id as null,
        };
        state.chats = [created];
        return route.fulfill({ status: 201, json: created });
      }
      return route.fulfill({
        json: { items: workspace.userId === owner ? state.chats : [] },
      });
    }
    if (path.endsWith("/state"))
      return route.fulfill({
        json: { conversation: state.chats[0], run: state.run },
      });
    if (path.endsWith("/messages/stream")) {
      const run = {
        id: "44444444-2222-4333-8444-555555555555",
        status: state.disconnect ? "running" : "completed",
        provider: "openrouter",
        model: chat.model,
        submission_id: body!.submission_id,
        attempts: [],
        tools: [],
        price: null,
      };
      state.run = run;
      state.messages = [
        {
          id: "user-message",
          sequence: 1,
          role: "user",
          content: String(body!.message),
          sources: [],
        },
      ];
      if (!state.disconnect)
        state.messages.push({
          id: "answer-message",
          sequence: 2,
          role: "assistant",
          content: `Ответ по заметке [source:${pageId}]`,
          sources: [reference],
        });
      return route.fulfill({
        contentType: "text/event-stream",
        body:
          frame("run", run) +
          frame("progress", { kind: "model", status: "started" }) +
          frame("delta", { id: "delta-1", text: "Ответ по " }) +
          frame("delta", { id: "delta-1", text: "заметке" }) +
          (state.disconnect
            ? frame("recover", { run_id: run.id })
            : frame("run", run) + frame("done", {})),
      });
    }
    if (path.endsWith("/messages"))
      return route.fulfill({ json: { items: state.messages } });
    if (path.endsWith("/cancel")) {
      state.run = { ...state.run, status: "cancelled" };
      return route.fulfill({ json: state.run });
    }
    if (path.endsWith("/usage"))
      return route.fulfill({
        json: {
          timezone: "Europe/Minsk",
          date_from: "2026-10-18",
          date_to: "2026-10-24",
          summary: metrics,
          fake: { ...metrics, runs: 0, attempts: 0 },
          daily: [{ ...metrics, label: "2026-10-24", fake: false }],
          models: [
            {
              ...metrics,
              label: "openrouter / synthetic/model · operator",
              fake: false,
            },
          ],
          recent_runs: [],
          has_more: false,
          retained_from: "2026-09-24T12:00:00Z",
          retention_partial: new URL(request.url()).searchParams.has(
            "date_from",
          ),
        },
      });
    if (path.endsWith(`/conversations/${chatId}`) && method === "DELETE") {
      state.chats = [];
      state.messages = [];
      return route.fulfill({ status: 204 });
    }
    throw new Error(`Unexpected AI request: ${method} ${path}`);
  });
  return state;
}

test("AI sends selected sources once and opens current safe source text", async ({
  page,
}) => {
  const state = await mockAi(page);
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page
    .getByRole("button", { name: "Все источники", exact: true })
    .click();
  await page.getByLabel("Все мои источники автоматически").uncheck();
  await page.getByLabel("Моя заметка", { exact: true }).check();
  await page.getByRole("button", { name: "Применить", exact: true }).click();
  await page.getByLabel("Сообщение AI").fill("Объясни заметку");
  await page.getByRole("button", { name: "Отправить ↑" }).dblclick();
  await expect(page.getByRole("log")).toContainText("Ответ по заметке");
  const submitted = state.writes.filter((item) =>
    item.path.endsWith("/messages/stream"),
  );
  expect(submitted).toHaveLength(1);
  expect(submitted[0].body!.source_scope).toEqual({
    page_ids: [pageId],
    material_ids: [],
    database_ids: [],
    calendar: false,
  });
  await page
    .getByRole("log")
    .getByRole("button", { name: "Моя заметка", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText(
    "Источник изменился после ответа",
  );
  await expect(page.getByRole("dialog")).toContainText(
    "Текущий текст <script>",
  );
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  state.previewMissing = true;
  await page
    .getByRole("log")
    .getByRole("button", { name: "Моя заметка", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog")).toContainText("Источник недоступен");
  await expect(page.getByRole("dialog")).not.toContainText("Текущий текст");
});

test("broken streaming recovers the stored run without resubmission and can cancel", async ({
  page,
}) => {
  const state = await mockAi(page);
  state.disconnect = true;
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page.getByLabel("Сообщение AI").fill("Долгий вопрос");
  await page.getByRole("button", { name: "Отправить ↑" }).click();
  await expect(
    page.getByText("Соединение прервано. Восстановите состояние чата."),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Восстановить состояние", exact: true })
    .click();
  expect(
    state.writes.filter((item) => item.path.endsWith("/messages/stream")),
  ).toHaveLength(1);
  await page.getByRole("button", { name: "Остановить", exact: true }).click();
  await expect(page.getByRole("button", { name: "Отправить ↑" })).toBeVisible();
  expect(state.run!.status).toBe("cancelled");
  expect(
    state.writes.filter((item) => item.path.endsWith("/cancel")),
  ).toHaveLength(1);
});

test("model connection selection and explicitly saved instructions reuse the existing shell", async ({
  page,
}) => {
  const state = await mockAi(page);
  await page.goto("/workspace/ai");
  await page.getByRole("button", { name: "Новый чат", exact: false }).click();
  await page.getByLabel("Название чата").fill("Новая подготовка");
  await page.getByLabel("Модель", { exact: true }).selectOption("flash");
  await page
    .getByLabel("Подключение", { exact: true })
    .selectOption(connectionId);
  await page.getByRole("button", { name: "Создать чат", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    state.writes.find((item) => item.path.endsWith("/conversations"))!.body,
  ).toEqual({
    title: "Новая подготовка",
    offering_id: "flash",
    connection_id: connectionId,
  });
  await page.getByRole("button", { name: "Настройки AI", exact: true }).click();
  await page.getByLabel("Личные инструкции").fill("Объясняй с примерами");
  expect(state.preferences.instructions).toBe("Отвечай кратко");
  await page
    .getByRole("button", { name: "Сохранить инструкции", exact: true })
    .click();
  await expect(page.getByText("Сохранено", { exact: true })).toBeVisible();
  expect(state.preferences.instructions).toBe("Объясняй с примерами");
  await page
    .getByRole("button", { name: "Подключить API", exact: true })
    .click();
  await page.getByLabel("Название подключения").fill("Запасной API");
  await page
    .getByLabel("API-ключ", { exact: true })
    .fill("synthetic-not-a-real-provider-key");
  await page
    .getByRole("button", { name: "Сохранить подключение", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Запасной API", { exact: true })).toBeVisible();
  await expect(page.getByLabel("API-ключ", { exact: true })).toHaveCount(0);
  await page
    .getByRole("button", { name: "Отключить", exact: true })
    .first()
    .click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Отключить", exact: true })
    .click();
  await expect(page.getByText("******** · Отключено")).toBeVisible();
  expect(
    await page.evaluate(() =>
      Object.keys(localStorage).filter((key) => key !== "ukladen-theme"),
    ),
  ).toEqual([]);
});

test("usage preserves unknowns and responsive source controls work with a keyboard", async ({
  page,
}) => {
  await mockAi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/workspace/ai/usage");
  await expect(page.getByText("Europe/Minsk", { exact: false })).toBeVisible();
  await expect(page.getByRole("table", { name: "По дням" })).toContainText(
    "Неизвестно",
  );
  await page.getByRole("button", { name: "30 дней", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "30 дней", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByLabel("С даты", { exact: true }).fill("2026-01-01");
  await page.getByLabel("По дату", { exact: true }).fill("2026-01-02");
  await page
    .getByRole("button", { name: "Показать период", exact: true })
    .click();
  await expect(
    page.getByText("Часть выбранного периода уже за пределами хранения.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page
    .getByRole("button", { name: "Все источники", exact: true })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Все источники", exact: true }),
  ).toBeFocused();
  await page.screenshot({
    path: test.info().outputPath("ai-mobile.png"),
    fullPage: true,
  });
});

test("logout and another account discard AI drafts and cached chats", async ({
  page,
}) => {
  const state = await mockAi(page);
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page.getByLabel("Сообщение AI").fill("Private unfinished question");
  await page.locator(".account-button").click();
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  await expect(
    page.getByRole("heading", { name: "Войти в Ukladen" }),
  ).toBeVisible();
  await expect(page.getByLabel("Сообщение AI")).toHaveCount(0);
  state.workspace.userId = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
  await login(page);
  await page.getByRole("button", { name: "Пока без группы" }).click();
  await expect(page.getByText("Private unfinished question")).toHaveCount(0);
  await page.getByRole("button", { name: "AI", exact: true }).click();
  await expect(page.getByRole("button", { name: /Подготовка/ })).toHaveCount(0);
});
