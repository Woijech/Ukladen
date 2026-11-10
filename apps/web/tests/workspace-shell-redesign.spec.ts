import { expect, test } from "@playwright/test";
import { mockWorkspace, navigateSection } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

test("section links survive reload and browser history without API writes", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace?section=tasks");
  await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
  await navigateSection(page, "Заметки");
  await expect(page).toHaveURL(/section=notes/);
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
  await page.goForward();
  await expect(page).toHaveURL(/section=notes/);
  await page.reload();
  await expect(page.locator(".sidebar a[aria-current=page]")).toHaveAttribute("href", "/workspace?section=notes");
  expect(state.writes).toEqual([]);
});

test("palette supports keyboard navigation, focus return and full-text search handoff", async ({ page }) => {
  await mockWorkspace(page);
  const queries: string[] = [];
  await page.route("**/api/v1/search?**", route => {
    queries.push(new URL(route.request().url()).searchParams.get("q")!);
    return route.fulfill({ json: { items: [], limit: 20, offset: 0 } });
  });
  await page.goto("/workspace");
  const trigger = page.getByRole("button", { name: "Поиск по пространству" });
  await trigger.focus();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("combobox", { name: "Раздел или текст для поиска" })).toBeFocused();
  await page.getByRole("combobox", { name: "Раздел или текст для поиска" }).fill("Черновик запроса");
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.getByRole("combobox", { name: "Раздел или текст для поиска" }).fill("Задачи");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/section=tasks/);
  await trigger.click();
  await page.getByRole("combobox", { name: "Раздел или текст для поиска" }).fill("неизвестный текст");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Поиск", exact: true })).toBeVisible();
  await expect(page.getByLabel("Поисковый запрос")).toHaveValue("неизвестный текст");
  await expect.poll(() => queries).toEqual(["неизвестный текст"]);
});

for (const width of [320, 390, 834, 1440]) {
  test(`shell navigation and palette fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await mockWorkspace(page);
    await page.goto("/workspace?section=tasks");
    await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
    for (const theme of ["light", "dark"]) {
      const toggle = page.getByRole("button", { name: /Тема:/ }).first();
      while (await page.locator("html").getAttribute("data-theme") !== theme) await toggle.click();
      await checkWorkspaceVisuals(page);
      await page.screenshot({ path: info.outputPath(`shell-${theme}.png`), fullPage: true, animations: "disabled" });
      if (width < 761) {
        await page.getByRole("button", { name: "Все разделы" }).click();
        const dialog = page.getByRole("dialog", { name: "Навигация", exact: true });
        await dialog.getByRole("searchbox").fill("базы");
        await expect(dialog.getByRole("link", { name: "Базы данных", exact: true })).toBeVisible();
        await dialog.evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
        const box = (await dialog.getByRole("link", { name: "Базы данных", exact: true }).boundingBox())!;
        expect(box.height).toBeGreaterThanOrEqual(44);
        await page.screenshot({ path: info.outputPath(`navigation-${theme}.png`), fullPage: true, animations: "disabled" });
        await page.keyboard.press("Escape");
      }
      await page.getByRole("button", { name: "Поиск по пространству" }).click();
      await expect(page.getByRole("combobox", { name: "Раздел или текст для поиска" })).toBeFocused();
      await checkWorkspaceVisuals(page);
      await page.screenshot({ path: info.outputPath(`palette-${theme}.png`), fullPage: true, animations: "disabled" });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await expect(page.getByRole("dialog")).toHaveCSS("animation-name", "none");
      await page.keyboard.press("Escape");
    }
  });
}

test.describe("touch navigation", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  test("dock and searchable drawer work with taps without writes", async ({ page }) => {
    const state = await mockWorkspace(page);
    await page.goto("/workspace");
    await page.getByRole("navigation", { name: "Быстрые переходы" }).getByRole("link", { name: "Задачи", exact: true }).tap();
    await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Все разделы" }).tap();
    const dialog = page.getByRole("dialog", { name: "Навигация", exact: true });
    await dialog.getByRole("searchbox").fill("такого раздела нет");
    await expect(dialog.getByRole("status")).toContainText("Раздел не найден");
    await expect(dialog.getByRole("link")).toHaveCount(0);
    await dialog.getByRole("searchbox").fill("Заметки");
    await dialog.getByRole("link", { name: "Заметки", exact: true }).tap();
    await expect(page).toHaveURL(/section=notes/);
    expect(state.writes).toEqual([]);
  });
});

test("AI route history remains compatible with workspace section links", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/ai/**", route => route.fulfill({ status: 503, json: { message: "Synthetic unavailable service" } }));
  await page.goto("/workspace/ai");
  await page.getByRole("button", { name: "Использование", exact: true }).click();
  await expect(page).toHaveURL(/\/workspace\/ai\/usage/);
  await navigateSection(page, "Задачи");
  await expect(page.getByRole("heading", { name: "Задачи", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "Твой AI", exact: true })).toBeVisible();
  await expect(page.locator(".ai-tabs button[aria-current]")).toHaveText("Использование");
});
