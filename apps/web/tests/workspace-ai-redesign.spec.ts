import { expect, test, type Page } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

const chatId = "11111111-2222-4333-8444-555555555555";
async function conversation(page: Page) {
  await mockWorkspace(page);
  const writes: string[] = [];
  await page.route("**/api/v1/notes/pages?**", route => route.fulfill({ json: { items: [] } }));
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
      writeText: async (text: string) => { (window as Window & { copied?: string }).copied = text; },
    } });
  });
  const chat = { id: chatId, title: "План исследования", provider: "fake", model: "synthetic", offering_id: null, connection_id: null };
  await page.route("**/api/v1/ai/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== "GET") { writes.push(path); throw new Error(`Unexpected write: ${path}`); }
    if (path.endsWith("/diagnostics/access")) return route.fulfill({ json: { allowed: false } });
    if (path.endsWith("/conversations")) return route.fulfill({ json: { items: [chat] } });
    if (path.endsWith("/state")) return route.fulfill({ json: { conversation: chat, run: null } });
    if (path.endsWith("/messages")) return route.fulfill({ json: { items: [{ id: "answer", sequence: 1, role: "assistant", content: "Сохранённый ответ без генерации", sources: [] }] } });
    if (path.endsWith("/proposals")) return route.fulfill({ json: [] });
    throw new Error(`Unexpected read: ${path}`);
  });
  await page.goto(`/workspace/ai?chat=${chatId}`);
  await expect(page.getByRole("log")).toContainText("Сохранённый ответ без генерации");
  return writes;
}

for (const width of [320, 390, 768, 834, 1440]) {
  test(`focused AI transcript and history fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await conversation(page);
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      if (width <= 900) {
        const trigger = page.getByRole("button", { name: "История чатов", exact: true });
        await trigger.click();
        const history = page.getByRole("dialog", { name: "История чатов", exact: true });
        await expect(history).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(trigger).toBeFocused();
      }
      await page.screenshot({ path: info.outputPath(`chat-${theme}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await page.getByRole("button", { name: "Копировать ответ 1", exact: true }).focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("status").filter({ hasText: "Сообщение скопировано" })).toBeVisible();
      expect(await page.evaluate(() => (window as Window & { copied?: string }).copied)).toBe("Сохранённый ответ без генерации");
    }
    expect(writes).toEqual([]);
  });
}

test("explicit empty AI context is distinct from automatic scope and opening history preserves the message draft", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await conversation(page);
  await page.getByLabel("Сообщение AI").fill("Не отправлять");
  await page.getByRole("button", { name: "История чатов", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Сообщение AI")).toHaveValue("Не отправлять");
  await page.getByRole("button", { name: "Источники: автоматически", exact: true }).click();
  await page.getByLabel("Все мои источники автоматически", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Применить", exact: true }).click();
  await expect(page.getByRole("button", { name: "Источники: без источников", exact: true })).toBeVisible();
  expect(writes).toEqual([]);
});

test("clipboard failure keeps the AI answer readable and offers manual copying", async ({ page }) => {
  const writes = await conversation(page);
  await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw new Error("Clipboard unavailable"); }; });
  await page.getByRole("button", { name: "Копировать ответ 1", exact: true }).click();
  await expect(page.getByText("Не удалось скопировать. Выдели текст и скопируй его вручную.", { exact: true })).toBeVisible();
  await expect(page.getByRole("log")).toContainText("Сохранённый ответ без генерации");
  expect(writes).toEqual([]);
});
