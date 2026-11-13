import { sections, type SectionKey } from "./navigation";

export type WorkspaceLocation = {
  section: SectionKey;
  taskId?: string;
  pageId?: string;
  databaseId?: string;
  viewId?: string;
  date?: string;
  calendarView?: "day" | "week";
  query?: string;
};

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isWorkspaceDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function readWorkspaceLocation(pathname: string, search: string, fallback: SectionKey) {
  const params = new URLSearchParams(search);
  let invalid = false;
  function single(key: string) {
    const values = params.getAll(key);
    if (values.length > 1) { invalid = true; return undefined; }
    return values[0];
  }
  function identifier(key: string) {
    const value = single(key);
    if (value === undefined) return undefined;
    if (!uuid.test(value)) { invalid = true; return undefined; }
    return value.toLowerCase();
  }
  function date() {
    const value = single("date");
    if (value === undefined) return undefined;
    if (!isWorkspaceDate(value)) { invalid = true; return undefined; }
    return value;
  }
  // AI owns its existing path/chat parameters; do not canonicalize them here.
  if (pathname === "/workspace/ai" || pathname.startsWith("/workspace/ai/")) {
    return { location: { section: "ai" } as WorkspaceLocation, invalid: false };
  }
  const requested = single("section");
  let section = sections.find(item => item.id === requested)?.id;
  if (requested !== undefined && !section) invalid = true;
  // Preserve previously copied /workspace?page=UUID links.
  if (requested === undefined && params.has("page")) section = "notes";
  const location: WorkspaceLocation = { section: section ?? fallback };
  switch (location.section) {
    case "tasks": location.taskId = identifier("task"); break;
    case "notes": location.pageId = identifier("page"); break;
    case "calendar": {
      location.date = date();
      const view = single("view");
      if (view === "day" || view === "week") location.calendarView = view;
      else if (view !== undefined) invalid = true;
      break;
    }
    case "databases":
      location.databaseId = identifier("database");
      location.viewId = identifier("view");
      location.date = date();
      if (!location.databaseId && (location.viewId || location.date)) {
        invalid = true;
        delete location.viewId;
        delete location.date;
      }
      break;
    case "search": location.query = single("q"); break;
  }
  return { location, invalid };
}

export function workspaceHref(location: WorkspaceLocation): string {
  const params = new URLSearchParams({ section: location.section });
  switch (location.section) {
    case "tasks": if (location.taskId) params.set("task", location.taskId); break;
    case "notes": if (location.pageId) params.set("page", location.pageId); break;
    case "calendar":
      if (location.date) params.set("date", location.date);
      if (location.calendarView) params.set("view", location.calendarView);
      break;
    case "databases":
      if (location.databaseId) {
        params.set("database", location.databaseId);
        if (location.viewId) params.set("view", location.viewId);
        if (location.date) params.set("date", location.date);
      }
      break;
    case "search": if (location.query) params.set("q", location.query); break;
  }
  return `/workspace?${params.toString()}`;
}
