import { expect, test, type Page } from "@playwright/test";
import { uniqueAnswerSources, type Source } from "../src/app/workspace/panels/ai-api";
import { citedAnswerSources, resolveSourceCitation } from "../src/app/workspace/panels/ai-source-citations";
import { mockWorkspace } from "./workspace-fixtures";

const chatId = "11111111-2222-4333-8444-555555555555";
const materialId = "22222222-2222-4333-8444-555555555555";
const otherId = "33333333-2222-4333-8444-555555555555";
const reference: Source = {
  source: "material", id: materialId, title: "Лабораторная работа 1.pdf",
  version: 1, locator: "page:7;chars:200:400", parent_id: null,
};

test("answer source summaries keep the first reference without mutating fragment evidence", () => {
  const renamed = { ...reference, title: "Renamed document", version: 2, locator: "page:8;chars:600:800", fingerprint: "a".repeat(64) };
  const another = { ...reference, id: otherId };
  const sources = Object.freeze([Object.freeze(reference), Object.freeze(renamed), another, reference]);
  const unique = uniqueAnswerSources(sources);
  expect(unique).toEqual([reference, another]);
  expect(unique[0]).toBe(reference);
  expect(sources).toEqual([reference, renamed, another, reference]);
  expect(uniqueAnswerSources([])).toEqual([]);
});

test("answer source summaries distinguish source types and parent scopes rather than titles", () => {
  const page = { ...reference, source: "page" as const };
  const record = { ...reference, source: "database_record" as const, parent_id: materialId };
  const otherParent = { ...record, parent_id: otherId };
  const web = { ...reference, source: "web" as const, url: "https://example.org/encapsulation", retrieved_at: "2030-11-04T09:00:00Z" };
  expect(uniqueAnswerSources([reference, page, record, otherParent, web, { ...web }]))
    .toEqual([reference, page, record, otherParent, web]);
});

test("inline citations select the actual evidence page rather than the first document fragment", () => {
  const first = { ...reference, locator: "page:4;chars:633:1041" };
  const slide = { ...reference, locator: "slide:7;chars:2300:2400" };
  const sources = [first, reference, slide];
  expect(resolveSourceCitation(`[source:${materialId}]`, sources)).toEqual({ index: 0, label: reference.title });
  expect(resolveSourceCitation(`[source:${materialId}, page:7]`, sources)).toEqual({ index: 1, label: `${reference.title} · стр. 7` });
  expect(resolveSourceCitation(`[source: ${materialId} , page: 4 ]`, sources)).toEqual({ index: 0, label: `${reference.title} · стр. 4` });
  expect(resolveSourceCitation(`[source:${materialId}, slide:7]`, sources)).toEqual({ index: 2, label: `${reference.title} · слайд 7` });
});

test("inline citations never invent missing pages or treat a database schema version as a PDF page", () => {
  const database: Source = { ...reference, source: "database_record", locator: "schema:1:page:7", parent_id: otherId };
  for (const marker of [
    `[source:${otherId}, page:7]`, `[source:${materialId}, page:8]`,
    `[source:${materialId}, page:0]`, `[source:${materialId}, page:-7]`,
    `[source:${materialId}, page:7, extra:true]`, `[source:${materialId},\npage:7]`,
  ]) expect(resolveSourceCitation(marker, [reference])).toBeNull();
  expect(resolveSourceCitation(`[source:${materialId}, page:7]`, [database])).toBeNull();
});

test("answer summaries include only cited evidence in citation order and preserve the first cited page", () => {
  const first = Object.freeze({ ...reference, locator: "page:4;chars:633:1041" });
  const second = Object.freeze({ ...reference, id: otherId });
  const sources = Object.freeze([first, Object.freeze(reference), second]);
  const cited = citedAnswerSources(`Пример [source:${otherId}]. Определение [source:${materialId}, page:7]. Ещё [source:${materialId}, page:4].`, sources);
  expect(cited).toEqual([second, reference]);
  expect(cited[1]).toBe(reference);
  expect(sources).toEqual([first, reference, second]);
  expect(citedAnswerSources("Общие знания модели. Ответ без ссылок.", sources)).toEqual([]);
});

test("answer summaries ignore literal code, image labels, external link labels and unsupported markers", () => {
  const marker = `[source:${materialId}]`;
  const text = `\`${marker}\`\n\n\`\`\`text\n${marker}\n\`\`\`\n\n[${marker}](https://example.org)\n\n![${marker}](https://example.org/image.png)\n\n[source:${otherId}]\n\n[source:${materialId}, page:500]`;
  expect(citedAnswerSources(text, [reference])).toEqual([]);
});

test("answer summaries follow rendered footnotes but ignore unused definitions and linked reference labels", () => {
  const marker = `[source:${materialId}]`;
  expect(citedAnswerSources(`Ответ.\n\n[^unused]: ${marker}`, [reference])).toEqual([]);
  expect(citedAnswerSources(`Ответ[^used].\n\n[^used]: ${marker}`, [reference])).toEqual([reference]);
  expect(citedAnswerSources(`[${marker}][manual]\n\n[manual]: https://example.org`, [reference])).toEqual([]);
});

async function mockAnswer(page: Page, sources: Source[], content: string) {
  await mockWorkspace(page);
  const writes: { path: string; body: Record<string, unknown> }[] = [];
  const chat = { id: chatId, title: "Источники", provider: "fake", model: "synthetic", offering_id: null, connection_id: null };
  await page.route("**/api/v1/ai/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path.endsWith("/sources/read")) {
      expect(request.headers()["x-csrf-token"]).toBe("c".repeat(43));
      writes.push({ path, body: request.postDataJSON() });
      return route.fulfill({ json: {
        status: "ok", coverage: "partial", next_offset: null, warnings: [],
        sources, data: { text: "Текущий фрагмент" },
      } });
    }
    if (request.method() !== "GET") throw new Error(`Unexpected write: ${path}`);
    if (path.endsWith("/diagnostics/access")) return route.fulfill({ json: { allowed: false } });
    if (path.endsWith("/conversations")) return route.fulfill({ json: { items: [chat] } });
    if (path.endsWith("/state")) return route.fulfill({ json: { conversation: chat, run: null } });
    if (path.endsWith("/messages")) return route.fulfill({ json: { items: [
      { id: "answer", sequence: 1, role: "assistant", content, sources },
    ] } });
    if (path.endsWith("/proposals")) return route.fulfill({ json: [] });
    if (path.endsWith("/index")) return route.fulfill({ json: { status: "ready", version: 1 } });
    throw new Error(`Unexpected read: ${path}`);
  });
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await expect(page.locator('[data-ai-message-id="answer"]')).toBeVisible();
  return writes;
}

for (const width of [390, 1440]) {
  test(`answer sources deduplicate document fragments and preserve inline preview targets at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const second: Source = { ...reference, id: otherId, title: "стата3 объяснение", locator: "chars:900:1100" };
    const sources = [reference, ...Array.from({ length: 20 }, (_, index) => ({
      ...reference, locator: `page:${index + 8};chars:${600 + index * 200}:${800 + index * 200}`,
    })), second, { ...second, locator: "chars:1800:2000" }];
    const writes = await mockAnswer(page, sources,
      `Определение [source:${materialId}]. Пример [source:${otherId}]. Ещё пример [source:${materialId}].`);
    const answer = page.locator('[data-ai-message-id="answer"]');
    const summary = answer.locator(".ai-citations");
    await expect(summary.getByRole("button")).toHaveText([reference.title, second.title]);
    await expect(answer.locator(".ai-inline-citation")).toHaveCount(3);
    expect(writes).toEqual([]);

    await summary.getByRole("button", { name: reference.title, exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText("Страница PDF 7");
    await expect.poll(() => writes.at(-1)?.body).toEqual({ material_id: materialId, offset: 200 });
    await page.keyboard.press("Escape");
    await answer.locator(".ai-inline-citation").nth(1).click();
    await expect(page.getByRole("dialog")).toContainText("Текущий фрагмент");
    await expect.poll(() => writes.at(-1)?.body).toEqual({ material_id: otherId, offset: 900 });
    expect(writes).toHaveLength(2);
    await page.keyboard.press("Escape");
    await page.screenshot({ path: info.outputPath("unique-answer-sources.png"), fullPage: true, animations: "disabled" });
    await page.reload();
    await expect(page.locator(".ai-citations").getByRole("button")).toHaveCount(2);
    expect(writes).toHaveLength(2);
  });
}

test("answer sources keep different documents with the same title", async ({ page }) => {
  const second = { ...reference, id: otherId };
  await mockAnswer(page, [reference, { ...reference }, second, { ...second }], `Два разных документа: [source:${materialId}], [source:${otherId}].`);
  await expect(page.locator(".ai-citations").getByRole("button", { name: reference.title, exact: true })).toHaveCount(2);
});

for (const width of [390, 1440]) {
  test(`page-qualified citations render as buttons and open their original evidence ranges at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const pages = [
      { page: 4, offset: 633, end: 1041 }, { page: 9, offset: 2305, end: 2423 },
      { page: 7, offset: 1516, end: 1922 }, { page: 6, offset: 1172, end: 1515 },
    ];
    const sources: Source[] = [
      ...pages.map(({ page, offset, end }) => ({ ...reference, locator: `page:${page};chars:${offset}:${end}` })),
      { ...reference, id: otherId, title: "Другой документ" },
      { ...reference, source: "page", id: chatId, title: "Заметка" },
    ];
    const writes = await mockAnswer(page, sources,
      `Определение [source:${materialId}, page:7].\n\n- Система [source:${materialId}, page:4].\n- Пример [source:${materialId}, page:6].\n- Модель [source:${materialId}, page:9].`);
    const answer = page.locator('[data-ai-message-id="answer"]');
    const inline = answer.locator(".ai-inline-citation");
    await expect(inline).toHaveText([7, 4, 6, 9].map(number => `${reference.title} · стр. ${number}`));
    await expect(answer.locator(".ai-message-text")).not.toContainText("[source:");
    const summary = answer.locator(".ai-citations");
    await expect(summary.getByRole("button")).toHaveText([reference.title]);
    expect(writes).toEqual([]);
    await page.screenshot({ path: info.outputPath("page-citations.png"), fullPage: true, animations: "disabled" });
    await summary.getByRole("button").click();
    await expect(page.getByRole("dialog")).toContainText("Страница PDF 7");
    await expect.poll(() => writes.at(-1)?.body).toEqual({ material_id: materialId, offset: 1516 });
    await page.keyboard.press("Escape");
    for (const [index, number] of [7, 4, 6, 9].entries()) {
      await inline.nth(index).click();
      await expect(page.getByRole("dialog")).toContainText(`Страница PDF ${number}`);
      await expect.poll(() => writes.at(-1)?.body).toEqual({ material_id: materialId, offset: pages.find(item => item.page === number)!.offset });
      await page.keyboard.press("Escape");
    }
    // The footer and first inline citation share a page; query caching may coalesce their reads.
    expect([...new Set(writes.map(item => item.body.offset))]).toEqual([1516, 633, 1172, 2305]);
  });
}

test("unknown page citations and citations in code stay literal and cannot open a fabricated source", async ({ page }) => {
  const unknown = `[source:${materialId}, page:500]`;
  const known = `[source:${materialId}, page:7]`;
  const writes = await mockAnswer(page, [reference], `${unknown}\n\n\`${known}\`\n\n\`\`\`text\n${known}\n\`\`\``);
  const answer = page.locator('[data-ai-message-id="answer"]');
  await expect(answer.locator(".ai-message-text")).toContainText(unknown);
  await expect(answer.locator("code")).toHaveText([known, known]);
  await expect(answer.locator(".ai-inline-citation")).toHaveCount(0);
  await expect(answer.locator(".ai-citations")).toHaveCount(0);
  expect(writes).toEqual([]);
});

for (const width of [390, 1440]) {
  test(`general-knowledge answers hide inherited source evidence without regeneration at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const sources = Array.from({ length: 8 }, (_, index) => ({ ...reference, locator: `page:${index + 1};chars:${index * 200}:${index * 200 + 200}` }));
    const writes = await mockAnswer(page, sources, "**Общие знания модели**\n\nКаталония — регион Испании. В ответе нет ссылок на документы.");
    await expect(page.getByRole("log")).toContainText("Каталония");
    await expect(page.locator(".ai-citations")).toHaveCount(0);
    await expect(page.getByText("Источники ответа", { exact: true })).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("no-uncited-sources.png"), fullPage: true, animations: "disabled" });
    await page.reload();
    await expect(page.getByRole("log")).toContainText("Каталония");
    await expect(page.locator(".ai-citations")).toHaveCount(0);
    expect(writes).toEqual([]);
  });
}

test("mixed answers show only explicit citations rather than filtering by a prose heading", async ({ page }) => {
  const second = { ...reference, id: otherId, title: "Не процитированный документ" };
  const writes = await mockAnswer(page, [second, reference], `**Общие знания модели**\n\nОбъяснение.\n\n**Из твоих материалов**\n\nПример [source:${materialId}, page:7].`);
  await expect(page.locator(".ai-citations").getByRole("button")).toHaveText([reference.title]);
  expect(writes).toEqual([]);
});
