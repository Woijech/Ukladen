import { expect, type Page } from "@playwright/test";

export const group = { id: 1, name: "353501", faculty_name: "Faculty", faculty_abbrev: "F", speciality_name: "Computing", course: 4 };
export const profile = { group, subgroup: 1 };
export const ready = { group_id: 1, group_number: "353501", status: "ready", last_attempt_at: "2026-10-16T08:00:00Z", last_success_at: "2026-10-16T08:00:01Z", error_code: null };
export function calendarEvent(overrides = {}) {
  return { id: "personal:11111111-1111-4111-8111-111111111111", source_event_id: "11111111-1111-4111-8111-111111111111", source: "personal", kind: "personal", title: "Private plan", description: "Private description", version: 1, starts_at: "2026-10-12T10:00:00Z", ends_at: "2026-10-12T11:00:00Z", location: "Home", blocks_time: true, hidden: false, skipped: false, has_override: false, lesson_type: null, subject: null, subject_full_name: null, rooms: [], teacher_names: [], ...overrides };
}

export async function mockWorkspace(page: Page) {
  const state = {
    authenticated: true, userId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", timezone: "UTC",
    profile: null as typeof profile | null, status: { ...ready },
    events: [] as ReturnType<typeof calendarEvent>[],
    holdCalendar: null as Promise<void> | null,
    calendarCode: 200, syncCode: 202,
    writes: [] as { method: string; path: string; body: Record<string, unknown> | null }[],
  };
  await page.clock.setFixedTime(new Date("2026-10-16T12:00:00Z"));
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method !== "GET") {
      expect(request.headers()["x-csrf-token"]).toBe("test-csrf");
      expect(request.headers().cookie).toContain("ukladen_csrf=test-csrf");
      expect(request.headers().origin).toBe("http://127.0.0.1:3001");
      state.writes.push({ method, path, body: request.postData() ? request.postDataJSON() : null });
    }
    if (path === "/api/v1/auth/csrf") return route.fulfill({ headers: { "Set-Cookie": "ukladen_csrf=test-csrf; Path=/; HttpOnly; SameSite=Lax" }, json: { csrf_token: "test-csrf" } });
    if (path === "/api/v1/auth/logout") { state.authenticated = false; return route.fulfill({ status: 204 }); }
    if (path === "/api/v1/auth/login" || path === "/api/v1/auth/register") { state.authenticated = true; return route.fulfill({ json: { user_id: state.userId } }); }
    if (!state.authenticated) return route.fulfill({ status: 401, json: { detail: "Invalid session." } });
    if (path === "/api/v1/users/me") return route.fulfill({ json: { id: state.userId, email: "test@example.com", status: "active", timezone: state.timezone, locale: "ru", display_name: null, email_verified_at: null, created_at: "2026-10-16T08:00:00Z", updated_at: "2026-10-16T08:00:00Z", avatar_url: null } });
    if (path === "/api/v1/academics/groups") return route.fulfill({ json: [group] });
    if (path === "/api/v1/academics/groups/1/context") return route.fulfill({ json: { group, schedule_available: true, subgroups: [1, 2], period: null } });
    if (path === "/api/v1/academics/me") {
      if (method === "PATCH") state.profile = { group, subgroup: request.postDataJSON().subgroup };
      return route.fulfill({ json: state.profile });
    }
    if (path === "/api/v1/schedule/me/sync-status") return route.fulfill({ json: state.status });
    if (path === "/api/v1/schedule/me/sync") return route.fulfill({ status: state.syncCode, json: { group_id: 1, status: "accepted" } });
    if (path === "/api/v1/calendar/events") {
      await state.holdCalendar;
      return route.fulfill({ status: state.calendarCode, json: { events: state.events, timezone: state.timezone, source: state.profile ? state.status : null, warnings: [] } });
    }
    if (path.startsWith("/api/v1/calendar/personal-events")) {
      if (method === "DELETE") { state.events = []; return route.fulfill({ status: 204 }); }
      const event = calendarEvent({ ...request.postDataJSON(), version: method === "PATCH" ? 2 : 1 });
      state.events = [event];
      return route.fulfill({ status: method === "POST" ? 201 : 200, json: { ...event, id: event.source_event_id } });
    }
    throw new Error(`Unexpected workspace request: ${method} ${path}`);
  });
  return state;
}

export async function login(page: Page) {
  await page.getByLabel("Электронная почта").fill("test@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("a-test-password-123");
  await page.getByRole("button", { name: "Войти", exact: true }).click();
}
