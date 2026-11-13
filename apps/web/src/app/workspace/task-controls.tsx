"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Modal } from "@/shared/ui";
import { CalendarMonth } from "./calendar-month";
import { dateKey, dateTimeLocal, localInstants, prettyDate, resolveLocalTime } from "./calendar-time";

export type Status = "todo" | "in_progress" | "done" | "cancelled";
export type Priority = "low" | "normal" | "high" | "urgent";
export type TaskSummary = {
  id: string; parent_id: string | null; title: string; status: Status; priority: Priority;
  deadline_at: string | null; estimated_minutes: number | null; remaining_minutes: number | null;
  version: number; created_at: string; updated_at: string; trashed_at: string | null;
  trash_batch_id: string | null; is_overdue: boolean;
};
export type Task = TaskSummary & { description: string | null };
export type TaskPatch = Partial<Pick<Task, "title" | "description" | "status" | "priority" | "deadline_at">>;
export type TaskField = "status" | "priority" | "deadline_at";
export const statusLabels: Record<Status, string> = { todo: "К выполнению", in_progress: "В работе", done: "Готово", cancelled: "Отменена" };
export const priorityLabels: Record<Priority, string> = { low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" };
const statusIcons: Record<Status, string> = { todo: "○", in_progress: "◐", done: "✓", cancelled: "⊘" };
const priorityIcons: Record<Priority, string> = { low: "↓", normal: "−", high: "↑", urgent: "!" };
export type PatchTask = (task: TaskSummary, changes: TaskPatch) => Promise<boolean>;

export function TaskPropertyEditor({ task, field, position, timeZone, busy, error, onSave, onReload, onClose }: {
  task: TaskSummary; field: TaskField; position: CSSProperties; timeZone: string; busy: boolean; error: string;
  onSave: PatchTask; onReload: () => void; onClose: () => void;
}) {
  const [day, setDay] = useState(task.deadline_at ? dateKey(new Date(task.deadline_at), timeZone) : dateKey(new Date(), timeZone));
  const [clock, setClock] = useState(task.deadline_at ? dateTimeLocal(new Date(task.deadline_at), timeZone).slice(11) : "18:00");
  const [choice, setChoice] = useState(task.deadline_at ?? "");
  const [validation, setValidation] = useState("");
  const match = /^(\d{1,2}):?(\d{2})$/.exec(clock);
  const normalized = match && +match[1] < 24 && +match[2] < 60 ? `${match[1].padStart(2, "0")}:${match[2]}` : null;
  const wall = `${day}T${normalized ?? clock}`;
  const options = localInstants(wall, timeZone, task.deadline_at ?? undefined);
  const title = field === "status" ? "Статус задачи" : field === "priority" ? "Приоритет задачи" : "Срок задачи";
  async function save(changes: TaskPatch) { if (await onSave(task, changes)) onClose(); }
  return <Modal title={title} className="task-property-dialog" style={position} initialFocus={field === "deadline_at" ? "#task-clock" : '[aria-pressed="true"]'} onClose={() => { if (!busy) onClose(); }}>
    <h2>{title}</h2>
    {field === "status" || field === "priority" ? <div className="task-property-choices" role="group" aria-label={title}>
      {Object.entries(field === "status" ? statusLabels : priorityLabels).map(([value, label]) => <button type="button" key={value} aria-pressed={task[field] === value} disabled={busy} onClick={() => void save({ [field]: value })}><span aria-hidden="true">{field === "status" ? statusIcons[value as Status] : priorityIcons[value as Priority]}</span>{label}{task[field] === value && <span aria-hidden="true">✓</span>}</button>)}
    </div> : <form onSubmit={event => {
      event.preventDefault();
      try { if (!normalized) throw new Error("Введи время в формате 09:37 или 0937."); setValidation(""); void save({ deadline_at: resolveLocalTime(wall, timeZone, choice, task.deadline_at ?? undefined) }); }
      catch (cause) { setValidation((cause as Error).message); }
    }}>
      <CalendarMonth selected={day} timeZone={timeZone} onSelect={value => { setDay(value); setChoice(""); }} />
      <label className="task-clock-label" htmlFor="task-clock">Точное время<input id="task-clock" name="deadline-time" autoComplete="off" inputMode="numeric" maxLength={5} placeholder="09:37" required value={clock} onChange={event => { setClock(event.target.value); setChoice(""); }} /></label>
      {options.length > 1 && <label>Смещение срока<select aria-label="Смещение срока" required value={choice} onChange={event => setChoice(event.target.value)}><option value="">Выбери смещение</option>{options.map(value => <option key={value} value={value}>{prettyDate(new Date(value), timeZone, { hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })}</option>)}</select></label>}
      {options.length > 1 && !choice && <p role="alert" className="task-field-error">Это время повторяется. Выбери нужное смещение.</p>}
      <p className="task-hint">{timeZone}. Срок не занимает время в календаре.</p>
      <div className="task-dialog-actions"><button type="button" className="task-secondary" disabled={busy} onClick={() => void save({ deadline_at: null })}>Убрать срок</button><button className="primary-button" disabled={busy}>{busy ? "Сохраняем…" : "Применить"}</button></div>
    </form>}
    {busy && <p role="status" className="task-hint">Сохраняем изменение…</p>}
    {(validation || error) && <div role="alert" className="task-error">{validation || error}{error && <button type="button" disabled={busy} onClick={onReload}>Загрузить актуальную версию</button>}</div>}
  </Modal>;
}

export function TaskRow({ task, selected, timeZone, busy, onSelect, onPatch, onProperty, onEdit, onChild, onDirtyChange }: {
  onDirtyChange: (id: string, dirty: boolean) => void;
  task: TaskSummary; selected: boolean; timeZone: string; busy: boolean; onSelect: () => void;
  onPatch: PatchTask; onProperty: (field: TaskField, trigger: HTMLElement) => void; onEdit: () => void; onChild: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [titleSnapshot, setTitleSnapshot] = useState(task);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<CSSProperties>({});
  const titleButton = useRef<HTMLButtonElement>(null);
  const titleInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if (editing) requestAnimationFrame(() => titleInput.current?.focus()); }, [editing]);
  function rename() { setTitleSnapshot(task); setTitle(task.title); setEditing(true); setMenuOpen(false); }
  function closeRename() { setEditing(false); requestAnimationFrame(() => titleButton.current?.focus({ preventScroll: true })); }
  useEffect(() => { onDirtyChange(task.id, editing && title !== task.title); return () => onDirtyChange(task.id, false); }, [task.id, task.title, editing, title, onDirtyChange]);
  const trashed = Boolean(task.trashed_at);
  return <li className={`task-line ${selected ? "is-selected" : ""}`} data-task-id={task.id}>
    {!trashed ? <label className="task-complete-target"><input className="task-complete" type="checkbox" checked={task.status === "done"} disabled={busy || task.status === "cancelled"} aria-label={`${task.status === "done" ? "Вернуть к выполнению" : "Завершить"}: ${task.title}`} onChange={() => void onPatch(task, { status: task.status === "done" ? "todo" : "done" })} /></label> : <span className="task-trash-marker" aria-hidden="true">↩</span>}
    {editing ? <form className="task-inline-title" onSubmit={event => { event.preventDefault(); void onPatch(titleSnapshot, { title: title.trim() }).then(saved => { if (saved) closeRename(); }); }}>
      <input name="task-title" autoComplete="off" ref={titleInput} aria-label="Название задачи в строке" required maxLength={200} pattern={".*\\S.*"} value={title} disabled={busy} onChange={event => setTitle(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); closeRename(); } }} />
      {task.version !== titleSnapshot.version && <button type="button" disabled={busy} aria-label="Загрузить актуальную версию названия" title="Загрузить актуальную версию названия" onClick={() => { setTitle(task.title); setTitleSnapshot(task); }}>↻</button>}
      <button type="submit" disabled={busy} aria-label="Сохранить название">✓</button><button type="button" disabled={busy} aria-label="Отменить название" onClick={closeRename}>×</button>
    </form> : <button ref={titleButton} type="button" className={`task-row ${selected ? "selected" : ""} ${task.status === "done" ? "is-done" : ""}`} aria-current={selected ? "true" : undefined} title={task.title} onClick={onSelect} onKeyDown={event => {
      if (trashed || busy) return;
      if (event.key === "F2") { event.preventDefault(); rename(); }
      const field = ({ s: "status", p: "priority", d: "deadline_at" } as Record<string, TaskField>)[event.key];
      if (field && !event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); onProperty(field, event.currentTarget); }
    }}><span className="task-row-title">{task.parent_id && <span aria-label="Подзадача">↳ </span>}{task.title}</span></button>}
    <div className="task-row-properties"><button type="button" className={`task-row-property task-row-status status-${task.status}`} aria-label="Изменить статус" title={statusLabels[task.status]} disabled={busy || trashed} onClick={event => onProperty("status", event.currentTarget)}><span aria-hidden="true">{statusIcons[task.status]}</span><span>{statusLabels[task.status]}</span></button>
    <button type="button" className="task-row-property task-row-priority" aria-label="Изменить приоритет" title={priorityLabels[task.priority]} disabled={busy || trashed} onClick={event => onProperty("priority", event.currentTarget)}><span aria-hidden="true">{priorityIcons[task.priority]}</span><span>{priorityLabels[task.priority]}</span></button>
    <button type="button" className={`task-row-property task-row-deadline ${task.is_overdue ? "task-overdue" : ""}`} aria-label="Изменить срок" title={task.deadline_at ? prettyDate(new Date(task.deadline_at), timeZone, { day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" }) : "Срок не задан"} disabled={busy || trashed} onClick={event => onProperty("deadline_at", event.currentTarget)}>{task.deadline_at ? prettyDate(new Date(task.deadline_at), timeZone, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "Без срока"}</button></div>
    {!trashed && <div className="task-row-menu"><button type="button" aria-label="Действия задачи" onClick={event => { const box = event.currentTarget.getBoundingClientRect(); setMenuPosition({ left: Math.max(8, Math.min(box.right - 230, window.innerWidth - 238)), top: Math.max(8, Math.min(box.bottom + 4, window.innerHeight - 220)) }); setMenuOpen(true); }}>⋯</button>
      {menuOpen && <Modal title="Действия задачи" className="task-context-dialog" style={menuPosition} initialFocus=".task-context-actions button" onClose={() => setMenuOpen(false)}><div className="task-context-actions"><button type="button" disabled={busy} onClick={rename}>Переименовать <kbd>F2</kbd></button><button type="button" disabled={busy} onClick={() => { setMenuOpen(false); onEdit(); }}>Все параметры</button><button type="button" disabled={busy} onClick={() => { setMenuOpen(false); onChild(); }}>Добавить подзадачу</button></div></Modal>}
    </div>}
    {trashed && <small className="task-trash-scope">{task.trash_batch_id === task.id ? "Корень удалённой ветки" : "Часть удалённой ветки"}</small>}
  </li>;
}

export function TaskRows({ tasks, selectedId, timeZone, busy, draftReset, onDirtyChange, onSelect, onPatch, onProperty, onEdit, onChild }: {
  tasks: TaskSummary[]; selectedId: string | null; timeZone: string; busy: boolean; draftReset: number;
  onDirtyChange: (id: string, dirty: boolean) => void; onSelect: (id: string) => void; onPatch: PatchTask;
  onProperty: (task: TaskSummary, field: TaskField, trigger: HTMLElement) => void;
  onEdit: (task: TaskSummary) => void; onChild: (id: string) => void;
}) {
  return <ul className="task-list">{tasks.map(task => <TaskRow key={`${task.id}:${draftReset}`} task={task} selected={selectedId === task.id} timeZone={timeZone} busy={busy} onDirtyChange={onDirtyChange} onSelect={() => onSelect(task.id)} onPatch={onPatch} onProperty={(field, trigger) => onProperty(task, field, trigger)} onEdit={() => onEdit(task)} onChild={() => onChild(task.id)} />)}</ul>;
}
