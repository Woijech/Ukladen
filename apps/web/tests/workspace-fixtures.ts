import { expect, type Page } from "@playwright/test";

export const group = { id: 1, name: "353501", faculty_name: "Faculty", faculty_abbrev: "F", speciality_name: "Computing", course: 4 };
export const profile = { group, subgroup: 1 };
export const ready = { group_id: 1, group_number: "353501", status: "ready", last_attempt_at: "2026-10-16T08:00:00Z" as string | null, last_success_at: "2026-10-16T08:00:01Z" as string | null, error_code: null as string | null };
export function calendarEvent(overrides = {}) {
  return { id: "personal:11111111-1111-4111-8111-111111111111", source_event_id: "11111111-1111-4111-8111-111111111111", source: "personal", kind: "personal", title: "Private plan", description: "Private description", version: 1, starts_at: "2026-10-12T10:00:00Z", ends_at: "2026-10-12T11:00:00Z", location: "Home", blocks_time: true, hidden: false, skipped: false, has_override: false, lesson_type: null, subject: null, subject_full_name: null, rooms: [], teacher_names: [], ...overrides };
}

export function task(overrides: Record<string, unknown> = {}) {
  return { id: "11111111-1111-4111-8111-111111111111", parent_id: null as string | null, title: "Prepare report", description: null as string | null, status: "todo", priority: "normal", deadline_at: null as string | null, estimated_minutes: null as number | null, version: 1, created_at: "2026-10-16T12:00:00Z", updated_at: "2026-10-16T12:00:00Z", trashed_at: null as string | null, trash_batch_id: null as string | null, is_overdue: false, ...overrides };
}

export async function mockWorkspace(page: Page) {
  const csrf = "c".repeat(43);
  const state = {
    authenticated: true, userId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", timezone: "UTC",
    registrationComplete: true,
    profile: null as typeof profile | null, status: { ...ready },
    events: [] as ReturnType<typeof calendarEvent>[],
    eventCode: 200,
    tasks: [] as ReturnType<typeof task>[], taskConflictOnce: false, taskHierarchyConflictOnce: false,
    holdCalendar: null as Promise<void> | null,
    calendarCode: 200, groupSourceCode: 200, syncStatusCode: 200, authCode: 200, syncCode: 202, onSync: null as (() => void) | null,
    writes: [] as { method: string; path: string; body: Record<string, unknown> | null }[],
  };
  await page.clock.install({ time: new Date("2026-10-16T12:00:00Z") });
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const method = request.method();
    if (method !== "GET") {
      expect(request.headers()["x-csrf-token"]).toBe(csrf);
      expect(request.headers().cookie).toContain(`ukladen_csrf=${csrf}`);
      expect(request.headers().origin).toBe("http://127.0.0.1:3001");
      state.writes.push({ method, path, body: request.postData() ? request.postDataJSON() : null });
    }
    if (path === "/api/v1/auth/csrf") return route.fulfill({ headers: { "Set-Cookie": `ukladen_csrf=${csrf}; Path=/; HttpOnly; SameSite=Lax` }, json: { csrf_token: csrf } });
    if (path === "/api/v1/auth/logout") { state.authenticated = false; return route.fulfill({ status: 204 }); }
    if (path === "/api/v1/auth/login" || path === "/api/v1/auth/register") {
      if (state.authCode !== 200) return route.fulfill({ status: state.authCode, json: { detail: "Invalid credentials." } });
      state.authenticated = true;
      if (path.endsWith("register")) state.registrationComplete = false;
      return route.fulfill({ status: path.endsWith("register") ? 201 : 200, json: { user_id: state.userId, expires_at: "2026-11-16T12:00:00Z" } });
    }
    if (!state.authenticated) return route.fulfill({ status: 401, json: { detail: "Invalid session." } });
    if (path === "/api/v1/auth/registration") return route.fulfill({ json: { email: "test@example.com", email_verified: state.registrationComplete, password_required: false, complete: state.registrationComplete, password_min_length: 12 } });
    if (path === "/api/v1/auth/email-verification/request") return route.fulfill({ status: 202, json: {} });
    if (!state.registrationComplete) return route.fulfill({ status: 403, json: { code: "registration_incomplete", detail: "Registration is incomplete." } });
    if (path === "/api/v1/users/me") return route.fulfill({ json: { id: state.userId, email: "test@example.com", status: "active", timezone: state.timezone, locale: "ru", display_name: null, email_verified_at: "2026-10-16T08:00:00Z", created_at: "2026-10-16T08:00:00Z", updated_at: "2026-10-16T08:00:00Z", avatar_url: null } });
    if (path === "/api/v1/academics/groups") return route.fulfill({ json: [group] });
    if (path === "/api/v1/academics/groups/1/context") return route.fulfill({ json: { group, schedule_available: true, subgroups: [1, 2], period: null } });
    if (path === "/api/v1/academics/me") {
      if (method === "PATCH") state.profile = { group, subgroup: request.postDataJSON().subgroup };
      return route.fulfill({ json: state.profile });
    }
    if (path === "/api/v1/schedule/me/sync-status") return route.fulfill({ status: state.syncStatusCode, json: { ...state.status } });
    if (path === "/api/v1/schedule/groups/353501/events") return route.fulfill({ status: state.groupSourceCode, json: state.groupSourceCode === 200 ? { events: [], source: { ...state.status } } : { detail: "Schedule event not found." } });
    if (path === "/api/v1/schedule/me/sync") { state.onSync?.(); return route.fulfill({ status: state.syncCode, json: { group_id: 1, status: "accepted" } }); }
    if (path === "/api/v1/calendar/events") {
      await state.holdCalendar;
      return route.fulfill({ status: state.calendarCode, json: { events: state.events, timezone: state.timezone, source: state.profile ? state.status : null, warnings: [] } });
    }
    if (path.startsWith("/api/v1/calendar/personal-events")) {
      if (state.eventCode !== 200) return route.fulfill({ status: state.eventCode, json: {} });
      if (method === "DELETE") { state.events = state.events.filter(event => event.source_event_id !== path.split("/").at(-1)); return route.fulfill({ status: 204 }); }
      if (method === "PATCH") {
        const current = state.events.find(event => event.source_event_id === path.split("/").at(-1));
        if (!current) return route.fulfill({ status: 404, json: {} });
        const { expected_version, ...changes } = request.postDataJSON();
        if (expected_version !== current.version) return route.fulfill({ status: 409, json: {} });
        Object.assign(current, changes, { version: current.version + 1 });
        return route.fulfill({ json: { ...current, id: current.source_event_id } });
      }
      const event = calendarEvent({ ...request.postDataJSON(), version: 1 });
      state.events = [...state.events.filter(item => item.id !== event.id), event];
      return route.fulfill({ status: 201, json: { ...event, id: event.source_event_id } });
    }
    if (method === "GET" && (path === "/api/v1/notes/pages" || path.startsWith("/api/v1/relations/")))
      return route.fulfill({ json: { items: [], limit: 200, offset: 0 } });
    if (path === "/api/v1/tasks" && method === "GET") {
      const params = new URL(request.url()).searchParams;
      const offset = Number(params.get("offset") ?? 0);
      const limit = Number(params.get("limit") ?? 100);
      const filtered = state.tasks.filter(item => Boolean(item.trashed_at) === (params.get("trashed") === "true") && (!params.get("status") || item.status === params.get("status")) && (!params.get("priority") || item.priority === params.get("priority")) && (!params.get("parent_id") || item.parent_id === params.get("parent_id")));
      return route.fulfill({ json: { items: filtered.slice(offset, offset + limit).map(item => Object.fromEntries(Object.entries(item).filter(([key]) => key !== "description"))), limit, offset } });
    }
    if (path === "/api/v1/tasks" && method === "POST") {
      const body = request.postDataJSON();
      const created = task({ ...body, id: `00000000-0000-4000-8000-${String(state.tasks.length + 1).padStart(12, "0")}`, parent_id: body.parent_id ?? null });
      state.tasks.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    if (path.startsWith("/api/v1/tasks/")) {
      const parts = path.split("/");
      const operation = parts.at(-1);
      const current = state.tasks.find(item => item.id === (operation === "trash" || operation === "restore" ? parts.at(-2) : operation));
      if (!current) return route.fulfill({ status: 404, json: { code: "task_not_found" } });
      if (method === "GET") return route.fulfill({ json: current });
      if (state.taskConflictOnce || request.postDataJSON().expected_version !== current.version) {
        state.taskConflictOnce = false;
        return route.fulfill({ status: 409, json: { code: "task_version_conflict" } });
      }
      if (state.taskHierarchyConflictOnce) {
        state.taskHierarchyConflictOnce = false;
        return route.fulfill({ status: 409, json: { code: "task_hierarchy_conflict" } });
      }
      if (operation === "trash" || operation === "restore") {
        if (operation === "trash" && current.trashed_at || operation === "restore" && (!current.trashed_at || current.trash_batch_id !== current.id)) return route.fulfill({ status: 409, json: { code: "task_trash_conflict" } });
        if (operation === "trash") {
          const visit = (id: string) => {
            const item = state.tasks.find(candidate => candidate.id === id);
            if (!item) return;
            if (!item.trashed_at) Object.assign(item, { trashed_at: "2026-10-16T12:00:00Z", trash_batch_id: current.id, version: item.version + 1 });
            state.tasks.filter(candidate => candidate.parent_id === id).forEach(child => visit(child.id));
          };
          visit(current.id);
        } else {
          state.tasks.filter(item => item.trash_batch_id === current.id).forEach(item => Object.assign(item, { trashed_at: null, trash_batch_id: null, version: item.version + 1 }));
        }
        return route.fulfill({ json: current });
      }
      const changes = request.postDataJSON();
      delete changes.expected_version;
      Object.assign(current, changes, { version: current.version + 1 });
      return route.fulfill({ json: current });
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


export async function navigateSection(page: Page, name: string) {
  const mobile = page.getByRole("button", { name: "Открыть навигацию", exact: true });
  const isMobile = await mobile.isVisible();
  if (isMobile) await mobile.click();
  const scope = isMobile ? page.getByRole("dialog", { name: "Навигация", exact: true }) : page.locator(".sidebar");
  const target = scope.getByRole("button", { name, exact: true });
  if (!await target.isVisible()) await scope.getByRole("button", { name: "Ещё", exact: true }).click();
  await target.click();
}
