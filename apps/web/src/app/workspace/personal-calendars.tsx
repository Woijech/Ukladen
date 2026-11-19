"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, QueryState, useAction } from "@/shared/ui";
import { positionNoteMenu } from "./panels/note-menu";
import type { CalendarEvent } from "./workspace";

export type PersonalCalendar = { id: string; name: string; color: string; version: number };
type Visibility = { version: number; default_visible: boolean; hidden_calendar_ids: string[]; hidden_lesson_types: string[] };
const defaults: Visibility = { version: 0, default_visible: true, hidden_calendar_ids: [], hidden_lesson_types: [] };
const lessonTypes = { ЛК: "Лекции", ЛР: "Лабораторные", ПЗ: "Практические", other: "Другие занятия" };
export function lessonCategory(type: string | null) { return type && Object.hasOwn(lessonTypes, type) ? type : "other"; }

export function usePersonalCalendars() {
  const client = useQueryClient();
  const action = useAction();
  const list = useQuery({ queryKey: ["personal-calendars"], queryFn: ({ signal }) => requestJson<{ items: PersonalCalendar[] }>("/api/v1/calendar/calendars", { signal }) });
  const visibility = useQuery({ queryKey: ["calendar-visibility"], queryFn: ({ signal }) => requestJson<Visibility>("/api/v1/calendar/visibility", { signal }) });
  const settings = visibility.data ?? defaults;
  const calendars = list.data?.items ?? [];
  async function refresh() {
    await Promise.all([client.invalidateQueries({ queryKey: ["personal-calendars"] }), client.invalidateQueries({ queryKey: ["workspace-calendar"] }), client.invalidateQueries({ queryKey: ["calendar-visibility"] })]);
  }
  function setVisibility(value: Visibility) {
    void action.run(async () => {
      const previous = client.getQueryData<Visibility>(["calendar-visibility"]);
      client.setQueryData(["calendar-visibility"], value);
      try {
        const result = await writeJson<Visibility>("/api/v1/calendar/visibility", "PUT", value);
        client.setQueryData(["calendar-visibility"], result);
      } catch (error) {
        client.setQueryData(["calendar-visibility"], previous);
        throw error;
      }
    }, "Видимость сохранена");
  }
  function visible(event: CalendarEvent) {
    return event.source === "personal" ? event.calendar_id ? !settings.hidden_calendar_ids.includes(event.calendar_id) : settings.default_visible : !settings.hidden_lesson_types.includes(lessonCategory(event.lesson_type));
  }
  return { calendars, settings, list, visibility, action, setVisibility, visible, refresh };
}

export function PersonalCalendarSources({ state }: { state: ReturnType<typeof usePersonalCalendars> }) {
  const { calendars, settings, setVisibility, action } = state;
  const [editing, setEditing] = useState<PersonalCalendar | "new" | null>(null);
  const [deleting, setDeleting] = useState<PersonalCalendar | null>(null);
  const allPersonal = settings.default_visible && !settings.hidden_calendar_ids.length;
  const allOfficial = !settings.hidden_lesson_types.length;
  const disabled = action.busy || state.visibility.isPending || !!state.visibility.error;
  const toggle = (values: string[], key: string) => values.includes(key) ? values.filter(i => i !== key) : [...values, key];
  return <div className="personal-calendar-sources">
    <div className="calendar-source-heading"><strong>Мои календари</strong><button type="button" className="text-action" aria-label="Добавить календарь" onClick={() => setEditing("new")}>+</button></div>
    <QueryState pending={state.list.isPending || state.visibility.isPending} error={state.list.error || state.visibility.error} retry={() => { void state.list.refetch(); void state.visibility.refetch(); }} />
    <details className="calendar-source-disclosure" open><summary>Личные календари</summary>
      <label className="calendar-source-row"><input type="checkbox" aria-label="Все личные календари" checked={allPersonal} disabled={disabled} onChange={event => setVisibility({ ...settings, default_visible: event.target.checked, hidden_calendar_ids: event.target.checked ? [] : calendars.map(c => c.id) })} />Все личные</label>
      <label className="calendar-source-row"><input type="checkbox" checked={settings.default_visible} disabled={disabled} onChange={event => setVisibility({ ...settings, default_visible: event.target.checked })} /><span className="legend-dot personal-dot" />Личные события</label>
      {calendars.map(calendar => <div className="calendar-source-row" key={calendar.id}>
        <label><input type="checkbox" checked={!settings.hidden_calendar_ids.includes(calendar.id)} disabled={disabled} onChange={() => setVisibility({ ...settings, hidden_calendar_ids: toggle(settings.hidden_calendar_ids, calendar.id) })} /><span className="legend-dot" style={{ background: calendar.color }} /><span>{calendar.name}</span></label>
        <details className="note-menu calendar-source-menu" onToggle={event => positionNoteMenu(event.currentTarget)}><summary aria-label={`Действия календаря ${calendar.name}`}>···</summary><div className="note-menu-items"><button type="button" onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); setEditing(calendar); }}>Название и цвет</button><button type="button" onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); setDeleting(calendar); }}>Удалить календарь</button></div></details>
      </div>)}
    </details>
    <details className="calendar-source-disclosure" open><summary>Расписание IIS</summary>
      <label className="calendar-source-row"><input type="checkbox" aria-label="Расписание IIS" checked={allOfficial} disabled={disabled} onChange={event => setVisibility({ ...settings, hidden_lesson_types: event.target.checked ? [] : Object.keys(lessonTypes) })} /><span className="legend-dot official-dot" />Все занятия</label>
      {Object.entries(lessonTypes).map(([key, label]) => <label className="calendar-source-row" key={key}><input type="checkbox" checked={!settings.hidden_lesson_types.includes(key)} disabled={disabled} onChange={() => setVisibility({ ...settings, hidden_lesson_types: toggle(settings.hidden_lesson_types, key) })} />{label}</label>)}
    </details>
    <ActionFeedback error={action.error} notice="" />
    {editing && <CalendarEditor calendar={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={state.refresh} />}
    {deleting && <Modal title="Удалить календарь" onClose={() => { if (!action.busy) setDeleting(null); }}>
      <h2>Удалить «{deleting.name}»?</h2><p>События сохранятся в календаре «Личные события».</p>
      <button type="button" className="danger-button" disabled={action.busy} onClick={() => void action.run(async () => { await writeJson(`/api/v1/calendar/calendars/${deleting.id}`, "DELETE", { expected_version: deleting.version }); setDeleting(null); await state.refresh(); }, "Календарь удалён. События сохранены.")}>Удалить календарь</button><ActionFeedback error={action.error} notice="" />
    </Modal>}
  </div>;
}

function CalendarEditor({ calendar, onClose, onSaved }: { calendar: PersonalCalendar | null; onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(calendar?.name ?? "");
  const [color, setColor] = useState(calendar?.color ?? "#70558e");
  const action = useAction();
  const dirty = name !== (calendar?.name ?? "") || color !== (calendar?.color ?? "#70558e");
  return <Modal title={calendar ? "Настройки календаря" : "Новый календарь"} onClose={() => { if (!action.busy && (!dirty || window.confirm("Закрыть календарь без сохранения?"))) onClose(); }}>
    <h2>{calendar ? "Настройки календаря" : "Новый календарь"}</h2>
    <form onSubmit={event => { event.preventDefault(); void action.run(async () => { await writeJson(calendar ? `/api/v1/calendar/calendars/${calendar.id}` : "/api/v1/calendar/calendars", calendar ? "PATCH" : "POST", { name, color, ...(calendar ? { expected_version: calendar.version } : {}) }); await onSaved(); onClose(); }); }}>
      <label>Название<input required maxLength={100} value={name} onChange={event => setName(event.target.value)} /></label>
      <label>Цвет<input type="color" value={color} onChange={event => setColor(event.target.value)} /></label>
      <button className="primary-button" disabled={action.busy || !name.trim()}>Сохранить календарь</button><ActionFeedback {...action} />
    </form>
  </Modal>;
}
