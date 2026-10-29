import { expect, test, type Page } from "@playwright/test";
import type { Proposal } from "../src/app/workspace/panels/ai-actions";
import { login, mockWorkspace, navigateSection } from "./workspace-fixtures";

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
    documentProgress: null as null | { phase: string; processed_characters: number; total_characters: number; steps: number; error: string | null },
    proposals: [] as Proposal[],
    proposalCommits: 0,
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
    if (path.endsWith("/proposals")) return route.fulfill({ json: state.proposals });
    if (path.endsWith("/decision")) {
      const proposal = state.proposals.find((item) => path.includes(item.id));
      if (!proposal) return route.fulfill({ status: 404, json: {} });
      expect(body?.digest).toBe(proposal.digest);
      expect(Object.keys(body!).sort()).toEqual(["decision", "digest"]);
      if (proposal.status === "pending") {
        if (Date.parse(proposal.expires_at) <= Date.now()) proposal.status = "expired";
        else if (body?.decision === "reject") proposal.status = "rejected";
        else {
          proposal.status = "applied";
          state.proposalCommits++;
          proposal.outcomes = proposal.effects.map((effect, index) => ({ operation: effect.operation, target_id: `${pageId.slice(0, -1)}${index}` }));
        }
      }
      return route.fulfill({ json: proposal });
    }
    if (path.endsWith("/document-progress")) return route.fulfill({ json: state.documentProgress });
    if (path.endsWith("/index")) return route.fulfill({ json: { status: "ready", version: 1 } });
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
            available: true,
            operator_available: true,
            is_default: true,
          },
          ...["Claude Haiku", "Claude Sonnet", "GPT-5.5"].map((name, index) => ({
            id: `planned-${index}`,
            name,
            provider: "openrouter",
            model: `synthetic/planned-${index}`,
            streaming: true,
            tools: false,
            free_only: false,
            personal_allowed: true,
            available: false,
            operator_available: false,
            is_default: false,
          })),
        ],
      });
    if (path.endsWith("/access"))
      return route.fulfill({json: {
        plan: "free", monthly_request_limit: null, monthly_token_limit: null,
      }});
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
        status: state.disconnect || body!.full_sources ? "running" : "completed",
        provider: "openrouter",
        model: chat.model,
        submission_id: body!.submission_id,
        attempts: [],
        tools: [],
        price: null,
      };
      state.run = run;
      if (body!.full_sources) state.documentProgress = { phase: "reading", processed_characters: 1500, total_characters: 6000, steps: 1, error: null };
      state.messages = [
        {
          id: "user-message",
          sequence: 1,
          role: "user",
          content: String(body!.message),
          sources: [],
        },
      ];
      if (!state.disconnect && !body!.full_sources)
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
    task_ids: [],
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

test("application model is selected by default and future models cannot be selected", async ({page}) => {
  const state = await mockAi(page);
  state.connections = [];
  await page.goto("/workspace/ai");
  await page.getByRole("button", {name: "Новый чат", exact: false}).click();
  await expect(page.getByLabel("Модель", {exact: true})).toHaveValue("flash");
  await expect(page.getByLabel("Подключение", {exact: true})).toHaveValue("");
  for (const name of ["Claude Haiku", "Claude Sonnet", "GPT-5.5"])
    await expect(page.getByRole("option", {name: `${name} · пока недоступно`, exact: true})).toHaveJSProperty("disabled", true);
  await page.getByRole("button", {name: "Создать чат", exact: true}).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(state.writes.find(item => item.path.endsWith("/conversations"))!.body).toEqual({
    title: "Новая беседа", offering_id: "flash",
  });
});

test("missing application credentials block creation without an implicit demo or personal fallback", async ({page}) => {
  const state = await mockAi(page);
  state.connections = [];
  await page.route("**/api/v1/ai/models", route => route.fulfill({json: [{
    id: "flash", name: "Test Flash", provider: "openrouter", model: "synthetic/model",
    streaming: true, tools: true, free_only: false, personal_allowed: true,
    available: true, operator_available: false, is_default: true,
  }]}));
  await page.goto("/workspace/ai");
  await page.getByRole("button", {name: "Новый чат", exact: false}).click();
  await expect(page.getByRole("button", {name: "Создать чат", exact: true})).toBeDisabled();
  await expect(page.getByLabel("Модель", {exact: true})).toHaveValue("flash");
  expect(state.writes).toHaveLength(0);
});

test("demo mode requires an explicit selection and never sends an application model", async ({page}) => {
  const state = await mockAi(page);
  await page.goto("/workspace/ai");
  await page.getByRole("button", {name: "Новый чат", exact: false}).click();
  await page.getByLabel("Модель", {exact: true}).selectOption("__demo__");
  await page.getByRole("button", {name: "Создать чат", exact: true}).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(state.writes.find(item => item.path.endsWith("/conversations"))!.body).toEqual({
    title: "Новая беседа", demo: true,
  });
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
  await expect(page.getByRole("region", {name: "Доступ к AI"})).toContainText("Бесплатный доступ");
  await expect(page.getByRole("region", {name: "Доступ к AI"})).toContainText("без ограничений");
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
  await navigateSection(page, "AI");
  await expect(page.getByRole("button", { name: /Подготовка/ })).toHaveCount(0);
});


test("full-source processing requires sources, shows saved progress and cancels", async ({ page }) => {
  const state = await mockAi(page);
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page.getByLabel("Разобрать выбранные страницы и файлы целиком").check();
  await page.getByLabel("Сообщение AI").fill("Сверь конспект с материалами лекции целиком");
  await page.getByRole("button", { name: "Отправить ↑" }).click();
  await expect(page.getByText("Для полного разбора выбери страницы и файлы в источниках запроса.")).toBeVisible();
  await page.getByRole("button", { name: "Все источники", exact: true }).click();
  await page.getByLabel("Все мои источники автоматически").uncheck();
  await page.getByLabel("Моя заметка", { exact: true }).check();
  await page.getByRole("button", { name: "Применить", exact: true }).click();
  await page.getByRole("button", { name: "Отправить ↑" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Читаю источники целиком · 25%" })).toBeVisible();
  const sent = state.writes.find(item => item.path.endsWith("/messages/stream"));
  expect(sent?.body?.full_sources).toBe(true);
  await page.reload();
  await expect(page.getByText("Читаю источники целиком · 25%", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("full-source-progress.png"), fullPage: true });
  await page.getByRole("button", { name: "Остановить", exact: true }).click();
  await expect(page.getByText("Остановлено", { exact: true })).toBeVisible();
});


function actionProposal(): Proposal {
  return {
    id: "77777777-2222-4333-8444-555555555555", digest: "a".repeat(64), run_id: "run-proposal",
    expires_at: new Date(Date.now() + 86400000).toISOString(), timezone: "Europe/Minsk",
    status: "pending", outcomes: [], effects: [
      { operation: "page_update", target_id: pageId, warnings: [], before: {
        title: "До правки", document: { schema_version: 1, blocks: [{ id: "block", type: "text", text: "Исходный текст", text_format: "plain" }] },
      }, after: { title: "После правки", document: { schema_version: 1, blocks: [{ id: "block", type: "text", text: "<script>window.injected=true</script>", text_format: "plain" }] } } },
      { operation: "event_create", target_id: null, warnings: [], before: null, after: {
        title: "Тренировка", starts_at: "2030-10-27T15:00:00Z", ends_at: "2030-10-27T16:30:00Z", blocks_time: true,
      } },
      { operation: "reminder_create", target_id: null, warnings: [], before: null, after: {
        title: "Тренировка", event_action: 1, minutes_before: 30, due_at: "2030-10-27T14:30:00Z",
      } },
    ],
  };
}

test("AI shows exact batch preview and applies only its confirmed digest", async ({ page }) => {
  const state = await mockAi(page);
  state.proposals = [actionProposal()];
  await page.goto(`/workspace/ai?chat=${chatId}`);
  const proposals = page.getByRole("region", { name: "Предложения действий" });
  await expect(proposals.getByText("Исходный текст", { exact: true })).toBeVisible();
  await expect(proposals.getByText("<script>window.injected=true</script>", { exact: true })).toBeVisible();
  await expect(proposals.getByText(/Начало:.*18:00/)).toBeVisible();
  await expect(proposals.getByText(/Уведомление:.*17:30/)).toBeVisible();
  expect(state.proposalCommits).toBe(0);
  expect(await page.evaluate(() => "injected" in window)).toBe(false);
  await proposals.getByRole("button", { name: "Применить всё", exact: true }).click();
  await expect(proposals.getByText("Все изменения применены", { exact: true })).toBeVisible();
  expect(state.proposalCommits).toBe(1);
  await page.reload();
  await expect(page.getByText("Все изменения применены", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Применить всё", exact: true })).toHaveCount(0);
  expect(state.proposalCommits).toBe(1);
  await page.screenshot({ path: test.info().outputPath("confirmed-actions.png"), fullPage: true });
});

test("AI proposals reject and expire without applying", async ({ page }) => {
  const state = await mockAi(page);
  state.proposals = [actionProposal()];
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await page.getByRole("button", { name: "Отклонить", exact: true }).click();
  await expect(page.getByText("Отклонено", { exact: true })).toBeVisible();
  expect(state.proposalCommits).toBe(0);
  state.proposals[0].status = "expired";
  state.proposals[0].expires_at = "2020-01-01T00:00:00Z";
  await page.reload();
  await expect(page.getByText("Срок подтверждения истёк", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Применить всё", exact: true })).toHaveCount(0);
});


test("a proposal appears when the same running submission completes", async ({ page }) => {
  const state = await mockAi(page);
  state.run = { id: "delayed-proposal", status: "running" };
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await expect(page.getByRole("button", { name: "Остановить", exact: true })).toBeVisible();
  state.proposals = [actionProposal()];
  state.run = { ...state.run, status: "completed" };
  await expect(page.getByRole("button", { name: "Применить всё", exact: true })).toBeVisible();
  expect(state.proposalCommits).toBe(0);
});

test("AI task proposals show provenance and estimates, and edits require a new preview", async ({ page }) => {
  const state = await mockAi(page);
  const source = { ...reference, source: "page" as const };
  const proposedTask = { title: "Read chapter", description: null, priority: "high", deadline_at: null, estimated_minutes: 45, remaining_minutes: 45, parent_id: null };
  const original = actionProposal();
  original.batch = { actions: [{ operation: "task_create", task: proposedTask, estimate_kind: "estimate", sources: [source], uncertainties: ["Deadline is unclear"] }] };
  original.effects = [{ operation: "task_create", target_id: null, before: null, after: { task: proposedTask, estimate_kind: "estimate", sources: [source], uncertainties: ["Deadline is unclear"], possible_duplicates: [{ id: "duplicate-task", title: "Read similar chapter", status: "todo" }] }, warnings: [] }];
  state.proposals = [original];
  await page.route("**/api/v1/ai/proposals/*/revise", async route => {
    const body = route.request().postDataJSON();
    expect(route.request().headers()["x-csrf-token"]).toBe("c".repeat(43));
    expect(body.actions[0].sources).toEqual([source]);
    const revised: Proposal = { ...original, id: "revision-task", digest: "c".repeat(64), batch: body, effects: [{ ...original.effects[0], after: { ...original.effects[0].after, task: body.actions[0].task, estimate_kind: body.actions[0].estimate_kind } }] };
    state.proposals = [revised, { ...original, status: "superseded" }];
    return route.fulfill({ json: revised });
  });
  await page.goto(`/workspace/ai?chat=${chatId}`);
  const proposals = page.getByRole("region", { name: "Предложения действий" });
  await expect(proposals.getByText("Read similar chapter", { exact: true })).toBeVisible();
  await expect(proposals.getByText(/Продолжительность предложена как оценка/)).toBeVisible();
  await expect(proposals.getByText(/Deadline is unclear/)).toBeVisible();
  expect(state.proposalCommits).toBe(0);
  await proposals.getByRole("button", { name: "Уточнить задачи" }).click();
  const editor = page.getByRole("dialog", { name: "Уточнить предложенные задачи" });
  await editor.getByLabel("Название", { exact: true }).fill("Read corrected chapter");
  await editor.getByLabel("Осталось работы, мин", { exact: true }).fill("30");
  await editor.getByRole("button", { name: "Подготовить новый просмотр" }).click();
  await expect(editor).toHaveCount(0);
  expect(state.proposalCommits).toBe(0);
  await expect(proposals.getByText("Read corrected chapter", { exact: true })).toBeVisible();
  await proposals.getByRole("button", { name: "Применить всё", exact: true }).click();
  await expect(proposals.getByText("Все изменения применены", { exact: true })).toBeVisible();
  expect(state.proposalCommits).toBe(1);
  expect(state.writes.find(item => item.path.endsWith("/decision"))?.body?.digest).toBe("c".repeat(64));
});

test("AI plan preview requires explicit partial acceptance and blocks unverified coverage", async ({ page }) => {
  const state = await mockAi(page);
  const proposal = actionProposal();
  proposal.batch = { actions: [{ operation: "task_plan_apply", plan_id: "plan", digest: "b".repeat(64), accept_partial: true }] };
  proposal.effects = [{ operation: "task_plan_apply", target_id: "plan", before: null, warnings: [], after: { id: "plan", digest: "b".repeat(64), expires_at: "2030-01-01T12:00:00Z", timezone: "UTC", status: "pending", verified: true, sessions: [{ task_id: "task", starts_at: "2026-10-17T09:00:00Z", ends_at: "2026-10-17T09:45:00Z", retained_id: null }], task_titles: { task: "Read chapter" }, cancelled_sessions: [], unplaced: [{ task_id: "task", minutes: 45, reason: "not_placed_in_allowed_windows" }], warnings: [] } }];
  state.proposals = [proposal];
  await page.goto(`/workspace/ai?chat=${chatId}`);
  const apply = page.getByRole("button", { name: "Применить всё", exact: true });
  await expect(apply).toBeDisabled();
  await page.getByLabel("Подтверждаю частичный план и показанный остаток").check();
  await expect(apply).toBeEnabled();
  state.proposals[0].effects[0].after.verified = false;
  await page.reload();
  await page.getByLabel("Подтверждаю частичный план и показанный остаток").check();
  await expect(page.getByText("Условный план. Применение недоступно.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Применить всё", exact: true })).toBeDisabled();
  expect(state.proposalCommits).toBe(0);
});

test("AI labels web evidence and opens only the retrieved public source", async ({ page }) => {
  const state = await mockAi(page);
  const web = { ...reference, source: "web", id: "a".repeat(64), version: 0,
    title: "Дисперсия — внешний источник", url: "https://example.org/variance",
    retrieved_at: "2026-10-29T10:00:00Z" };
  state.messages.push({ id: "web-answer", sequence: 1, role: "assistant",
    content: `В конспекте определения нет. Из интернета: дисперсия — мера разброса. [source:${web.id}]`,
    sources: [web] });
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await expect(page.getByRole("button", { name: `Из интернета: ${web.title}` })).toBeVisible();
  await page.getByRole("button", { name: web.title, exact: true }).click();
  const viewer = page.getByRole("dialog", { name: "Источник из интернета" });
  await expect(viewer.getByText("Внешний источник. Его содержание не является частью твоих документов.")).toBeVisible();
  const link = viewer.getByRole("link", { name: "Открыть источник" });
  await expect(link).toHaveAttribute("href", web.url);
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(state.writes.filter(item => item.path.endsWith("/sources/read"))).toHaveLength(0);
  await page.screenshot({ path: test.info().outputPath("web-source.png"), fullPage: true });
});
