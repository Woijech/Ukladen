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

test("desktop chat history collapses without remounting the conversation or submitting a draft", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const writes = await conversation(page);
  const draft = page.getByLabel("Сообщение AI");
  await draft.fill("Черновик без отправки");
  const chat = page.getByRole("region", { name: "Переписка" });
  const expandedWidth = (await chat.boundingBox())!.width;
  const toggle = page.getByRole("button", { name: "Свернуть список чатов", exact: true });
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await toggle.click();
  const expand = page.getByRole("button", { name: "Развернуть список чатов", exact: true });
  await expect(expand).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByRole("complementary", { name: "История чатов" })).toHaveCount(0);
  await expect.poll(async () => (await chat.boundingBox())!.width).toBeGreaterThan(expandedWidth + 200);
  await expect(draft).toHaveValue("Черновик без отправки");
  await expect(page.getByRole("log")).toContainText("Сохранённый ответ без генерации");
  await expand.focus();
  await page.keyboard.press("Enter");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("complementary", { name: "История чатов" })).toBeVisible();
  await expect(draft).toHaveValue("Черновик без отправки");
  expect(writes).toEqual([]);
});

test("history collapse respects reduced motion and does not hide mobile history", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await conversation(page);
  await expect(page.locator(".ai-layout")).toHaveCSS("transition-duration", "0s");
  await page.getByRole("button", { name: "Свернуть список чатов", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "История чатов", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "История чатов", exact: true })).toContainText("План исследования");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "История чатов", exact: true })).toBeFocused();
});

for (const width of [320, 390, 1440]) {
  test(`compact composer retains options, keyboard focus and draft without submission at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await conversation(page);
    const draft = page.getByLabel("Сообщение AI");
    await draft.fill("Черновик с выбранными параметрами");
    const send = page.getByRole("button", { name: "Отправить", exact: true });
    await expect(send).toHaveText("");
    const size = await send.boundingBox();
    expect(size!.width).toBeLessThanOrEqual(44);
    expect(size!.height).toBe(size!.width);
    const options = page.getByRole("button", { name: "Параметры ответа", exact: true });
    const panel = page.getByRole("region", { name: "Настройки ответа", exact: true });
    await options.focus();
    await page.keyboard.press("Enter");
    await expect(options).toHaveAttribute("aria-expanded", "true");
    await expect(panel).toBeVisible();
    await page.getByLabel("Только мои источники", { exact: true }).check();
    await page.getByLabel("Разобрать документы целиком", { exact: true }).check();
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(options).toBeFocused();
    await expect(options).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByLabel("Активные параметры ответа")).toContainText("Только мои источники");
    await expect(page.getByLabel("Активные параметры ответа")).toContainText("Полный разбор");
    await options.click();
    await expect(page.getByLabel("Только мои источники", { exact: true })).toBeChecked();
    await expect(page.getByLabel("Разобрать документы целиком", { exact: true })).toBeChecked();
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      if (!await panel.isVisible()) await options.click();
      await page.screenshot({ path: info.outputPath(`composer-options-${theme}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      const box = (await panel.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
    }
    await page.getByRole("heading", { name: "План исследования", exact: true }).click();
    await expect(panel).toBeHidden();
    await expect(draft).toHaveValue("Черновик с выбранными параметрами");
    await draft.dispatchEvent("keydown", { key: "Enter", ctrlKey: true, isComposing: true });
    expect(writes).toEqual([]);
  });
}

for (const width of [390, 1440]) {
  test(`floating composer closes only its settings on Escape and retains the draft at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const writes = await conversation(page);
    await page.goto("/workspace");
    await page.getByRole("button", { name: "Открыть AI-помощника", exact: true }).click();
    const assistant = page.getByRole("dialog", { name: "Помощник", exact: true });
    await expect(assistant).toBeVisible();
    await assistant.getByRole("button", { name: "История чатов", exact: true }).click();
    await page.getByRole("dialog", { name: "История чатов", exact: true }).getByRole("button", { name: /^План исследования/ }).click();
    const draft = assistant.getByLabel("Сообщение AI");
    await draft.fill("Черновик в помощнике");
    const options = assistant.getByRole("button", { name: "Параметры ответа", exact: true });
    await options.click();
    const panel = page.getByRole("region", { name: "Настройки ответа", exact: true });
    await page.getByLabel("Только мои источники", { exact: true }).check();
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(assistant).toBeVisible();
    await expect(options).toBeFocused();
    await options.click();
    await assistant.getByRole("button", { name: "Отправить", exact: true }).focus();
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(assistant).toBeVisible();
    const surface = (await assistant.locator(".ai-composer-surface").boundingBox())!;
    const controls = await Promise.all([
      assistant.getByRole("button", { name: /^Источники:/ }).boundingBox(),
      options.boundingBox(),
      assistant.getByRole("button", { name: "Отправить", exact: true }).boundingBox(),
    ]);
    for (const box of controls) {
      expect(box!.x).toBeGreaterThanOrEqual(surface.x);
      expect(box!.x + box!.width).toBeLessThanOrEqual(surface.x + surface.width);
    }
    const [sources, settings] = controls;
    const overlapX = Math.min(sources!.x + sources!.width, settings!.x + settings!.width) - Math.max(sources!.x, settings!.x);
    const overlapY = Math.min(sources!.y + sources!.height, settings!.y + settings!.height) - Math.max(sources!.y, settings!.y);
    expect(overlapX > 1 && overlapY > 1, "Source and response controls must not overlap").toBe(false);
    await page.screenshot({ path: info.outputPath("floating-composer.png"), fullPage: true });
    await assistant.getByRole("button", { name: "Свернуть помощника", exact: true }).click();
    await page.getByRole("button", { name: "Открыть AI-помощника", exact: true }).click();
    await expect(draft).toHaveValue("Черновик в помощнике");
    await options.click();
    await expect(page.getByLabel("Только мои источники", { exact: true })).toBeChecked();
    expect(writes).toEqual([]);
  });
}
