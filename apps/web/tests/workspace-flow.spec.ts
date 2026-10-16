import { test, expect } from "@playwright/test";
import { calendarEvent, login, mockWorkspace, profile } from "./workspace-fixtures";

test.use({ timezoneId: "UTC" });

test("registration, group import, personal CRUD and returning-user login work together", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.authenticated = false;
  state.status = { ...state.status, status: "not_synced", last_attempt_at: null, last_success_at: null };
  state.onSync = () => {
    state.status = { ...state.status, status: "ready", last_attempt_at: "2026-10-16T12:00:00Z", last_success_at: "2026-10-16T12:00:01Z" };
    state.events = [calendarEvent({ id: "official:22222222-2222-4222-8222-222222222222", source_event_id: "22222222-2222-4222-8222-222222222222", source: "official", kind: "lesson", title: "IIS lesson", subject_full_name: "Algorithms", version: 0, rooms: ["101-1"], teacher_names: ["Instructor"] })];
  };
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Создать аккаунт", exact: true }).click();
  await page.getByLabel("Электронная почта").fill("test@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("a-test-password-123");
  await page.getByRole("button", { name: "Зарегистрироваться", exact: true }).click();
  await expect(page).toHaveURL("/auth/complete-registration");
  await expect(page.getByRole("status")).toContainText("Подтвердите почту");
  await expect(page.locator(".workspace-shell")).toHaveCount(0);
  state.registrationComplete = true;
  await page.getByRole("button", { name: "Я подтвердил почту — проверить" }).click();
  await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Настроить учебную группу" }).click();
  await expect(page.getByRole("heading", { name: "Добавь расписание учёбы" })).toBeVisible();
  await page.getByRole("option", { name: /353501/ }).click();
  await page.getByLabel("Подгруппа", { exact: true }).selectOption("2");
  await page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await expect(page.locator(".schedule-sync-notice")).toHaveClass(/is-success/);
  await expect(page.locator(".event-card")).toContainText("IIS lesson");
  expect(state.writes.find(write => write.path === "/api/v1/academics/me")?.body).toEqual({ group_id: 1, subgroup: 2 });
  await page.locator(".event-card").click();
  await expect(page.locator(".event-readonly")).toContainText("Algorithms");
  await expect(page.locator(".event-readonly")).toContainText("101-1");
  await expect(page.locator(".event-readonly").getByRole("button", { name: "Сохранить", exact: true })).toHaveCount(0);
  await page.locator(".event-readonly .primary-button").click();

  await page.getByRole("button", { name: "Новое событие", exact: true }).click();
  await page.getByLabel("Название", { exact: true }).fill("Study plan");
  await page.getByLabel("Описание", { exact: false }).fill("Prepare exercises");
  await page.locator(".event-modal").getByRole("button", { name: "Добавить событие" }).click();
  await expect(page.locator(".event-card")).toHaveCount(2);
  await page.locator(".event-card").filter({ hasText: "Study plan" }).click();
  await page.getByLabel("Название", { exact: true }).fill("Updated plan");
  await page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(page.locator(".event-card").filter({ hasText: "Updated plan" })).toHaveCount(1);
  expect(state.writes.find(write => write.path.includes("/personal-events/") && write.method === "PATCH")?.body).toMatchObject({ expected_version: 1, title: "Updated plan", description: "Prepare exercises" });
  await page.locator(".event-card").filter({ hasText: "Updated plan" }).click();
  await page.getByRole("button", { name: "Удалить", exact: true }).click();
  await expect(page.locator(".event-card")).toHaveCount(1);
  await expect(page.locator(".event-card")).toContainText("IIS lesson");

  await page.locator(".account-button").click();
  await page.getByRole("button", { name: "Выйти из аккаунта" }).click();
  await login(page);
  await expect(page.getByRole("heading", { name: "Календарь", exact: true })).toBeVisible();
  await expect(page.locator(".group-page")).toHaveCount(0);
  await expect(page.locator(".event-card")).toContainText("IIS lesson");
});

test("invalid credentials keep the user signed out and allow another login attempt", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.authenticated = false;
  state.authCode = 401;
  await page.goto("/workspace");
  await login(page);
  await expect(page.locator(".auth-card").getByRole("alert")).toContainText("Неверная почта или пароль");
  await expect(page.locator(".workspace-shell")).toHaveCount(0);
  state.authCode = 200;
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.locator(".group-page")).toBeVisible();
});

test("a failed calendar read offers a working retry", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.calendarCode = 503;
  await page.goto("/workspace");
  await expect(page.locator(".inline-error")).toContainText("временно недоступен");
  state.calendarCode = 200;
  state.events = [calendarEvent()];
  await page.locator(".inline-error").getByRole("button", { name: "Повторить", exact: true }).click();
  await expect(page.locator(".event-card")).toContainText("Private plan");
  await expect(page.locator(".inline-error")).toHaveCount(0);
});

test("temporary status-read failures keep polling until the new import completes", async ({ page }) => {
  const state = await mockWorkspace(page);
  state.profile = profile;
  state.status.status = "error";
  state.onSync = () => { state.syncStatusCode = 503; };
  await page.goto("/workspace");
  await page.getByRole("button", { name: "Повторить синхронизацию" }).click();
  await expect(page.locator(".schedule-sync-notice")).toContainText("Не удалось проверить статус");
  state.syncStatusCode = 200;
  state.status = { ...state.status, status: "ready", last_attempt_at: "2026-10-16T12:00:00Z", last_success_at: "2026-10-16T12:00:01Z" };
  await page.clock.fastForward(3100);
  await expect(page.locator(".schedule-sync-notice")).toHaveClass(/is-success/);
});
