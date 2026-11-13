import { expect, test } from "@playwright/test";
import { isWorkspaceDate, readWorkspaceLocation, workspaceHref, type WorkspaceLocation } from "../src/app/workspace/workspace-location";

const id = "11111111-1111-4111-8111-111111111111";
const other = "22222222-2222-4222-8222-222222222222";

test("workspace locations round-trip typed object selections and civil dates", () => {
  const locations: WorkspaceLocation[] = [
    { section: "tasks", taskId: id },
    { section: "notes", pageId: id },
    { section: "databases", databaseId: id, viewId: other, date: "2026-11-13" },
    { section: "calendar", date: "2026-11-13", calendarView: "week" },
    { section: "search", query: "Отчёт & лекция?" },
    { section: "settings" },
  ];
  for (const location of locations) {
    const url = new URL(workspaceHref(location), "https://example.test");
    const result = readWorkspaceLocation(url.pathname, url.search, "calendar");
    expect(result.invalid).toBe(false);
    expect(result.location).toEqual(location);
  }
});

test("legacy page links and existing AI paths retain their destinations", () => {
  expect(readWorkspaceLocation("/workspace", `?page=${id}`, "calendar").location).toEqual({ section: "notes", pageId: id });
  expect(readWorkspaceLocation("/workspace/ai/usage", "?chat=existing", "calendar")).toEqual({ location: { section: "ai" }, invalid: false });
});

test("invalid and duplicate route values cannot become API object identifiers", () => {
  for (const query of ["task=invalid", `task=${id}&task=${other}`, "task=", "task=%2F..%2Fprivate"]) {
    const result = readWorkspaceLocation("/workspace", `?section=tasks&${query}`, "calendar");
    expect(result.invalid).toBe(true);
    expect(result.location.taskId).toBeUndefined();
  }
  expect(readWorkspaceLocation("/workspace", `?section=databases&view=${id}`, "calendar")).toMatchObject({ invalid: true, location: { section: "databases" } });
  expect(readWorkspaceLocation("/workspace", "?section=calendar&date=2026-02-30&view=month", "calendar").invalid).toBe(true);
  expect(readWorkspaceLocation("/workspace", "?section=unknown", "calendar")).toEqual({ location: { section: "calendar" }, invalid: true });
});

test("calendar dates validate real leap days without device timezone conversion", () => {
  for (const value of ["2024-02-29", "2026-11-13", "0099-01-01"]) expect(isWorkspaceDate(value)).toBe(true);
  for (const value of ["2026-02-29", "2026-13-01", "2026-04-31", "0000-01-01", "2026-1-01", "2026-01-01T00:00:00Z"]) expect(isWorkspaceDate(value)).toBe(false);
});

test("serialization drops unrelated selections rather than leaking previous object context", () => {
  expect(workspaceHref({ section: "tasks", taskId: id, pageId: other, date: "2026-11-13", query: "private draft" })).toBe(`/workspace?section=tasks&task=${id}`);
  expect(workspaceHref({ section: "databases", viewId: id })).toBe("/workspace?section=databases");
});
