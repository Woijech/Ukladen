import { expect, test } from "@playwright/test";
import { mockWorkspace } from "./workspace-fixtures";
import { checkWorkspaceVisuals } from "./design-checks";

for (const width of [320, 390, 834, 1440]) {
  test(`public and auth surfaces fit both themes at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const state = await mockWorkspace(page);
    state.authenticated = false;
    await page.route("**/api/health/live", route => route.fulfill({ json: { status: "ok" } }));
    for (const theme of ["light", "dark"]) {
      await page.goto("/");
      const toggle = page.getByRole("button", { name: /Тема:/ });
      while ((await page.locator("html").getAttribute("data-theme")) !== theme) await toggle.click();
      for (const path of ["/", "/workspace", "/auth/reset-password", "/auth/verify-email", "/auth/error"]) {
        await page.goto(path);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await page.screenshot({ path: info.outputPath(`${path.replaceAll("/", "_") || "home"}-${theme}.png`), fullPage: true, animations: "disabled" });
        await checkWorkspaceVisuals(page);
      }
    }
    expect(errors).toEqual([]);
    expect(state.writes).toEqual([]);
  });
}
