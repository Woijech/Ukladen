import { expect, test, type Page } from "@playwright/test";
import { uniqueAnswerSources, type Source } from "../src/app/workspace/panels/ai-api";
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
  await expect(page.locator(".ai-citations")).toBeVisible();
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
    expect(writes.at(-1)?.body).toEqual({ material_id: materialId, offset: 200 });
    await page.keyboard.press("Escape");
    await answer.locator(".ai-inline-citation").nth(1).click();
    await expect(page.getByRole("dialog")).toContainText("Текущий фрагмент");
    expect(writes.at(-1)?.body).toEqual({ material_id: otherId, offset: 900 });
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
  await mockAnswer(page, [reference, { ...reference }, second, { ...second }], "Два разных документа.");
  await expect(page.locator(".ai-citations").getByRole("button", { name: reference.title, exact: true })).toHaveCount(2);
});
