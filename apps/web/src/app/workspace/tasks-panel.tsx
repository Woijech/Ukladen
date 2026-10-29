"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { dateTimeLocal, localInstants, resolveLocalTime } from "./calendar-time";
import { requestJson, writeJson, RequestError, SessionExpiredError } from "@/shared/api";
import { Modal } from "@/shared/ui";
import "./tasks-panel.css";
import { PlanningButton } from "./task-planning";
import { TaskRelations } from "./task-relations";

type Status = "todo" | "in_progress" | "done" | "cancelled";
type Priority = "low" | "normal" | "high" | "urgent";

type TaskSummary = {
  id: string;
  parent_id: string | null;
  title: string;
  status: Status;
  priority: Priority;
  deadline_at: string | null;
  estimated_minutes: number | null;
  remaining_minutes: number | null;
  version: number;
  created_at: string;
  updated_at: string;
  trashed_at: string | null;
  trash_batch_id: string | null;
  is_overdue: boolean;
};
type Task = TaskSummary & { description: string | null };
type TaskList = { items: TaskSummary[]; limit: number; offset: number };
type TaskFilter = "all" | Status;
type PriorityFilter = "all" | Priority;

const pageSize = 30;
const statusLabels: Record<Status, string> = { todo: "К выполнению", in_progress: "В работе", done: "Готово", cancelled: "Отменена" };
const priorityLabels: Record<Priority, string> = { low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" };

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

function TaskForm({ task, parentId, timeZone, onClose, onSaved, onSessionEnd }: {
  task: Task | null; parentId: string | null; timeZone: string; onClose: () => void; onSaved: (saved: Task) => void; onSessionEnd: () => void;
}) {
  const [snapshot, setSnapshot] = useState(task);
  const [title, setTitle] = useState(task?.title ?? "");
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
  const deadlineOptions = useMemo(() => localInstants(deadline, timeZone, snapshot?.deadline_at ?? undefined), [deadline, timeZone, snapshot?.deadline_at]);

  function loadSnapshot(current: Task) {
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
    } finally { setBusy(false); }
  }

  return <Modal title={snapshot ? "Изменить задачу" : parentId ? "Новая подзадача" : "Новая задача"} onClose={() => { if (!busy) onClose(); }}>
    <form className="task-dialog" aria-labelledby="task-form-title" onSubmit={submit}>
      <span className="greeting">ЛИЧНЫЕ ЗАДАЧИ</span>
      <h2 id="task-form-title">{snapshot ? "Изменить задачу" : parentId ? "Новая подзадача" : "Новая задача"}</h2>
      <p className="task-hint">Срок не занимает время в календаре. Для подзадач действуют правила завершения родителя.</p>
      <label htmlFor="task-title">Название</label>
      <input id="task-title" autoFocus required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="Например, подготовить отчёт" />
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
      <div className="task-dialog-actions"><button className="task-secondary" type="button" disabled={busy} onClick={onClose}>Отмена</button><button className="primary-button" disabled={busy}>{busy ? "Сохраняем…" : snapshot ? "Сохранить" : "Создать задачу"}</button></div>
    </form>
  </Modal>;
}

function ParentPicker({ task, onClose, onMoved, onSessionEnd }: { task: Task; onClose: () => void; onMoved: (saved: Task) => void; onSessionEnd: () => void }) {
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const query = useQuery({ queryKey: ["tasks-parent-picker", offset], queryFn: ({ signal }) => requestJson<TaskList>(taskListPath(offset), { signal }), retry: false });

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
      {query.data && <div className="task-pagination"><button type="button" disabled={offset === 0 || busy} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Назад</button><span>Страница {offset / pageSize + 1}</span><button type="button" disabled={query.data.items.length < pageSize || busy} onClick={() => setOffset(offset + pageSize)}>Далее</button></div>}
      {error && <div className="task-error" role="alert">{error}<button type="button" onClick={onClose}>Закрыть и обновить</button></div>}
    </section>
  </Modal>;
}

function TaskDetails({ id, timeZone, onSelect, onCreateChild, onEdit, onUpdated, onTrashed, onRestored, onSessionEnd, onOpenPage }: {
  onOpenPage: (id: string) => void;
  id: string; timeZone: string; onSelect: (id: string) => void; onCreateChild: (id: string) => void; onEdit: (task: Task) => void; onUpdated: (task: Task) => void; onTrashed: (task: Task) => void; onRestored: (task: Task) => void; onSessionEnd: () => void;
}) {
  const [childrenOffset, setChildrenOffset] = useState(0);
  const [showPicker, setShowPicker] = useState(false);
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const detail = useQuery({ queryKey: ["task-detail", id], queryFn: ({ signal }) => requestJson<Task>(`/api/v1/tasks/${id}`, { signal }), retry: false });
  const children = useQuery({ queryKey: ["task-children", id, childrenOffset], queryFn: ({ signal }) => requestJson<TaskList>(taskListPath(childrenOffset, "all", "all", id), { signal }), enabled: detail.data?.trashed_at === null, retry: false });
  const parent = useQuery({ queryKey: ["task-detail", detail.data?.parent_id], queryFn: ({ signal }) => requestJson<Task>(`/api/v1/tasks/${detail.data?.parent_id}`, { signal }), enabled: Boolean(detail.data?.parent_id), retry: false });
  if (detail.isPending) return <section className="task-detail" role="status">Загружаем задачу…</section>;
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

  return <section className="task-detail" aria-label="Детали задачи">
    <div className="task-detail-top"><span className="greeting">{task.trashed_at ? "КОРЗИНА" : "ЗАДАЧА"}</span>{!task.trashed_at && <button type="button" className="task-secondary" onClick={() => onEdit(task)}>Изменить</button>}</div>
    <h2>{task.title}</h2>
    {task.parent_id && <p className="task-parent">Подзадача: {parent.data ? <button type="button" onClick={() => onSelect(parent.data.id)}>{parent.data.title}</button> : parent.isError ? <span>родитель недоступен</span> : <span>загружаем…</span>}</p>}
    <div className="task-badges"><span className={`task-status status-${task.status}`}>{statusLabels[task.status]}</span><span>Приоритет: {priorityLabels[task.priority]}</span>{task.is_overdue && <span className="task-overdue">Срок прошёл</span>}</div>
    {task.description && <p className="task-description">{task.description}</p>}
    <dl className="task-meta"><div><dt>Срок</dt><dd>{task.deadline_at ? formatDeadline(task.deadline_at, timeZone) : "Не задан"}</dd></div><div><dt>Оценка</dt><dd>{task.estimated_minutes ? `${task.estimated_minutes} мин` : "Не задана"}</dd></div></dl>
    {task.trashed_at ? <div className="task-trash-info"><p>Задача в корзине с {formatDeadline(task.trashed_at, timeZone)}.</p>{canRestore ? <><button className="task-secondary" type="button" disabled={busy || Boolean(task.parent_id && (!parent.data || parent.data.trashed_at))} onClick={() => void changeTrash("restore")}>{busy ? "Восстанавливаем…" : "Восстановить ветку"}</button>{parent.data?.trashed_at && <p>Сначала восстановите родительскую ветку.</p>}</> : <p>Восстановление доступно через корень удалённой ветки.</p>}</div> : <><div className="task-detail-actions"><button className="task-secondary" type="button" onClick={() => onCreateChild(task.id)}>+ Подзадача</button><button className="task-secondary" type="button" onClick={() => setShowPicker(true)}>Перенести</button><button className="task-secondary task-danger" type="button" onClick={() => setConfirmTrash(true)}>В корзину</button></div>{confirmTrash && <div className="task-trash-confirm" role="group" aria-label="Подтверждение удаления"><p>Переместить задачу и её активные подзадачи в корзину?</p><button type="button" className="task-secondary task-danger" disabled={busy} onClick={() => void changeTrash("trash")}>{busy ? "Перемещаем…" : "Подтвердить"}</button><button type="button" className="task-secondary" disabled={busy} onClick={() => setConfirmTrash(false)}>Отмена</button></div>}</>}
    {actionError && <div className="task-error" role="alert">{actionError}<button type="button" onClick={() => void detail.refetch()}>Обновить задачу</button></div>}
    {!task.trashed_at && <>
    <p>Осталось работы: {task.remaining_minutes == null ? "не указано" : `${task.remaining_minutes} мин`}</p>
    <PlanningButton timezone={timeZone} taskId={task.id} label="Сессии и планирование задачи" />
    <TaskRelations task={task} onSelectTask={onSelect} onOpenPage={onOpenPage} />
    <div className="task-children-heading"><h3>Подзадачи</h3><span>Прямые дочерние задачи</span></div>
    {children.isPending && <p role="status">Загружаем подзадачи…</p>}
    {children.isError && <div className="task-error" role="alert">Не удалось загрузить подзадачи. <button onClick={() => void children.refetch()}>Повторить</button></div>}
    {children.data && (children.data.items.length ? <ul className="task-children">{children.data.items.map(child => <li key={child.id}><button type="button" onClick={() => onSelect(child.id)}><span>{child.title}</span><small>{statusLabels[child.status]}</small></button></li>)}</ul> : <p className="task-muted">Подзадач пока нет.</p>)}
    {children.data && (childrenOffset > 0 || children.data.items.length === pageSize) && <div className="task-pagination"><button type="button" disabled={childrenOffset === 0} onClick={() => setChildrenOffset(childrenOffset - pageSize)}>Назад</button><span>Страница {childrenOffset / pageSize + 1}</span><button type="button" disabled={children.data.items.length < pageSize} onClick={() => setChildrenOffset(childrenOffset + pageSize)}>Далее</button></div>}
    {showPicker && <ParentPicker task={task} onClose={() => { setShowPicker(false); void detail.refetch(); }} onMoved={saved => { setShowPicker(false); onUpdated(saved); }} onSessionEnd={onSessionEnd} />}
    </>}
  </section>;
}

export function TasksPanel({ timeZone, onSessionEnd, onOpenPage }: { timeZone: string; onSessionEnd: () => void; onOpenPage: (id: string) => void }) {
  const client = useQueryClient();
  const [view, setView] = useState<"active" | "trash">("active");
  const [status, setStatus] = useState<TaskFilter>("all");
  const [priority, setPriority] = useState<PriorityFilter>("all");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<{ task: Task | null; parentId: string | null } | null>(null);
  const [notice, setNotice] = useState("");
  const [quickTitle, setQuickTitle] = useState("");
  const [quickBusy, setQuickBusy] = useState(false);
  const [quickError, setQuickError] = useState("");
  const quickLock = useRef(false);
  const list = useQuery({ queryKey: ["tasks-list", view, status, priority, offset], queryFn: ({ signal }) => requestJson<TaskList>(taskListPath(offset, status, priority, undefined, view === "trash"), { signal }), retry: false });

  function updated(task: Task, select = true) {
    client.setQueryData(["task-detail", task.id], task);
    void client.invalidateQueries({ queryKey: ["tasks-list"] });
    void client.invalidateQueries({ queryKey: ["task-children"] });
    void client.invalidateQueries({ queryKey: ["tasks-parent-picker"] });
    if (select) setSelectedId(task.id);
    setNotice("Задача сохранена.");
  }

  async function quickSave(task?: TaskSummary) {
    if (quickLock.current || (!task && !quickTitle.trim())) return;
    quickLock.current = true;
    setQuickBusy(true); setQuickError(""); setNotice("");
    try {
      const saved = await writeTask(task ? `/api/v1/tasks/${task.id}` : "/api/v1/tasks", task ? "PATCH" : "POST", task
        ? { expected_version: task.version, status: task.status === "done" ? "todo" : "done" }
        : { title: quickTitle.trim() });
      updated(saved, !task);
      if (!task) { setQuickTitle(""); setStatus("all"); setPriority("all"); setOffset(0); }
      setNotice(task ? saved.status === "done" ? "Задача выполнена." : "Задача снова к выполнению." : "Задача создана.");
    } catch (cause) {
      if (cause instanceof SessionExpiredError) onSessionEnd();
      else {
        setQuickError(cause instanceof Error ? cause.message : "Не удалось сохранить задачу.");
        void client.invalidateQueries({ queryKey: ["tasks-list"] });
        void client.invalidateQueries({ queryKey: ["task-detail"] });
      }
    } finally { quickLock.current = false; setQuickBusy(false); }
  }

  function saved(task: Task) {
    setForm(null);
    updated(task);
  }

  function changeView(next: "active" | "trash") {
    setView(next);
    setSelectedId(null);
    setOffset(0);
    setStatus("all");
    setPriority("all");
    setNotice("");
  }

  function changedTrash(task: Task, next: "active" | "trash") {
    client.setQueryData(["task-detail", task.id], task);
    void client.invalidateQueries({ queryKey: ["task-detail"] });
    void client.invalidateQueries({ queryKey: ["tasks-list"] });
    void client.invalidateQueries({ queryKey: ["task-children"] });
    void client.invalidateQueries({ queryKey: ["tasks-parent-picker"] });
    setView(next);
    setOffset(0);
    setStatus("all");
    setPriority("all");
    setSelectedId(task.id);
    setNotice(next === "trash" ? "Задача и её активные подзадачи перемещены в корзину." : "Ветка задач восстановлена.");
  }

  return <div className="feature-page tasks-content">
    <div className="page-heading"><div><span className="greeting">ЛИЧНОЕ ПРОСТРАНСТВО</span><h1>Задачи</h1><p className="heading-subtitle">Планы, сроки и подзадачи — без привязки к учебной группе.</p></div><button className="primary-button task-new" onClick={() => setForm({ task: null, parentId: null })}>+ Новая задача</button></div>
    <PlanningButton timezone={timeZone} />
    <div className="task-view-tabs" role="group" aria-label="Режим списка задач"><button type="button" aria-pressed={view === "active"} onClick={() => changeView("active")}>Активные</button><button type="button" aria-pressed={view === "trash"} onClick={() => changeView("trash")}>Корзина</button></div>
    {notice && <p className="task-notice" role="status">{notice}<button type="button" aria-label="Скрыть уведомление" onClick={() => setNotice("")}>×</button></p>}
    <div className="tasks-layout">
      <section className="task-list-card" aria-label="Список задач">
        <div className="task-list-filters"><label>Статус<select value={status} onChange={event => { setStatus(event.target.value as TaskFilter); setOffset(0); }}><option value="all">Все</option>{Object.entries(statusLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Приоритет<select value={priority} onChange={event => { setPriority(event.target.value as PriorityFilter); setOffset(0); }}><option value="all">Все</option>{Object.entries(priorityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
        {view === "active" && <form className="task-quick-add" onSubmit={event => { event.preventDefault(); void quickSave(); }}>
          <input aria-label="Быстро добавить задачу" placeholder="+ Добавить задачу и нажать Enter" maxLength={200} required pattern={".*\\S.*"} value={quickTitle} disabled={quickBusy} onChange={event => setQuickTitle(event.target.value)} />
          <button type="submit" className="task-secondary" disabled={quickBusy || !quickTitle.trim()}>{quickBusy ? "Сохраняем…" : "Добавить"}</button>
        </form>}
        {quickError && <div className="task-error" role="alert">{quickError}</div>}
        {list.isPending && <p className="task-list-message" role="status">Загружаем задачи…</p>}
        {list.isError && <div className="task-error" role="alert">{list.error instanceof Error ? list.error.message : "Не удалось загрузить задачи."}<button onClick={() => void list.refetch()}>Повторить</button></div>}
        {list.data && (list.data.items.length ? <ul className="task-list">{list.data.items.map(task => <li key={task.id}>{view === "active" && <input className="task-complete" type="checkbox" checked={task.status === "done"} disabled={quickBusy || task.status === "cancelled"} aria-label={`${task.status === "done" ? "Вернуть к выполнению" : "Завершить"}: ${task.title}`} onChange={() => void quickSave(task)} />}<button type="button" className={`task-row ${selectedId === task.id ? "selected" : ""}`} aria-current={selectedId === task.id ? "true" : undefined} onClick={() => setSelectedId(task.id)}><span className="task-row-title">{task.parent_id && <span aria-label="Подзадача">↳ </span>}{task.title}</span><span className="task-row-info"><span className={`task-status status-${task.status}`}>{statusLabels[task.status]}</span><span>{priorityLabels[task.priority]}</span>{view === "trash" && <span>{task.trash_batch_id === task.id ? "Корень удалённой ветки" : "Часть удалённой ветки"}</span>}{task.deadline_at && <span className={task.is_overdue ? "task-overdue" : ""}>{formatDeadline(task.deadline_at, timeZone)}</span>}</span></button></li>)}</ul> : <p className="task-list-message">{status === "all" && priority === "all" ? view === "trash" ? "Корзина пуста." : "Пока нет задач. Создайте первую." : "По этим фильтрам задач нет."}</p>)}
        {list.data && (offset > 0 || list.data.items.length === pageSize) && <div className="task-pagination"><button type="button" disabled={offset === 0} onClick={() => setOffset(offset - pageSize)}>Назад</button><span>Страница {offset / pageSize + 1}</span><button type="button" disabled={list.data.items.length < pageSize} onClick={() => setOffset(offset + pageSize)}>Далее</button></div>}
      </section>
      {selectedId ? <TaskDetails key={selectedId} id={selectedId} timeZone={timeZone} onOpenPage={onOpenPage} onSelect={setSelectedId} onCreateChild={parentId => setForm({ task: null, parentId })} onEdit={task => setForm({ task, parentId: null })} onUpdated={updated} onTrashed={task => changedTrash(task, "trash")} onRestored={task => changedTrash(task, "active")} onSessionEnd={onSessionEnd} /> : <section className="task-detail task-detail-empty"><h2>Выберите задачу</h2><p>Здесь появятся описание, срок и подзадачи.</p></section>}
    </div>
    {form && <TaskForm task={form.task} parentId={form.parentId} timeZone={timeZone} onClose={() => setForm(null)} onSaved={saved} onSessionEnd={onSessionEnd} />}
  </div>;
}
