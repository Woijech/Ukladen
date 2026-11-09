import { expect, type Page } from "@playwright/test";

export async function checkWorkspaceVisuals(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
  const failures = await page.evaluate(() => {
    const rgba = (value: string) => (value.match(/[\d.]+/g) ?? []).map(Number);
    const composite = (front: number[], back: number[]) => {
      const alpha = front[3] ?? 1;
      return front.slice(0, 3).map((channel, index) => channel * alpha + back[index] * (1 - alpha));
    };
    const luminance = (color: number[]) => color.reduce((total, channel, index) => {
      const s = channel / 255;
      return total + (s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4) * [0.2126, 0.7152, 0.0722][index];
    }, 0);
    const failures: { text: string; ratio: number; color: string; background: number[] }[] = [];
    for (const element of document.querySelectorAll<HTMLElement>("body *")) {
      const text = [...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join("").trim();
      if (!text || !element.checkVisibility() || element.closest("script, style, svg, [aria-hidden=true], .sr-only, .visually-hidden, :disabled")) continue;
      const style = getComputedStyle(element);
      const ancestors: HTMLElement[] = [];
      for (let parent: HTMLElement | null = element; parent; parent = parent.parentElement) ancestors.unshift(parent);
      const background = ancestors.reduce((color, parent) => composite(rgba(getComputedStyle(parent).backgroundColor), color), [255, 255, 255]);
      const foreground = composite(rgba(style.color), background);
      const l1 = luminance(foreground), l2 = luminance(background);
      const ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
      const large = parseFloat(style.fontSize) >= 24 || (parseFloat(style.fontSize) >= 18.66 && parseInt(style.fontWeight) >= 700);
      if (ratio < (large ? 3 : 4.5)) failures.push({ text: text.slice(0, 80), ratio, color: style.color, background });
    }
    return failures;
  });
  expect(failures, "Visible text meets AA contrast on its rendered background").toEqual([]);
}
