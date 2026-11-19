import { expect, test } from "@playwright/test";
import { mockWorkspace, navigateSection } from "./workspace-fixtures";

const material = {
  id: "88888888-2222-4333-8444-555555555555", title: "Конспект по философии",
  kind: "file", filename: "lecture.docx", size_bytes: 3000, url: null,
  status: "ready", version: 3, error_code: null, trashed_at: null,
};

for (const width of [1440, 390]) {
  test(`document reader supports text, pagination, font size and keyboard at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    const workspace = await mockWorkspace(page);
    await page.route("**/api/v1/materials**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith("/storage")) return route.fulfill({ json: { used_bytes: 3000, limit_bytes: 1073741824 } });
      if (url.pathname.endsWith("/text")) return route.fulfill({ json: {
        material_id: material.id, version: 3, title: material.title,
        offset: Number(url.searchParams.get("offset")), total_characters: 2100,
        text: url.searchParams.get("offset") === "0" ? "Философия начинается с вопроса.\n\n<script>Это безопасный текст</script>" : "Последний фрагмент 🙂",
      } });
      return route.fulfill({ json: url.pathname.endsWith(material.id) ? material : { items: [material] } });
    });
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
    await navigateSection(page, "Материалы");
    await page.getByRole("button", { name: "Читать", exact: true }).click();
    const reader = page.getByRole("dialog", { name: `Чтение: ${material.title}` });
    await expect(reader.getByRole("article")).toContainText("Философия начинается");
    await expect(reader.getByRole("article")).toContainText("<script>");
    await expect(reader.locator("script")).toHaveCount(0);
    await reader.getByRole("button", { name: "Увеличить текст" }).click();
    await expect(reader.getByRole("article")).toHaveCSS("font-size", "20px");
    await expect(reader.getByRole("link", { name: "Скачать оригинал" })).toHaveAttribute("href", `/api/v1/materials/${material.id}/content`);
    const bounds = await reader.boundingBox();
    expect(bounds!.width).toBeLessThanOrEqual(width);
    expect(await reader.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`reader-${width}.png`) });
    await reader.getByRole("button", { name: "Далее", exact: true }).click();
    await expect(reader.getByRole("article")).toContainText("Последний фрагмент 🙂");
    await expect(reader.getByRole("button", { name: "Далее", exact: true })).toBeDisabled();
    await reader.getByRole("button", { name: "Назад", exact: true }).click();
    await expect(reader.getByRole("article")).toContainText("Философия начинается");
    await reader.getByRole("button", { name: "Увеличить текст" }).focus();
    await page.keyboard.press("Escape");
    await expect(reader).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Читать", exact: true })).toBeFocused();
    expect(workspace.writes).toEqual([]);
  });
}

test("reader handles processing, empty text, retry and PDF originals", async ({ page }) => {
  await mockWorkspace(page);
  let status = "processing";
  let filename = "lecture.docx";
  let textError = false;
  let textBody = "";
  let contentReads = 0;
  await page.route("**/api/v1/materials**", async route => {
    const url = new URL(route.request().url());
    const current = { ...material, status, filename };
    if (url.pathname.endsWith("/storage")) return route.fulfill({ json: { used_bytes: 3000, limit_bytes: 1073741824 } });
    if (url.pathname.endsWith("/text")) return textError
      ? route.fulfill({ status: 503, json: {} })
      : route.fulfill({ json: { text: textBody, offset: 0, total_characters: textBody.length, version: 3 } });
    if (url.pathname.endsWith("/content")) {
      contentReads++;
      return route.fulfill({ contentType: "application/octet-stream", body: "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF" });
    }
    return route.fulfill({ json: url.pathname.endsWith(material.id) ? current : { items: [current] } });
  });
  await page.goto("/workspace");
  await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
  await navigateSection(page, "Материалы");
  const open = () => page.getByRole("button", { name: "Читать", exact: true }).click();
  const reader = page.getByRole("dialog", { name: `Чтение: ${material.title}` });
  await open();
  await expect(reader.getByText("Готовим документ к чтению")).toBeVisible();
  status = "ready";
  await page.clock.runFor(3100);
  await expect(reader.getByText("В документе нет доступного текста.", { exact: false })).toBeVisible();
  await reader.getByRole("button", { name: "Закрыть", exact: true }).click();
  textError = true;
  await open();
  await page.clock.runFor(10000);
  await expect(reader.getByRole("alert")).toBeVisible();
  textError = false;
  textBody = "Текст снова доступен";
  await reader.getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(reader.getByRole("article")).toContainText(textBody);
  await reader.getByRole("button", { name: "Закрыть", exact: true }).click();
  filename = "lecture.pdf";
  await page.reload();
  await expect(page.locator(".resource-copy")).toContainText("lecture.pdf");
  await open();
  await expect(reader.locator("iframe")).toHaveAttribute("src", /^blob:/);
  expect(contentReads).toBe(1);
  await reader.getByRole("button", { name: "Закрыть", exact: true }).click();
});
