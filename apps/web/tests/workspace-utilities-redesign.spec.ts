import { expect, test } from "@playwright/test";
import { mockWorkspace, navigateSection } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

test("profile drafts survive errors and guard navigation until saved", async ({ page }) => {
  const state = await mockWorkspace(page);
  let current = { id: state.userId, email: "test@example.com", display_name: null as string | null, timezone: state.timezone, locale: "ru", avatar_url: null, updated_at: "2026-10-16T08:00:00Z" };
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/v1/users/me", async route => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON();
      expect(route.request().headers()["x-csrf-token"]).toBe("c".repeat(43));
      writes.push(body);
      if (writes.length === 1) return route.fulfill({ status: 503, json: {} });
      current = { ...current, ...body };
      state.timezone = current.timezone;
    }
    return route.fulfill({ json: current });
  });
  await page.goto("/workspace?section=settings");
  await page.getByLabel("Имя", { exact: true }).fill("Новое имя");
  await page.getByLabel("Часовой пояс календаря", { exact: true }).selectOption("America/New_York");
  await navigateSection(page, "Календарь");
  await expect(page.getByRole("dialog", { name: "Несохранённые изменения", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Имя", { exact: true })).toHaveValue("Новое имя");
  await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click();
  await expect(page.locator(".profile-form").getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Часовой пояс календаря", { exact: true })).toHaveValue("America/New_York");
  await page.getByRole("button", { name: "Сохранить профиль", exact: true }).click();
  await expect(page.locator(".profile-form").getByRole("status")).toContainText("Сохранено");
  expect(writes).toEqual([{ display_name: "Новое имя", timezone: "America/New_York" }, { display_name: "Новое имя", timezone: "America/New_York" }]);
  await navigateSection(page, "Календарь");
  await expect(page.locator(".calendar-card")).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("theme choices apply directly without profile writes even when storage is unavailable", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.addInitScript(() => { Storage.prototype.setItem = () => { throw new Error("Storage unavailable"); }; });
  await page.goto("/workspace?section=settings");
  const choices = page.getByRole("group", { name: "Оформление приложения", exact: true });
  for (const [label, value] of [["Тёмная", "dark"], ["Светлая", "light"], ["Системная", "system"]]) {
    await choices.getByRole("button", { name: label, exact: true }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", value);
    await expect(choices.getByRole("button", { name: label, exact: true })).toHaveAttribute("aria-pressed", "true");
  }
  expect(state.writes).toEqual([]);
});

for (const width of [320, 390, 834, 1440]) {
  test(`settings and utility home fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    await mockWorkspace(page);
    await page.goto("/workspace?section=settings");
    for (const theme of ["light", "dark"]) {
      await page.getByRole("group", { name: "Оформление приложения", exact: true }).getByRole("button", { name: theme === "light" ? "Светлая" : "Тёмная", exact: true }).click();
      await expect(page.locator(".skeleton-stack")).toHaveCount(0);
      await page.evaluate(() => window.scrollTo(0, 0));
      const skip = (await page.locator(".skip-link").boundingBox())!;
      expect(skip.y + skip.height).toBeLessThanOrEqual(0);
      await page.screenshot({ path: info.outputPath(`settings-${theme}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await navigateSection(page, "Главная");
      await expect(page.getByRole("heading", { name: "Продолжить работу", exact: true })).toBeVisible();
      await page.screenshot({ path: info.outputPath(`home-${theme}.png`), fullPage: true, animations: "disabled" });
      await checkWorkspaceVisuals(page);
      await page.getByRole("button", { name: "Открыть календарь", exact: true }).click();
      await expect(page.locator(".calendar-card")).toBeVisible();
      await navigateSection(page, "Настройки");
    }
  });
}
