import { expect, test } from "@playwright/test";
import { mockWorkspace, navigateSection } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

test("contextual help closes without dismissing a task draft", async ({ page }) => {
  const state = await mockWorkspace(page);
  await page.goto("/workspace");
  await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
  await navigateSection(page, "Задачи");
  await page.getByRole("button", { name: "Новая задача" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Название", { exact: true }).fill("Keep this draft");
  const trigger = dialog.getByRole("button", { name: "Как работают сроки и подзадачи" });
  const explanation = dialog.getByRole("note").filter({ hasText: "Срок не занимает время" });
  await expect(explanation).toBeHidden();
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(explanation).toBeVisible();
  await explanation.focus();
  await page.keyboard.press("Escape");
  await expect(explanation).toBeHidden();
  await expect(trigger).toBeFocused();
  await expect(dialog.getByLabel("Название", { exact: true })).toHaveValue("Keep this draft");
  await trigger.click();
  await dialog.getByLabel("Название", { exact: true }).click();
  await expect(explanation).toBeHidden();
  expect(state.writes).toEqual([]);
});

for (const theme of ["light", "dark"]) {
  test(`long calendar help fits a narrow viewport in ${theme} theme`, async ({ page }, info) => {
    await page.setViewportSize({ width: 375, height: 667 });
    const state = await mockWorkspace(page);
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
    await page.evaluate(value => document.documentElement.setAttribute("data-theme", value), theme);
    await page.getByRole("button", { name: "Справка по управлению календарём" }).click();
    const explanation = page.getByRole("note").filter({ hasText: "С клавиатуры: ↑ ↓ выбрать время" });
    await expect(explanation).toBeVisible();
    await explanation.focus();
    await page.keyboard.press("End");
    await expect.poll(() => explanation.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await page.setViewportSize({ width: 320, height: 568 });
    await page.screenshot({ path: info.outputPath(`calendar-help-${theme}.png`), animations: "disabled" });
    const box = await explanation.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(12);
    expect(box!.x + box!.width).toBeLessThanOrEqual(308);
    expect(box!.y).toBeGreaterThanOrEqual(12);
    expect(box!.y + box!.height).toBeLessThanOrEqual(556);
    await checkWorkspaceVisuals(page);
    await page.keyboard.press("Escape");
    await expect(explanation).toBeHidden();
    expect(state.writes).toEqual([]);
  });
}
