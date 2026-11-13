"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTimeLocal, localInstants, resolveLocalTime } from "./calendar-time";
import { requestJson, writeJson, RequestError, SessionExpiredError } from "@/shared/api";
import { Modal } from "@/shared/ui";
import "./tasks-panel.css";
import { PlanningButton } from "./task-planning";
import { TaskRelations } from "./task-relations";
import { isUnavailableObject, UnavailableObject } from "./unavailable-object";

import { TaskRows, TaskPropertyEditor, statusLabels, priorityLabels, type Task, type TaskSummary, type TaskPatch, type TaskField, type Status, type Priority, type PatchTask } from "./task-controls";

type TaskList = { items: TaskSummary[]; limit: number; offset: number };
type TaskFilter = "all" | Status;
type PriorityFilter = "all" | Priority;

const pageSize = 30;
function taskListPath(offset: number, status: TaskFilter = "all", priority: PriorityFilter = "all", parentId?: string, trashed = false) {
  const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
  if (status !== "all") params.set("status", status);
  if (priority !== "all") params.set("priority", priority);
  if (parentId) params.set("parent_id", parentId);
  if (trashed) params.set("trashed", "true");
  return `/api/v1/tasks?${params}`;
}

function formatDeadline(value: string, timeZone: string) {
  return new Intl.DateTimeFormat("ru-RU", { timeZone, day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

async function writeTask(path: string, method: "POST" | "PATCH", payload: Record<string, unknown>) {
  return writeJson<Task>(path, method, payload);
}

function TaskForm({ task, parentId, initialTitle = "", timeZone, onClose, onSaved, onSessionEnd, onDirtyChange, onBusyChange }: {
  onDirtyChange: (dirty: boolean) => void;
  onBusyChange: (busy: boolean) => void;
  task: Task | null; parentId: string | null; initialTitle?: string; timeZone: string; onClose: () => void; onSaved: (saved: Task) => void; onSessionEnd: () => void;
}) {
  const [snapshot, setSnapshot] = useState(task);
  const [title, setTitle] = useState(task?.title ?? initialTitle);
  const [description, setDescription] = useState(task?.description ?? "");
  const [status, setStatus] = useState<Status>(task?.status ?? "todo");
  const [priority, setPriority] = useState<Priority>(task?.priority ?? "normal");
  const [deadline, setDeadline] = useState(task?.deadline_at ? dateTimeLocal(new Date(task.deadline_at), timeZone) : "");
  const [deadlineChoice, setDeadlineChoice] = useState("");
  const [remaining, setRemaining] = useState(task?.remaining_minutes?.toString() ?? "");
  const [estimate, setEstimate] = useState(task?.estimated_minutes?.toString() ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const formLock = useRef(false);
  const deadlineOptions = useMemo(() => localInstants(deadline, timeZone, snapshot?.deadline_at ?? undefined), [deadline, timeZone, snapshot?.deadline_at]);

  function loadSnapshot(current: Task) {
    setInitialDraft(JSON.stringify([current.title, current.description ?? "", current.status, current.priority, current.deadline_at ? dateTimeLocal(new Date(current.deadline_at), timeZone) : "", current.remaining_minutes?.toString() ?? "", current.estimated_minutes?.toString() ?? ""]));
    setSnapshot(current);
    setTitle(current.title);
    setDescription(current.description ?? "");
    setStatus(current.status);
    setPriority(current.priority);
    setDeadline(current.deadline_at ? dateTimeLocal(new Date(current.deadline_at), timeZone) : "");
    setDeadlineChoice("");
    setEstimate(current.estimated_minutes?.toString() ?? "");
    setRemaining(current.remaining_minutes?.toString() ?? "");
    setConflict(false);
    setError("");
  }

  async function reload() {
    if (!snapshot) return;
    setBusy(true);
    try { loadSnapshot(await requestJson<Task>(`/api/v1/tasks/${snapshot.id}`)); }
    catch (cause) { if (cause instanceof SessionExpiredError) onSessionEnd(); else setError(cause instanceof Error ? cause.message : "Не удалось обновить задачу."); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (formLock.current) return;
    formLock.current = true;
    setBusy(true); setError(""); setConflict(false);
    try {
      const payload: Record<string, unknown> = {
        title: title.trim(), description: description || null, status, priority,
        deadline_at: deadline ? resolveLocalTime(deadline, timeZone, deadlineChoice, snapshot?.deadline_at ?? undefined) : null,
        estimated_minutes: estimate ? Number(estimate) : null,
        remaining_minutes: remaining === "" ? null : Number(remaining),
      };
      if (snapshot) payload.expected_version = snapshot.version;
      else payload.parent_id = parentId;
      const saved = await writeTask(snapshot ? `/api/v1/tasks/${snapshot.id}` : "/api/v1/tasks", snapshot ? "PATCH" : "POST", payload);
      onSaved(saved);
    } catch (cause) {
      if (cause instanceof SessionExpiredError) { onSessionEnd(); return; }
      if (cause instanceof RequestError && cause.code === "task_version_conflict") setConflict(true);
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить задачу.");
    } finally { formLock.current = false; setBusy(false); }
  }

  const [initialDraft, setInitialDraft] = useState(() => JSON.stringify([task?.title ?? initialTitle, task?.description ?? "", task?.status ?? "todo", task?.priority ?? "normal", deadline, remaining, estimate]));
  const dirty = JSON.stringify([title, description, status, priority, deadline, remaining, estimate]) !== initialDraft;
  useLayoutEffect(() => { onDirtyChange(dirty || busy); return () => onDirtyChange(false); }, [dirty, busy, onDirtyChange]);
  useLayoutEffect(() => { onBusyChange(busy); return () => onBusyChange(false); }, [busy, onBusyChange]);
  function close() {
    if (busy) return;
    if (!dirty || window.confirm("Закрыть без сохранения изменений задачи?")) onClose();
  }
  return <Modal initialFocus="#task-title" title={snapshot ? "Изменить задачу" : parentId ? "Новая подзадача" : "Новая задача"} onClose={close}>
    <form className="task-dialog" aria-labelledby="task-form-title" onSubmit={submit}>
      <span className="greeting">Личные задачи</span>
      <h2 id="task-form-title">{snapshot ? "Изменить задачу" : parentId ? "Новая подзадача" : "Новая задача"}</h2>
      <p className="task-hint">Срок не занимает время в календаре. Для подзадач действуют правила завершения родителя.</p>
      <label htmlFor="task-title">Название</label>
      <input id="task-title" required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="Например, подготовить отчёт" />
      <label htmlFor="task-description">Описание <span className="optional">необязательно</span></label>
      <textarea id="task-description" maxLength={10000} value={description} onChange={event => setDescription(event.target.value)} placeholder="Что нужно сделать?" />
      <div className="task-form-grid">
        <div><label htmlFor="task-status">Статус</label><select id="task-status" value={status} onChange={event => setStatus(event.target.value as Status)}>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <div><label htmlFor="task-priority">Приоритет</label><select id="task-priority" value={priority} onChange={event => setPriority(event.target.value as Priority)}>{Object.entries(priorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      </div>
      <div className="task-form-grid">
        <div><label htmlFor="task-deadline">Срок <span className="optional">необязательно</span></label><input id="task-deadline" type="datetime-local" value={deadline} onChange={event => { setDeadline(event.target.value); setDeadlineChoice(""); }}/>{deadline && deadlineOptions.length === 0 && <small className="task-field-error">Такого местного времени нет.</small>}{deadlineOptions.length > 1 && <select aria-label="Смещение срока" required value={deadlineChoice} onChange={event => setDeadlineChoice(event.target.value)}><option value="" disabled>Выберите смещение</option>{deadlineOptions.map(value => <option key={value} value={value}>{new Intl.DateTimeFormat("ru-RU", { timeZone, hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" }).format(new Date(value))}</option>)}</select>}</div>
        <div><label htmlFor="task-estimate">Оценка, минуты <span className="optional">необязательно</span></label><input id="task-estimate" type="number" min={1} max={525600} step={1} value={estimate} onChange={event => setEstimate(event.target.value)} placeholder="90" /></div>
      </div>
      <label htmlFor="task-remaining">Осталось работы, минуты</label><input id="task-remaining" type="number" min={0} max={525600} step={1} value={remaining} onChange={event => setRemaining(event.target.value)} placeholder="Уточните для планирования" /><p className="task-hint">Не меняется автоматически после сессий. Для родителя с подзадачами планируется работа подзадач.</p>
      <p className="task-timezone">Часовой пояс: {timeZone}</p>
      {error && <div className="task-error" role="alert">{error}{conflict && <button type="button" disabled={busy} onClick={() => void reload()}>Загрузить актуальную версию</button>}</div>}
      <div className="task-dialog-actions"><button className="task-secondary" type="button" disabled={busy} onClick={close}>Отмена</button><button className="primary-button" disabled={busy}>{busy ? "Сохраняем…" : snapshot ? "Сохранить" : "Создать задачу"}</button></div>
    </form>
  </Modal>;
}

function ParentPicker({ task, onClose, onMoved, onSessionEnd, onBusyChange }: { task: Task; onClose: () => void; onMoved: (saved: Task) => void; onSessionEnd: () => void; onBusyChange: (busy: boolean) => void }) {
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useQuery({ queryKey: ["tasks-parent-picker", offset], queryFn: ({ signal }) => requestJson<TaskList>(taskListPath(offset), { signal }), retry: false });
  useLayoutEffect(() => { onBusyChange(busy); return () => onBusyChange(false); }, [busy, onBusyChange]);

  async function move(parentId: string | null) {
    setBusy(true); setError("");
    try { onMoved(await writeTask(`/api/v1/tasks/${task.id}`, "PATCH", { expected_version: task.version, parent_id: parentId })); }
    catch (cause) { if (cause instanceof SessionExpiredError) onSessionEnd(); else setError(cause instanceof Error ? cause.message : "Не удалось перенести задачу."); }
    finally { setBusy(false); }
  }

  return <Modal title="Выбрать родителя" onClose={() => { if (!busy) onClose(); }}>
    <section className="task-dialog task-picker" aria-labelledby="task-picker-title">
      <h2 id="task-picker-title">Выбрать родителя</h2><p className="task-hint">Задачу нельзя вложить в себя или в собственную подзадачу.</p>
      <button type="button" className="task-picker-item" disabled={busy || task.parent_id === null} onClick={() => void move(null)}>Без родителя · отдельная задача</button>
      {query.isPending && <p role="status">Загружаем задачи…</p>}
      {query.isError && <div className="task-error" role="alert">Не удалось загрузить задачи. <button onClick={() => void query.refetch()}>Повторить</button></div>}
      {query.data && <div className="task-picker-list">{query.data.items.filter(item => item.id !== task.id).map(item => <button key={item.id} type="button" className="task-picker-item" disabled={busy || item.id === task.parent_id} onClick={() => void move(item.id)}>{item.title}<small>{statusLabels[item.status]}</small></button>)}</div>}
      {query.data && (offset > 0 || query.data.items.length === pageSize) && <div className="task-pagination"><button type="button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Назад</button><span>Страница {offset / pageSize + 1}</span><button type="button" disabled={query.data.items.length < pageSize || busy} onClick={() => setOffset(offset + pageSize)}>Далее</button></div>}
      {error && <div className="task-error" role="alert">{error}<button type="button" onClick={onClose}>Закрыть и обновить</button></div>}
    </section>
  </Modal>;
}

function TaskDetails({ id, timeZone, onSelect, onBack, onCreateChild, onEdit, onUpdated, onTrashed, onRestored, onSessionEnd, onOpenPage, onPatch, onQuickChild, onProperty, onDirtyChange, onBusyChange }: {
  onBack: () => void;
  onBusyChange: (busy: boolean) => void;
  onOpenPage: (id: string) => void;
  onDirtyChange: (id: string, dirty: boolean) => void;
  onPatch: PatchTask; onQuickChild: (title: string, parentId?: string) => Promise<boolean>;
  onProperty: (task: TaskSummary, field: TaskField, trigger: HTMLElement) => void;
  id: string; timeZone: string; onSelect: (id: string) => void; onCreateChild: (id: string) => void; onEdit: (task: Task) => void; onUpdated: (task: Task) => void; onTrashed: (task: Task) => void; onRestored: (task: Task) => void; onSessionEnd: () => void;
}) {
  const [childrenOffset, setChildrenOffset] = useState(0);
  const [descriptionEditing, setDescriptionEditing] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [descriptionSnapshot, setDescriptionSnapshot] = useState<Task | null>(null);
  const descriptionTrigger = useRef<HTMLButtonElement>(null);
  function closeDescription() { setDescriptionEditing(false); requestAnimationFrame(() => descriptionTrigger.current?.focus({ preventScroll: true })); }
  const [childTitle, setChildTitle] = useState("");
  const [inlineBusy, setInlineBusy] = useState(false);
  const [moveBusy, setMoveBusy] = useState(false);
  const [relationsBusy, setRelationsBusy] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const objectMenu = useRef<HTMLDetailsElement>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const detail = useQuery({ queryKey: ["task-detail", id], queryFn: ({ signal }) => requestJson<Task>(`/api/v1/tasks/${id}`, { signal }), retry: false });
  useLayoutEffect(() => { onBusyChange(busy || inlineBusy || moveBusy || relationsBusy || planningBusy); return () => onBusyChange(false); }, [busy, inlineBusy, moveBusy, relationsBusy, planningBusy, onBusyChange]);
  const children = useQuery({ queryKey: ["task-children", id, childrenOffset], queryFn: ({ signal }) => requestJson<TaskList>(taskListPath(childrenOffset, "all", "all", id), { signal }), enabled: detail.data?.trashed_at === null, retry: false });
  const parent = useQuery({ queryKey: ["task-detail", detail.data?.parent_id], queryFn: ({ signal }) => requestJson<Task>(`/api/v1/tasks/${detail.data?.parent_id}`, { signal }), enabled: Boolean(detail.data?.parent_id), retry: false });
  useLayoutEffect(() => { onDirtyChange(`description:${id}`, descriptionEditing && descriptionDraft !== (detail.data?.description ?? "")); return () => onDirtyChange(`description:${id}`, false); }, [id, descriptionEditing, descriptionDraft, detail.data?.description, onDirtyChange]);
  useLayoutEffect(() => { onDirtyChange(`child:${id}`, Boolean(childTitle.trim())); return () => onDirtyChange(`child:${id}`, false); }, [id, childTitle, onDirtyChange]);
  if (detail.isPending) return <section className="task-detail" role="status">Загружаем задачу…</section>;
  if (isUnavailableObject(detail.error)) return <UnavailableObject onBack={onBack} />;
  if (detail.isError) return <section className="task-detail"><div className="task-error" role="alert">{detail.error instanceof Error ? detail.error.message : "Не удалось открыть задачу."} <button onClick={() => void detail.refetch()}>Повторить</button></div></section>;
  const task = detail.data;
  const canRestore = task.trashed_at !== null && task.trash_batch_id === task.id;

  async function changeTrash(operation: "trash" | "restore") {
    setBusy(true); setActionError("");
    try {
      const changed = await writeTask(`/api/v1/tasks/${task.id}/${operation}`, "POST", { expected_version: task.version });
      if (operation === "trash") onTrashed(changed);
      else onRestored(changed);
    } catch (cause) {
      if (cause instanceof SessionExpiredError) { onSessionEnd(); return; }
      setActionError(cause instanceof Error ? cause.message : "Не удалось изменить задачу.");
    } finally { setBusy(false); }
  }

  return <section className="task-detail" aria-label="Детали задачи" onKeyDown={event => {
    if (event.key === "Escape" && objectMenu.current?.open) { event.stopPropagation(); objectMenu.current.open = false; objectMenu.current.querySelector("summary")?.focus(); }
  }}>
    <div className="task-detail-top"><span className="greeting">{task.trashed_at ? "Корзина" : "Задача"}</span>{!task.trashed_at && <button type="button" className="task-secondary" onClick={() => onEdit(task)}>Изменить</button>}</div>
    <h2>{task.title}</h2>
    {task.parent_id && <p className="task-parent">Подзадача: {parent.data ? <button type="button" onClick={() => onSelect(parent.data.id)}>{parent.data.title}</button> : parent.isError ? <span>родитель недоступен</span> : <span>загружаем…</span>}</p>}
    {task.trashed_at && <div className="task-badges"><span className={`task-status status-${task.status}`}>{statusLabels[task.status]}</span><span>Приоритет: {priorityLabels[task.priority]}</span>{task.is_overdue && <span className="task-overdue">Срок прошёл</span>}</div>}
    {!task.trashed_at && <div className="task-detail-properties">
      <button type="button" className="task-secondary" onClick={event => onProperty(task, "status", event.currentTarget)}>Статус: {statusLabels[task.status]}</button>
      <button type="button" className="task-secondary" onClick={event => onProperty(task, "priority", event.currentTarget)}>Приоритет: {priorityLabels[task.priority]}</button>
      <button type="button" className="task-secondary" onClick={event => onProperty(task, "deadline_at", event.currentTarget)}>{task.deadline_at ? formatDeadline(task.deadline_at, timeZone) : "Срок: не задан"}</button>{task.is_overdue && <span className="task-overdue">Срок прошёл</span>}
    </div>}
    {descriptionEditing ? <form className="task-description-editor" onSubmit={event => { event.preventDefault(); setInlineBusy(true); void onPatch(descriptionSnapshot ?? task, { description: descriptionDraft || null }).then(ok => { if (ok) closeDescription(); }).finally(() => setInlineBusy(false)); }}>
      <label htmlFor="task-inline-description">Описание задачи</label><textarea name="task-description" autoComplete="off" id="task-inline-description" autoFocus value={descriptionDraft} maxLength={10000} disabled={inlineBusy} onChange={event => setDescriptionDraft(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); if (!inlineBusy) closeDescription(); } }} />
      {descriptionSnapshot && descriptionSnapshot.version !== task.version && <button type="button" className="task-secondary" disabled={inlineBusy} onClick={() => { setDescriptionSnapshot(task); setDescriptionDraft(task.description ?? ""); }}>Загрузить актуальную версию описания</button>}
      <button className="task-secondary" disabled={inlineBusy}>Сохранить описание</button><button type="button" className="text-action" disabled={inlineBusy} onClick={closeDescription}>Отменить описание</button>
    </form> : <div className="task-description-area">{task.description && <p className="task-description">{task.description}</p>}{!task.trashed_at && <button ref={descriptionTrigger} className="text-action" type="button" onClick={() => { setDescriptionSnapshot(task); setDescriptionDraft(task.description ?? ""); setDescriptionEditing(true); }}>{task.description ? "Изменить описание" : "Добавить описание"}</button>}</div>}
    <dl className="task-meta">{task.trashed_at && <div><dt>Срок</dt><dd>{task.deadline_at ? formatDeadline(task.deadline_at, timeZone) : "Не задан"}</dd></div>}<div><dt>Осталось работы</dt><dd>{task.remaining_minutes == null ? "Не указано" : `${task.remaining_minutes} мин`}</dd></div><div><dt>Оценка</dt><dd>{task.estimated_minutes ? `${task.estimated_minutes} мин` : "Не задана"}</dd></div></dl>
    {task.trashed_at ? <div className="task-trash-info"><p>Задача в корзине с {formatDeadline(task.trashed_at, timeZone)}.</p>{canRestore ? <><button className="task-secondary" type="button" disabled={busy || Boolean(task.parent_id && (!parent.data || parent.data.trashed_at))} onClick={() => void changeTrash("restore")}>{busy ? "Восстанавливаем…" : "Восстановить ветку"}</button>{parent.data?.trashed_at && <p>Сначала восстановите родительскую ветку.</p>}</> : <p>Восстановление доступно через корень удалённой ветки.</p>}</div> : <><details className="task-object-menu" ref={objectMenu}><summary>Действия задачи</summary><div className="task-detail-actions"><button className="task-secondary" type="button" onClick={() => { objectMenu.current!.open = false; setShowPicker(true); }}>Перенести</button><button className="task-secondary task-danger" type="button" onClick={() => { objectMenu.current!.open = false; setConfirmTrash(true); }}>В корзину</button></div></details>{confirmTrash && <div className="task-trash-confirm" role="group" aria-label="Подтверждение удаления"><p>Переместить задачу и её активные подзадачи в корзину?</p><button type="button" className="task-secondary task-danger" disabled={busy} onClick={() => void changeTrash("trash")}>{busy ? "Перемещаем…" : "Подтвердить"}</button><button type="button" className="task-secondary" disabled={busy} onClick={() => setConfirmTrash(false)}>Отмена</button></div>}</>}
    {actionError && <div className="task-error" role="alert">{actionError}<button type="button" onClick={() => void detail.refetch()}>Обновить задачу</button></div>}
    {!task.trashed_at && <>
    <div className="task-children-heading"><h3>Подзадачи</h3><button type="button" className="text-action" onClick={() => onCreateChild(task.id)}>+ Подзадача</button></div>
    <form className="task-child-add" onSubmit={event => { event.preventDefault(); setInlineBusy(true); void onQuickChild(childTitle, task.id).then(ok => { if (ok) setChildTitle(""); }).finally(() => setInlineBusy(false)); }}><input name="child-task-title" autoComplete="off" aria-label="Быстро добавить подзадачу" placeholder="+ Подзадача…" required maxLength={200} pattern={".*\\S.*"} value={childTitle} disabled={inlineBusy} onChange={event => setChildTitle(event.target.value)} /><button type="submit" className="task-secondary" disabled={inlineBusy || !childTitle.trim()} aria-label="Добавить подзадачу">Добавить</button></form>
    {children.isPending && <p role="status">Загружаем подзадачи…</p>}
    {children.isError && <div className="task-error" role="alert">Не удалось загрузить подзадачи. <button onClick={() => void children.refetch()}>Повторить</button></div>}
    {children.data && (children.data.items.length ? <ul className="task-children">{children.data.items.map(child => <li key={child.id}><button type="button" onClick={() => onSelect(child.id)}><span>{child.title}</span><small>{statusLabels[child.status]}</small></button></li>)}</ul> : <p className="task-muted">Подзадач пока нет.</p>)}
    {children.data && (childrenOffset > 0 || children.data.items.length === pageSize) && <div className="task-pagination"><button type="button" disabled={childrenOffset === 0} onClick={() => setChildrenOffset(childrenOffset - pageSize)}>Назад</button><span>Страница {childrenOffset / pageSize + 1}</span><button type="button" disabled={children.data.items.length < pageSize} onClick={() => setChildrenOffset(childrenOffset + pageSize)}>Далее</button></div>}
    <PlanningButton timezone={timeZone} taskId={task.id} label="Сессии и планирование задачи" onBusyChange={setPlanningBusy} />
    <TaskRelations task={task} onSelectTask={onSelect} onOpenPage={onOpenPage} onBusyChange={setRelationsBusy} />
    {showPicker && <ParentPicker task={task} onClose={() => { setShowPicker(false); void detail.refetch(); }} onMoved={saved => { setShowPicker(false); onUpdated(saved); }} onSessionEnd={onSessionEnd} onBusyChange={setMoveBusy} />}
    </>}
  </section>;
}

export function TasksPanel({ selectedId, onSelectTask, onBusyChange, timeZone, onSessionEnd, onOpenPage, onDirtyChange }: { selectedId: string | null; onSelectTask: (id: string | null) => void; onBusyChange: (busy: boolean) => void; timeZone: string; onSessionEnd: () => void; onOpenPage: (id: string) => void; onDirtyChange: (dirty: boolean) => void }) {
  const client = useQueryClient();
  const [view, setView] = useState<"active" | "trash">("active");
  const [status, setStatus] = useState<TaskFilter>("all");
  const [priority, setPriority] = useState<PriorityFilter>("all");
  const setSelectedId = onSelectTask;
  const [detailBusy, setDetailBusy] = useState(false);
  const [formBusy, setFormBusy] = useState(false);
  const [planningBusy, setPlanningBusy] = useState(false);
  const [form, setForm] = useState<{ task: Task | null; parentId: string | null; initialTitle?: string } | null>(null);
  const [property, setProperty] = useState<{ task: TaskSummary; field: TaskField; position: CSSProperties } | null>(null);
  const [sort, setSort] = useState("created");
  const [group, setGroup] = useState("none");
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const [createdId, setCreatedId] = useState<string | null>(null);
  const [quickTitle, setQuickTitle] = useState("");
  const [quickBusy, setQuickBusy] = useState(false);
  useLayoutEffect(() => { onBusyChange(quickBusy || detailBusy || formBusy || planningBusy); return () => onBusyChange(false); }, [quickBusy, detailBusy, formBusy, planningBusy, onBusyChange]);
  const [quickError, setQuickError] = useState("");
  const [undo, setUndo] = useState<{ task: TaskSummary; changes: TaskPatch } | null>(null);
  const [draftReset, setDraftReset] = useState(0);
  const dirtyDrafts = useRef(new Set<string>());
  const reportedDirty = useRef(false);
  const dirtyCallback = useRef(onDirtyChange);
  useEffect(() => { dirtyCallback.current = onDirtyChange; }, [onDirtyChange]);
  const markDirty = useCallback((id: string, dirty: boolean) => {
    if (dirty) dirtyDrafts.current.add(id); else dirtyDrafts.current.delete(id);
    const next = dirtyDrafts.current.size > 0;
    if (next !== reportedDirty.current) { reportedDirty.current = next; dirtyCallback.current(next); }
  }, []);
  const markFormDirty = useCallback((dirty: boolean) => markDirty("form", dirty), [markDirty]);
  useEffect(() => { markDirty("quick", Boolean(quickTitle.trim())); }, [quickTitle, markDirty]);
  useEffect(() => { markDirty("write", quickBusy); }, [quickBusy, markDirty]);
  useEffect(() => {
    const unload = (event: BeforeUnloadEvent) => { if (dirtyDrafts.current.size) event.preventDefault(); };
    window.addEventListener("beforeunload", unload);
    return () => { window.removeEventListener("beforeunload", unload); dirtyCallback.current(false); };
  }, []);
  function canChangeList() {
    if (quickBusy || detailBusy || formBusy || planningBusy) return false;
    if (![...dirtyDrafts.current].some(id => id !== "quick")) return true;
    if (!window.confirm("Изменить список без сохранения правок задачи?")) return false;
    setDraftReset(value => value + 1);
    return true;
  }
  const quickLock = useRef(false);
  const quickInput = useRef<HTMLInputElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const list = useInfiniteQuery({ queryKey: ["tasks-list", view, status, priority], initialPageParam: 0,
    queryFn: ({ pageParam, signal }) => requestJson<TaskList>(taskListPath(pageParam, status, priority, undefined, view === "trash"), { signal }),
    getNextPageParam: last => last.items.length === pageSize ? last.offset + pageSize : undefined, retry: false });
  useEffect(() => { if (selectedId) requestAnimationFrame(() => root.current?.querySelector<HTMLButtonElement>(".task-back")?.focus({ preventScroll: true })); }, [selectedId]);
  const loaded = [...new Map(list.data?.pages.flatMap(page => page.items).map(task => [task.id, task])).values()];
  const priorityOrder = ["urgent", "high", "normal", "low"];
  const visible = loaded.filter(task => task.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  if (sort === "priority") visible.sort((a, b) => priorityOrder.indexOf(a.priority) - priorityOrder.indexOf(b.priority));
  if (sort === "deadline") visible.sort((a, b) => (a.deadline_at ? Date.parse(a.deadline_at) : Infinity) - (b.deadline_at ? Date.parse(b.deadline_at) : Infinity));
  const groupKeys = group === "status" ? Object.keys(statusLabels) : group === "priority" ? priorityOrder : ["all"];

  function selectTask(id: string) { setSelectedId(id); }
  function handleSelectTask(id: string) { if (canChangeList()) selectTask(id); }
  function back() {
    if (!canChangeList()) return;
    const previousId = selectedId;
    setSelectedId(null);
    requestAnimationFrame(() => {
      const previous = root.current?.querySelector<HTMLButtonElement>(`.task-line[data-task-id="${previousId}"] .task-row`);
      if (previous?.checkVisibility()) previous.focus({ preventScroll: true });
      else root.current?.querySelector<HTMLButtonElement>(".task-row")?.focus({ preventScroll: true });
    });
  }
  function updated(task: Task, selectAfterSave = true) {
    client.setQueryData(["task-detail", task.id], task);
    for (const key of ["tasks-list", "task-children", "tasks-parent-picker"]) void client.invalidateQueries({ queryKey: [key] });
    if (selectAfterSave) selectTask(task.id);
    setNotice("Задача сохранена.");
  }
  const patchTask: PatchTask = async (task, changes) => {
    if (quickLock.current) return false;
    quickLock.current = true; setQuickBusy(true); setQuickError(""); setNotice(""); setCreatedId(null);
    try {
      const saved = await writeTask(`/api/v1/tasks/${task.id}`, "PATCH", { expected_version: task.version, ...changes });
      const inverse = Object.fromEntries(Object.keys(changes).map(key => [key, task[key as keyof TaskSummary]])) as TaskPatch;
      setUndo(Object.keys(changes).every(key => key in task) ? { task: saved, changes: inverse } : null);
      updated(saved, false);
      setNotice(changes.status === "done" ? "Задача выполнена." : "Задача сохранена.");
      return true;
    } catch (cause) {
      if (cause instanceof SessionExpiredError) onSessionEnd();
      else {
        setQuickError(cause instanceof Error ? cause.message : "Не удалось сохранить задачу.");
        void client.invalidateQueries({ queryKey: ["tasks-list"] });
        void client.invalidateQueries({ queryKey: ["task-detail"] });
      }
      return false;
    } finally { quickLock.current = false; setQuickBusy(false); }
  };
  async function addTask(title: string, parentId?: string) {
    if (quickLock.current || !title.trim()) return false;
    quickLock.current = true; setQuickBusy(true); setQuickError("");
    try {
      const saved = await writeTask("/api/v1/tasks", "POST", { title: title.trim(), ...(parentId ? { parent_id: parentId } : {}) });
      updated(saved, false); setUndo(null); setCreatedId(saved.id); setNotice("Задача создана.");
      if (!parentId) { setQuickTitle(""); setStatus("all"); setPriority("all"); setSearch(""); requestAnimationFrame(() => quickInput.current?.focus()); }
      return true;
    } catch (cause) { if (cause instanceof SessionExpiredError) onSessionEnd(); else setQuickError(cause instanceof Error ? cause.message : "Не удалось создать задачу."); return false; }
    finally { quickLock.current = false; setQuickBusy(false); }
  }
  async function editTask(task: TaskSummary) {
    try { setForm({ task: await requestJson<Task>(`/api/v1/tasks/${task.id}`), parentId: null }); }
    catch (cause) { if (cause instanceof SessionExpiredError) onSessionEnd(); else setQuickError((cause as Error).message); }
  }
  function openProperty(task: TaskSummary, field: TaskField, trigger: HTMLElement) {
    const box = trigger.getBoundingClientRect();
    setQuickError("");
    setProperty({ task, field, position: { left: Math.max(8, Math.min(box.left, window.innerWidth - 368)), top: Math.max(8, Math.min(box.bottom + 6, window.innerHeight - (field === "deadline_at" ? 640 : 300))), maxHeight: window.innerHeight - 16 } });
  }
  async function reloadProperty() {
    if (!property) return;
    try { const task = await requestJson<Task>(`/api/v1/tasks/${property.task.id}`); setProperty({ ...property, task }); setQuickError(""); }
    catch (cause) { if (cause instanceof SessionExpiredError) onSessionEnd(); else setQuickError((cause as Error).message); }
  }
  function changeView(next: "active" | "trash") { if (!canChangeList()) return; setView(next); setSelectedId(null); setStatus("all"); setPriority("all"); setSearch(""); setNotice(""); setUndo(null); }
  function changedTrash(task: Task, next: "active" | "trash") { updated(task); void client.invalidateQueries({ queryKey: ["task-detail"] }); setView(next); setStatus("all"); setPriority("all"); setUndo(null); setNotice(next === "trash" ? "Задача и её активные подзадачи перемещены в корзину." : "Ветка задач восстановлена."); }

  return <div ref={root} className={`feature-page tasks-content ${selectedId ? "task-is-open" : ""}`} onKeyDown={event => {
    if (event.defaultPrevented || (event.target as HTMLElement).closest("input, textarea, select, [contenteditable=true], dialog")) return;
    if (event.key === "Escape" && selectedId) { event.preventDefault(); back(); return; }
    const rows = Array.from(root.current?.querySelectorAll<HTMLButtonElement>(".task-row") ?? []);
    const index = rows.indexOf(event.target as HTMLButtonElement);
    if (index < 0 || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); rows[Math.max(0, Math.min(rows.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))]?.focus(); }
    if (event.key === "n" && view === "active") { event.preventDefault(); quickInput.current?.focus(); }
  }}>
    <div className="page-heading"><h1>Задачи</h1><div className="task-heading-actions"><PlanningButton timezone={timeZone} onBusyChange={setPlanningBusy} /><button className="primary-button task-new" onClick={() => setForm({ task: null, parentId: null, initialTitle: quickTitle })}>+ Новая задача</button></div></div>
    <div className="task-toolbar"><div className="task-view-tabs" role="group" aria-label="Режим списка задач"><button type="button" aria-pressed={view === "active"} onClick={() => changeView("active")}>Активные</button><button type="button" aria-pressed={view === "trash"} onClick={() => changeView("trash")}>Корзина</button></div><details className="task-shortcuts"><summary>Клавиши</summary><p>В списке: ↑ ↓ выбрать строку; Enter открыть; F2 переименовать; S статус; P приоритет; D срок; N добавить. Esc закрыть панель. В поле названия: Enter сохранить, Esc отменить.</p></details></div>
    {quickBusy && <p className="task-save-status" role="status">Сохраняем задачу…</p>}
    {notice && <p className="task-notice" role="status">{notice}{createdId && !loaded.some(task => task.id === createdId) && <button type="button" className="text-action" onClick={() => handleSelectTask(createdId)}>Открыть созданную задачу</button>}{undo && <button type="button" className="text-action" disabled={quickBusy} onClick={() => { const entry = undo; void patchTask(entry.task, entry.changes).then(ok => { if (ok) { setUndo(null); setNotice("Изменение отменено."); } }); }}>Отменить изменение</button>}<button type="button" aria-label="Скрыть уведомление" onClick={() => setNotice("")}>×</button></p>}
    {quickError && !property && <div className="task-error" role="alert">{quickError}<button type="button" onClick={() => void list.refetch()}>Обновить список</button></div>}
    <div className="tasks-layout">
      <section className="task-list-card" aria-label="Список задач">
        <div className="task-list-filters"><label>Статус<select aria-label="Статус" value={status} onChange={event => { if (canChangeList()) setStatus(event.target.value as TaskFilter); }}><option value="all">Все</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Приоритет<select aria-label="Приоритет" value={priority} onChange={event => { if (canChangeList()) setPriority(event.target.value as PriorityFilter); }}><option value="all">Все</option>{Object.entries(priorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <details className="task-display"><summary>Вид</summary><div><label>Группировка<select aria-label="Группировка" value={group} onChange={event => { if (canChangeList()) setGroup(event.target.value); }}><option value="none">Без групп</option><option value="status">По статусу</option><option value="priority">По приоритету</option></select></label><label>Сортировка<select aria-label="Сортировка" value={sort} onChange={event => setSort(event.target.value)}><option value="created">По дате создания</option><option value="deadline">По сроку</option><option value="priority">По приоритету</option></select></label><p>Только загруженные задачи: {loaded.length}. Загрузите ещё, чтобы расширить выборку.</p></div></details>
        </div>
        <div className="task-loaded-scope"><span>Загружено: {loaded.length}{search && ` · найдено: ${visible.length}`}</span><label><span className="sr-only">Поиск среди загруженных задач</span><input name="task-search" autoComplete="off" type="search" placeholder="Найти в загруженных…" value={search} onChange={event => { if (canChangeList()) setSearch(event.target.value); }} /></label></div>
        <div className="task-rows-scroll">
          {list.isPending && <p className="task-list-message" role="status">Загружаем задачи…</p>}
          {list.isError && <div className="task-error" role="alert">{list.error instanceof Error ? list.error.message : "Не удалось загрузить задачи."}<button onClick={() => void list.refetch()}>Повторить</button></div>}
          {list.data && (visible.length ? groupKeys.map(key => {
            const items = group === "none" ? visible : visible.filter(task => task[group as "status" | "priority"] === key);
            if (!items.length) return null;
            const rows = <TaskRows key={key} tasks={items} selectedId={selectedId} timeZone={timeZone} busy={quickBusy} draftReset={draftReset} onDirtyChange={markDirty} onSelect={handleSelectTask} onPatch={patchTask} onProperty={openProperty} onEdit={task => void editTask(task)} onChild={parentId => setForm({ task: null, parentId })} />;
            return group === "none" ? rows : <details open className="task-group" key={key}><summary>{group === "status" ? statusLabels[key as Status] : priorityLabels[key as Priority]}<span>{items.length} загружено</span></summary>{rows}</details>;
          }) : <p className="task-list-message">{status === "all" && priority === "all" && !search ? view === "trash" ? "Корзина пуста." : "Пока нет задач. Создайте первую." : "По этим фильтрам задач нет."}</p>)}
          {list.hasNextPage && <button type="button" className="task-load-more task-secondary" disabled={list.isFetchingNextPage} onClick={() => void list.fetchNextPage()}>{list.isFetchingNextPage ? "Загружаем…" : "Загрузить ещё"}</button>}
        </div>
        {view === "active" && <form className="task-quick-add" onSubmit={event => { event.preventDefault(); void addTask(quickTitle); }}><label className="task-quick-field"><span className="sr-only">Быстро добавить задачу</span><input name="quick-task-title" autoComplete="off" ref={quickInput} placeholder="+ Добавить задачу…" maxLength={200} required pattern={".*\\S.*"} value={quickTitle} disabled={quickBusy} onChange={event => setQuickTitle(event.target.value)} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setQuickTitle(""); } }} /></label><button type="submit" className="task-secondary" disabled={quickBusy || !quickTitle.trim()}>{quickBusy ? "Сохраняем…" : "Добавить"}</button><button type="button" className="text-action" onClick={() => setForm({ task: null, parentId: null, initialTitle: quickTitle })}>Подробнее</button></form>}
      </section>
      {selectedId && <div className="task-detail-surface"><button type="button" className="task-back text-action" onClick={back}>← К списку задач</button><TaskDetails onBack={back} onBusyChange={setDetailBusy} onDirtyChange={markDirty} key={`${selectedId}:${draftReset}`} id={selectedId} timeZone={timeZone} onOpenPage={onOpenPage} onSelect={handleSelectTask} onCreateChild={parentId => setForm({ task: null, parentId })} onEdit={task => setForm({ task, parentId: null })} onUpdated={updated} onPatch={(task, changes) => patchTask(task, changes)} onQuickChild={addTask} onProperty={(task, field, trigger) => openProperty(task, field, trigger)} onTrashed={task => changedTrash(task, "trash")} onRestored={task => changedTrash(task, "active")} onSessionEnd={onSessionEnd} /></div>}
    </div>
    {property && <TaskPropertyEditor key={`${property.task.id}:${property.task.version}:${property.field}`} {...property} timeZone={timeZone} busy={quickBusy} error={quickError} onSave={(task, changes) => patchTask(task, changes)} onReload={() => void reloadProperty()} onClose={() => setProperty(null)} />}
    {form && <TaskForm onBusyChange={setFormBusy} onDirtyChange={markFormDirty} {...form} timeZone={timeZone} onClose={() => setForm(null)} onSaved={task => { if (form.initialTitle !== undefined) setQuickTitle(""); setForm(null); updated(task); setUndo(null); }} onSessionEnd={onSessionEnd} />}
  </div>;
}
