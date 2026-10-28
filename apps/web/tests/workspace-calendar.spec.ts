import { expect, test, type Page } from "@playwright/test";
import {
  calendarEvent,
  mockWorkspace,
  navigateSection,
} from "./workspace-fixtures";

async function stretch(
  page: Page,
  label: string,
  pixels: number,
  release = true,
) {
  const handle = page.getByRole("slider", { name: label, exact: true });
  await handle.scrollIntoViewIfNeeded();
  const box = await handle.boundingBox();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width / 2,
    box!.y + box!.height / 2 + pixels,
    { steps: 5 },
  );
  if (release) await page.mouse.up();
}

test("navigation starts with three core sections and reveals secondary tools on demand", async ({
  page,
}) => {
  await mockWorkspace(page);
  await page.goto("/workspace");
  const sidebar = page.locator(".sidebar");
  for (const title of ["Календарь", "Заметки", "Задачи"])
    await expect(
      sidebar.getByRole("button", { name: title, exact: true }),
    ).toBeVisible();
  await expect(
    sidebar.getByRole("button", { name: "Материалы", exact: true }),
  ).toHaveCount(0);
  await sidebar.getByRole("button", { name: "Ещё", exact: true }).click();
  await expect(
    sidebar.getByRole("button", { name: "Материалы", exact: true }),
  ).toBeVisible();
  await sidebar.getByRole("button", { name: "Ещё", exact: true }).click();
  await expect(
    sidebar.getByRole("button", { name: "Материалы", exact: true }),
  ).toHaveCount(0);
  await navigateSection(page, "Задачи");
  await expect(
    page.getByRole("heading", { name: "Задачи", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Поиск по пространству" }),
  ).toBeVisible();
});

test("pointer resize previews locally and saves only the changed end with its original version", async ({
  page,
}) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  await page.goto("/workspace");
  await stretch(page, "Изменить окончание: Private plan", 54, false);
  await expect(page.locator(".event-card")).toHaveCSS("height", "108px");
  expect(state.writes).toEqual([]);
  await page.mouse.up();
  await expect
    .poll(() => state.events[0].ends_at)
    .toBe("2026-10-12T12:00:00.000Z");
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0].body).toEqual({
    expected_version: 1,
    ends_at: "2026-10-12T12:00:00.000Z",
  });
  expect(state.events[0].title).toBe("Private plan");
  expect(state.events[0].description).toBe("Private description");
  await expect(
    page.getByRole("article", { name: "Страница события" }),
  ).toHaveCount(0);
  await stretch(page, "Изменить начало: Private plan", 27);
  await expect
    .poll(() => state.events[0].starts_at)
    .toBe("2026-10-12T10:30:00.000Z");
  expect(state.writes[1].body).toEqual({
    expected_version: 2,
    starts_at: "2026-10-12T10:30:00.000Z",
  });
});

test("keyboard resize enforces positive duration and Escape or pointer cancellation never saves", async ({
  page,
}) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  await page.goto("/workspace");
  const end = page.getByRole("slider", {
    name: "Изменить окончание: Private plan",
    exact: true,
  });
  await end.focus();
  for (let i = 0; i < 8; i++) await end.press("ArrowUp");
  expect(Number(await end.getAttribute("aria-valuenow"))).toBe(
    Date.parse(state.events[0].starts_at) + 60_000,
  );
  await end.press("Escape");
  await expect(page.locator(".event-card")).toHaveCSS("height", "54px");
  await stretch(page, "Изменить окончание: Private plan", 54, false);
  await end.dispatchEvent("pointercancel");
  await page.mouse.up();
  await expect(page.locator(".event-card")).toHaveCSS("height", "54px");
  expect(state.writes).toEqual([]);
  await end.focus();
  await end.press("ArrowDown");
  await end.press("Enter");
  await expect
    .poll(() => state.events[0].ends_at)
    .toBe("2026-10-12T11:15:00.000Z");
});

for (const failure of ["conflict", "network"] as const) {
  test(`a ${failure} resize failure restores server geometry and allows a deliberate retry`, async ({
    page,
  }) => {
    const state = await mockWorkspace(page);
    state.events = [calendarEvent()];
    if (failure === "network") state.eventCode = 503;
    await page.goto("/workspace");
    const end = page.getByRole("slider", {
      name: "Изменить окончание: Private plan",
      exact: true,
    });
    await end.focus();
    await end.press("ArrowDown");
    if (failure === "conflict") state.events[0].version = 5;
    await end.press("Enter");
    await expect(page.locator(".inline-error")).toBeVisible();
    await expect(page.locator(".event-card")).toHaveCSS("height", "54px");
    expect(state.events[0].ends_at).toBe("2026-10-12T11:00:00Z");
    state.eventCode = 200;
    await end.focus();
    await end.press("ArrowDown");
    await end.press("Enter");
    await expect
      .poll(() => state.events[0].ends_at)
      .toBe("2026-10-12T11:15:00.000Z");
    expect(state.writes).toHaveLength(2);
    await expect(page.locator(".inline-error")).toHaveCount(0);
  });
}

test("a pending resize cannot submit twice or be mistaken for opening the event", async ({
  page,
}) => {
  const state = await mockWorkspace(page);
  state.events = [calendarEvent()];
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  let requests = 0;
  await page.route("**/api/v1/calendar/personal-events/*", async (route) => {
    requests++;
    await waiting;
    await route.fallback();
  });
  await page.goto("/workspace");
  const end = page.getByRole("slider", {
    name: "Изменить окончание: Private plan",
    exact: true,
  });
  await end.focus();
  await end.press("ArrowDown");
  await end.press("Enter");
  await expect(end).toBeDisabled();
  await page.keyboard.press("Enter");
  await expect.poll(() => requests).toBe(1);
  await expect(page.locator(".event-detail")).toHaveCount(0);
  release();
  await expect(end).toBeEnabled();
  expect(state.writes).toHaveLength(1);
});

test("overnight segments expose only their real boundaries and IIS events have no resize handles", async ({
  page,
}) => {
  const state = await mockWorkspace(page);
  state.events = [
    calendarEvent({
      title: "Night",
      starts_at: "2026-10-12T23:00:00Z",
      ends_at: "2026-10-13T01:00:00Z",
    }),
    calendarEvent({
      id: "official:test",
      source: "official",
      source_event_id: "22222222-2222-4222-8222-222222222222",
      title: "Lesson",
      version: 0,
    }),
  ];
  await page.goto("/workspace");
  const segments = page.locator(".personal-event");
  await expect(segments).toHaveCount(2);
  await expect(
    segments.first().getByRole("slider", { name: /Изменить окончание/ }),
  ).toHaveCount(0);
  await expect(
    segments.last().getByRole("slider", { name: /Изменить начало/ }),
  ).toHaveCount(0);
  await expect(page.locator(".official-event").getByRole("slider")).toHaveCount(
    0,
  );
  await page.locator(".official-event").click();
  await expect(
    page.getByRole("heading", { name: "Lesson", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Изменить событие", exact: true }),
  ).toHaveCount(0);
  expect(state.writes).toEqual([]);
});

test("resizing across a repeated DST hour follows elapsed calendar time and preserves the start", async ({
  page,
}) => {
  const state = await mockWorkspace(page);
  state.timezone = "America/New_York";
  await page.clock.setSystemTime(new Date("2026-11-01T12:00:00Z"));
  state.events = [
    calendarEvent({
      starts_at: "2026-11-01T05:30:37Z",
      ends_at: "2026-11-01T05:45:37Z",
    }),
  ];
  await page.goto("/workspace");
  const end = page.getByRole("slider", {
    name: "Изменить окончание: Private plan",
    exact: true,
  });
  await end.focus();
  for (let i = 0; i < 4; i++) await end.press("ArrowDown");
  await expect(end).toHaveAttribute("aria-valuetext", /GMT-5/);
  await end.press("Enter");
  await expect
    .poll(() => state.events[0].ends_at)
    .toBe("2026-11-01T06:45:37.000Z");
  expect(state.events[0].starts_at).toBe("2026-11-01T05:30:37Z");
  expect(state.writes[0].body).toEqual({
    expected_version: 1,
    ends_at: "2026-11-01T06:45:37.000Z",
  });
});

for (const width of [1440, 834, 390]) {
  test(`event detail exposes explicit notes, materials and related events at ${width}px`, async ({
    page,
  }, info) => {
    await page.setViewportSize({ width, height: 1000 });
    const state = await mockWorkspace(page);
    const secondId = "22222222-2222-4222-8222-222222222222";
    const pageId = "33333333-3333-4333-8333-333333333333";
    state.events = [
      calendarEvent(),
      calendarEvent({
        id: `personal:${secondId}`,
        source_event_id: secondId,
        title: "Next session",
        starts_at: "2026-10-13T10:00:00Z",
        ends_at: "2026-10-13T11:00:00Z",
      }),
    ];
    const note = {
      id: pageId,
      title: "Общий конспект",
      version: 1,
      parent_id: null,
      trashed_at: null,
      updated_at: "2026-10-16T10:00:00Z",
      document: {
        schema_version: 1,
        blocks: [
          {
            id: pageId,
            type: "text",
            text: "Связанный текст",
            text_format: "plain",
          },
        ],
      },
    };
    let linked = true;
    await page.route("**/api/v1/notes/pages**", (route) =>
      route.fulfill({
        json: new URL(route.request().url()).pathname.endsWith(pageId)
          ? note
          : { items: [note], limit: 200, offset: 0 },
      }),
    );
    await page.route("**/api/v1/materials?**", (route) =>
      route.fulfill({ json: { items: [], limit: 50, offset: 0 } }),
    );
    await page.route("**/api/v1/relations/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (route.request().method() === "DELETE") {
        linked = false;
        return route.fulfill({ status: 204 });
      }
      const items = path.endsWith("/calendar-events")
        ? state.events.map((event) => ({
            event: {
              source: event.source,
              event_id: event.source_event_id,
              title: event.title,
              starts_at: event.starts_at,
              source_status: "active",
            },
          }))
        : path.endsWith("/materials")
          ? [
              {
                id: "material-1",
                title: "Пособие",
                kind: "link",
                url: "https://example.com/material",
                status: "ready",
                trashed_at: null,
              },
            ]
          : linked
            ? [{ page: note }]
            : [];
      return route.fulfill({ json: { items, limit: 200, offset: 0 } });
    });
    await page.goto("/workspace");
    await page
      .locator(".event-card")
      .filter({ hasText: "Private plan" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Private plan", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "Название", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: /Связанные материалы/ }).click();
    await expect(page.getByText("Пособие", { exact: true })).toBeVisible();
    await page
      .getByRole("button", { name: /Связанные события этой заметки/ })
      .click();
    await expect(
      page.getByRole("button", { name: "Next session", exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(width);
    await page.screenshot({
      path: info.outputPath("event-detail.png"),
      fullPage: true,
      animations: "disabled",
    });
    const theme = page.getByRole("button", { name: /Тема:/ }).first();
    await theme.click();
    await theme.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.screenshot({
      path: info.outputPath("event-detail-dark.png"),
      fullPage: true,
      animations: "disabled",
    });
    await page
      .getByRole("button", { name: "Next session", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Next session", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Общий конспект", exact: true })
      .click();
    await expect(page.getByLabel("Текст блока 1")).toHaveValue(
      "Связанный текст",
    );
    expect(state.writes).toEqual([]);
    if (width === 1440) {
      await navigateSection(page, "Календарь");
      await page
        .locator(".event-card")
        .filter({ hasText: "Private plan" })
        .click();
      await page
        .getByRole("button", { name: /Связанные события этой заметки/ })
        .click();
      let release!: () => void;
      state.holdCalendar = new Promise<void>((resolve) => {
        release = resolve;
      });
      const delivered = page.waitForResponse((response) =>
        response.url().includes("date_to=2026-10-13"),
      );
      await page
        .getByRole("button", { name: "Next session", exact: true })
        .click();
      await expect(
        page.getByRole("button", { name: "Next session", exact: true }),
      ).toBeDisabled();
      await navigateSection(page, "Заметки");
      await page.getByLabel("Текст блока 1").fill("Черновик после перехода");
      release();
      await (await delivered).finished();
      await expect(page.getByLabel("Текст блока 1")).toHaveValue(
        "Черновик после перехода",
      );
      await expect(page.locator(".event-detail")).toHaveCount(0);
    }
  });
}
