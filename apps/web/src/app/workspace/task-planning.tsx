"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RequestError, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, Pager, QueryState, useAction } from "@/shared/ui";
import { dateTimeLocal, dayStart, shiftDate, localInstants, resolveLocalTime } from "./calendar-time";
import "./task-planning.css";

export const planningBase = "/api/v1/tasks/planning";
export type PlanningTask = { id: string; title: string; status: string; version: number; remaining_minutes?: number | null };
export type WorkSession = { id: string; task_id: string; starts_at: string; ends_at: string; pinned: boolean; cancelled: boolean; version: number };
export type WorkPlan = {
  id: string; digest: string; timezone: string; verified: boolean; status: string; expires_at: string;
  sessions: { task_id: string; starts_at: string; ends_at: string; retained_id: string | null }[];
  cancelled_sessions: string[];
  task_titles?: Record<string, string>;
  previous_sessions?: WorkSession[]; protected_sessions?: WorkSession[];
  unplaced: { task_id: string; minutes: number | null; reason: string }[]; warnings: string[];
};
type WeeklyWindow = { weekday: number; start_minute: number; end_minute: number };
type Preferences = { version: number; windows: WeeklyWindow[]; session_minutes: number; break_minutes: number };
const days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const reasons: Record<string, string> = {
  inactive_task: "Задача закрыта или удалена", remaining_work_required: "Укажите остаток работы",
  unresolved_dependencies: "Сначала нужно разместить или завершить предшественников",
  not_placed_in_allowed_windows: "Не разместилось в разрешённых окнах",
  protected_sessions_require_review: "Нужно проверить защищённые сессии и остаток работы",
  session_in_progress: "Сессия уже идёт; уточните остаток после неё",
};
export function planningWarning(value: string) {
  if (value === "work_windows_required") return "Задайте недельные часы работы или окно для этого запроса.";
  if (value.includes("schedule") || value.includes("sync")) return "Полнота или актуальность учебного расписания не подтверждена. План условный, применить его пока нельзя.";
  return "Есть ограничение полноты данных. Проверьте источники перед применением.";
}
export function workTime(value: string, timezone: string) {
  return new Intl.DateTimeFormat("ru", { timeZone: timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}
export function PlanDetails({ plan, titles = {} }: { plan: WorkPlan; titles?: Record<string, string> }) {
  const title = (id: string) => plan.task_titles?.[id] ?? titles[id] ?? `Задача ${id}`;
  return <section className="work-plan" aria-label="Просмотр плана">
    <p>Часовой пояс: {plan.timezone}. Подтвердить до {workTime(plan.expires_at, plan.timezone)}.</p>
    {!plan.verified && <p role="status" className="form-error">Условный план. Применение недоступно.</p>}
    {plan.warnings.map((warning, index) => <p key={index} className="muted">{planningWarning(warning)}</p>)}
    <h4>Рабочие сессии</h4>
    {plan.sessions.length ? <ol>{plan.sessions.map((session, index) => <li key={index}><strong>{title(session.task_id)}</strong><br />{workTime(session.starts_at, plan.timezone)} — {workTime(session.ends_at, plan.timezone)} · {session.retained_id ? "сохранить существующую" : "создать"}</li>)}</ol> : <p>Новых или переносимых сессий нет.</p>}
    {!!plan.cancelled_sessions.length && <><h4>Отменить прежние сессии</h4><ul>{plan.cancelled_sessions.map(id => {
      const old = plan.previous_sessions?.find(item => item.id === id);
      return <li key={id}>{old ? <>{title(old.task_id)} · {workTime(old.starts_at, plan.timezone)} — {workTime(old.ends_at, plan.timezone)}</> : id}</li>;
    })}</ul></>}
    {!!plan.protected_sessions?.length && <details><summary>Защищённые сессии ({plan.protected_sessions.length})</summary><ul>{plan.protected_sessions.map(item => <li key={item.id}>{title(item.task_id)} · {workTime(item.starts_at, plan.timezone)} — {workTime(item.ends_at, plan.timezone)}{item.pinned ? " · закреплена" : " · сохраняется"}</li>)}</ul></details>}
    {!!plan.unplaced.length && <><h4>Осталось разместить</h4><ul>{plan.unplaced.map((item, index) => <li key={index}>{title(item.task_id)}: {item.minutes == null ? "объём неизвестен" : `${item.minutes} мин`} · {reasons[item.reason] ?? "Требуется уточнение"}</li>)}</ul><p className="muted">Это результат текущего алгоритма, а не доказательство невозможности другого плана.</p></>}
    <p className="muted">Прошедшая сессия не означает выполнение задачи. Остаток работы меняется только явно.</p>
  </section>;
}

function minuteText(value: number) { return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`; }
function minuteValue(value: string) { const [hours, minutes] = value.split(":").map(Number); return hours * 60 + minutes; }
function PreferencesForm({ preferences, onSaved }: { preferences: Preferences; onSaved: () => Promise<unknown> }) {
  const [windows, setWindows] = useState(preferences.windows);
  const [session, setSession] = useState(preferences.session_minutes);
  const [pause, setPause] = useState(preferences.break_minutes);
  const action = useAction();
  return <form className="work-form" onSubmit={event => { event.preventDefault(); void action.run(async () => {
    await writeJson(planningBase + "/preferences", "PUT", { expected_version: preferences.version, windows, session_minutes: session, break_minutes: pause });
    await onSaved();
  }); }}>
    <h3>Недельные часы работы</h3><p className="muted">Используется часовой пояс профиля. Можно добавить несколько окон на день.</p>
    {windows.map((window, index) => <div key={index} className="work-window">
      <select aria-label={`День окна ${index + 1}`} value={window.weekday} onChange={event => setWindows(windows.map((item, at) => at === index ? { ...item, weekday: Number(event.target.value) } : item))}>{days.map((day, value) => <option key={value} value={value}>{day}</option>)}</select>
      <input aria-label={`Начало окна ${index + 1}`} type="time" required value={minuteText(window.start_minute)} onChange={event => setWindows(windows.map((item, at) => at === index ? { ...item, start_minute: minuteValue(event.target.value) } : item))} />
      <input aria-label={`Конец окна ${index + 1}`} type="time" required value={minuteText(window.end_minute === 1440 ? 0 : window.end_minute)} onChange={event => setWindows(windows.map((item, at) => at === index ? { ...item, end_minute: minuteValue(event.target.value) || 1440 } : item))} />
      <button type="button" className="text-action" aria-label={`Удалить окно ${index + 1}`} onClick={() => setWindows(windows.filter((_, at) => at !== index))}>Удалить</button>
    </div>)}
    <button type="button" className="secondary-button" disabled={windows.length >= 28} onClick={() => setWindows([...windows, { weekday: 0, start_minute: 540, end_minute: 1020 }])}>Добавить окно</button>
    <div className="work-fields"><label>Сессия, мин<input type="number" min={15} max={240} required value={session} onChange={event => setSession(Number(event.target.value))} /></label><label>Перерыв, мин<input type="number" min={0} max={120} required value={pause} onChange={event => setPause(Number(event.target.value))} /></label></div>
    <button className="secondary-button" disabled={action.busy}>Сохранить часы работы</button><button type="button" className="text-action" disabled={action.busy} onClick={() => void onSaved()}>Загрузить актуальные настройки</button><ActionFeedback {...action} />
  </form>;
}

function LocalTimeInput({ label, value, choice, onChange, onChoice, timezone }: { label: string; value: string; choice: string; onChange: (value: string) => void; onChoice: (value: string) => void; timezone: string }) {
  const options = localInstants(value, timezone);
  return <label>{label}<input type="datetime-local" required value={value} onChange={event => { onChange(event.target.value); onChoice(""); }} />{value && options.length === 0 && <span className="form-error">Такого местного времени нет.</span>}{options.length > 1 && <select required aria-label={`${label}: смещение`} value={choice} onChange={event => onChoice(event.target.value)}><option value="">Выберите смещение часов</option>{options.map(option => <option key={option} value={option}>{workTime(option, timezone)} · {option}</option>)}</select>}</label>;
}

function SessionEditor({ taskId, timezone, current, onSaved, onClose }: { taskId: string; timezone: string; current?: WorkSession; onSaved: () => Promise<unknown>; onClose: () => void }) {
  const [start, setStart] = useState(current ? dateTimeLocal(new Date(current.starts_at), timezone) : "");
  const [end, setEnd] = useState(current ? dateTimeLocal(new Date(current.ends_at), timezone) : "");
  const [startChoice, setStartChoice] = useState(""); const [endChoice, setEndChoice] = useState("");
  const [pinned, setPinned] = useState(current?.pinned ?? false);
  const [ack, setAck] = useState(false);
  const [check, setCheck] = useState<{ payload: Record<string, unknown>; snapshot: string; conflict: boolean; verified: boolean } | null>(null);
  const action = useAction();
  function edited(change: () => void) { change(); setCheck(null); setAck(false); }
  async function inspect(event: FormEvent) { event.preventDefault(); await action.run(async () => {
    const payload = { task_id: taskId, starts_at: resolveLocalTime(start, timezone, startChoice, current?.starts_at), ends_at: resolveLocalTime(end, timezone, endChoice, current?.ends_at), ...(current ? { session_id: current.id } : {}) };
    const result = await writeJson<{ snapshot: string; occupied: unknown[]; verified: boolean }>(planningBase + "/sessions/check", "POST", payload);
    setCheck({ payload, snapshot: result.snapshot, conflict: !!result.occupied.length, verified: result.verified });
  }, "Проверка выполнена. Подтвердите сохранение."); }
  return <form className="work-form" onSubmit={event => void inspect(event)}>
    <h4>{current ? "Перенести сессию" : "Создать рабочую сессию"}</h4>
    <div className="work-fields"><LocalTimeInput label="Начало сессии" value={start} choice={startChoice} onChange={value => edited(() => setStart(value))} onChoice={value => edited(() => setStartChoice(value))} timezone={timezone} /><LocalTimeInput label="Конец сессии" value={end} choice={endChoice} onChange={value => edited(() => setEnd(value))} onChoice={value => edited(() => setEndChoice(value))} timezone={timezone} /></div>
    <label className="checkbox-label"><input type="checkbox" checked={pinned} onChange={event => setPinned(event.target.checked)} />Закрепить: не переносить при перепланировании</label>
    <button className="secondary-button" disabled={action.busy}>Проверить занятость</button>
    {check && <div role="group" aria-label="Подтверждение сессии"><p>{check.conflict ? "Есть пересечение с занятым временем." : "Пересечений в сохранённых данных нет."}</p>{!check.verified && <p>Полнота учебного расписания неизвестна.</p>}{(check.conflict || !check.verified) && <label className="checkbox-label"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} />Разместить вручную с указанными ограничениями</label>}
      <button type="button" className="primary-button" disabled={action.busy || ((check.conflict || !check.verified) && !ack)} onClick={() => void action.run(async () => {
        try { await writeJson(planningBase + "/sessions", "POST", { ...check.payload, snapshot: check.snapshot, pinned, acknowledge_conflicts: ack, ...(current ? { expected_version: current.version } : {}) }); }
        catch (error) { setCheck(null); if (error instanceof RequestError && error.status === 409) throw new Error("Данные изменились. Проверьте занятость повторно; сессия не сохранена."); throw error; }
        await onSaved(); onClose();
      })}>Подтвердить сессию</button></div>}
    <button type="button" className="text-action" disabled={action.busy} onClick={onClose}>Закрыть форму сессии</button><ActionFeedback {...action} />
  </form>;
}

export function PlanningButton({ timezone, taskId, label = "Планирование" }: { timezone: string; taskId?: string; label?: string }) {
  const [open, setOpen] = useState(false);
  return <><button className="task-secondary" type="button" onClick={() => setOpen(true)}>{label}</button>{open && <PlanningDialog timezone={timezone} taskId={taskId} onClose={() => setOpen(false)} />}</>;
}
function PlanningDialog({ timezone, taskId, onClose }: { timezone: string; taskId?: string; onClose: () => void }) {
  const client = useQueryClient(); const action = useAction();
  const [clock, setClock] = useState(Date.now);
  useEffect(() => { const timer = window.setInterval(() => setClock(Date.now()), 30000); return () => window.clearInterval(timer); }, []);
  const [selected, setSelected] = useState<string[]>(taskId ? [taskId] : []);
  const [offset, setOffset] = useState(0);
  const [start, setStart] = useState(() => dateTimeLocal(new Date(Date.now() + 3600_000), timezone));
  const [end, setEnd] = useState(() => dateTimeLocal(new Date(Date.now() + 7 * 86400_000), timezone));
  const [startChoice, setStartChoice] = useState(""); const [endChoice, setEndChoice] = useState("");
  const [oneOff, setOneOff] = useState(false); const [replan, setReplan] = useState(false);
  const [plan, setPlan] = useState<WorkPlan | null>(null); const [partial, setPartial] = useState(false);
  const [editing, setEditing] = useState<{ taskId: string; current?: WorkSession } | null>(null);
  const [range] = useState(() => ({ starts_at: new Date(Date.now() - 7 * 86400_000).toISOString(), ends_at: new Date(Date.now() + 31 * 86400_000).toISOString() }));
  const preferences = useQuery({ queryKey: ["work-preferences"], queryFn: ({ signal }) => requestJson<Preferences>(planningBase + "/preferences", { signal }) });
  const tasks = useQuery({ queryKey: ["work-task-picker", offset], queryFn: ({ signal }) => requestJson<{ items: PlanningTask[] }>(`/api/v1/tasks?limit=20&offset=${offset}`, { signal }) });
  const detail = useQuery({ queryKey: ["task-detail", taskId], enabled: !!taskId, queryFn: ({ signal }) => requestJson<PlanningTask>(`/api/v1/tasks/${taskId}`, { signal }) });
  const sessions = useQuery({ queryKey: ["work-sessions", range], queryFn: ({ signal }) => requestJson<WorkSession[]>(`${planningBase}/sessions?${new URLSearchParams(range)}`, { signal }) });
  const titles = Object.fromEntries([...(tasks.data?.items ?? []), ...(detail.data ? [detail.data] : [])].map(item => [item.id, item.title]));
  async function refresh() { await Promise.all([client.invalidateQueries({ queryKey: ["work-sessions"] }), client.invalidateQueries({ queryKey: ["calendar-task-sessions"] }), client.invalidateQueries({ queryKey: ["workspace-calendar"] })]); }
  function changed(change: () => void) { change(); setPlan(null); setPartial(false); }
  return <Modal title="Планирование задач" wide onClose={() => { if (!action.busy) onClose(); }}><div className="work-planning">
    <h2>Планирование задач</h2><p>Часовой пояс: {timezone}. Укажите остаток работы в самой задаче. Подзадачи планируются без повторного учёта родителя.</p>
    <QueryState pending={preferences.isPending} error={preferences.error} retry={() => void preferences.refetch()} />
    {preferences.data && <details><summary>Часы работы и перерывы</summary>{preferences.data.version > 0 && <p role="status">Сохранённые настройки: версия {preferences.data.version}</p>}<PreferencesForm key={preferences.data.version} preferences={preferences.data} onSaved={async () => { changed(() => {}); await preferences.refetch(); }} /></details>}
    <section><h3>Задачи для плана</h3><QueryState pending={tasks.isPending} error={tasks.error} retry={() => void tasks.refetch()} />
      {tasks.data?.items.filter(item => ["todo", "in_progress"].includes(item.status)).map(item => <label key={item.id} className="checkbox-label"><input type="checkbox" checked={selected.includes(item.id)} onChange={event => changed(() => setSelected(event.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id)))} />{item.title} · остаток: {item.remaining_minutes == null ? "не указан" : `${item.remaining_minutes} мин`}</label>)}
      <Pager offset={offset} count={tasks.data?.items.length ?? 0} size={20} onChange={setOffset} /><p>Выбрано: {selected.length}</p>
    </section>
    <form className="work-form" onSubmit={event => { event.preventDefault(); void action.run(async () => {
      const starts_at = resolveLocalTime(start, timezone, startChoice), ends_at = resolveLocalTime(end, timezone, endChoice);
      const result = await writeJson<WorkPlan>(planningBase + "/plans", "POST", { task_ids: selected, starts_at, ends_at, replan, ...(oneOff ? { windows: [{ starts_at, ends_at }] } : {}) });
      setPlan(result); setPartial(false);
    }, "План подготовлен. Проверьте его перед подтверждением."); }}>
      <h3>Период планирования</h3><div className="work-fields"><LocalTimeInput label="Планировать с" value={start} choice={startChoice} onChange={value => changed(() => setStart(value))} onChoice={value => changed(() => setStartChoice(value))} timezone={timezone} /><LocalTimeInput label="Планировать до" value={end} choice={endChoice} onChange={value => changed(() => setEnd(value))} onChoice={value => changed(() => setEndChoice(value))} timezone={timezone} /></div>
      <label className="checkbox-label"><input type="checkbox" checked={oneOff} onChange={event => changed(() => setOneOff(event.target.checked))} />Разрешить весь этот интервал только для данного запроса</label>
      <label className="checkbox-label"><input type="checkbox" checked={replan} onChange={event => changed(() => setReplan(event.target.checked))} />Предложить перенос будущих незакреплённых сессий, включая ручные</label>
      <button className="primary-button" disabled={action.busy || !selected.length || selected.length > 100}>Подготовить план</button>
    </form>
    {plan && <><PlanDetails plan={plan} titles={titles} />{plan.status === "applied" ? <p role="status">План применён.</p> : <><p>Все создания и отмены применятся вместе. Изменение исходных данных потребует нового плана.</p>{!!plan.unplaced.length && <label className="checkbox-label"><input type="checkbox" checked={partial} onChange={event => setPartial(event.target.checked)} />Подтверждаю частичный план и указанный остаток</label>}<button className="primary-button" disabled={action.busy || !plan.verified || (!!plan.unplaced.length && !partial)} onClick={() => void action.run(async () => {
      try { setPlan(await writeJson<WorkPlan>(`${planningBase}/plans/${plan.id}/apply`, "POST", { digest: plan.digest, accept_partial: partial })); }
      catch (error) { setPlan(null); if (error instanceof RequestError && error.status === 409) throw new Error("План устарел. Ничего не применено. Подготовьте новый план."); throw error; }
      await refresh();
    }, "План применён.")}>Подтвердить план целиком</button></>}</>}
    <section><h3>Рабочие сессии · ближайший месяц и прошлая неделя</h3><button className="text-action" onClick={() => void refresh()}>Обновить сессии</button><QueryState pending={sessions.isPending} error={sessions.error} retry={() => void sessions.refetch()} />
      {sessions.data?.filter(item => !taskId || item.task_id === taskId).map(item => <div className="work-session" key={item.id}><p><strong>{titles[item.task_id] ?? "Рабочая сессия"}</strong> · {workTime(item.starts_at, timezone)} — {workTime(item.ends_at, timezone)}{item.cancelled ? " · отменена" : item.pinned ? " · закреплена" : ""}</p>{!item.cancelled && Date.parse(item.starts_at) > clock && <div className="work-actions"><button className="secondary-button" disabled={action.busy} onClick={() => setEditing({ taskId: item.task_id, current: item })}>Перенести сессию</button><button className="secondary-button" disabled={action.busy} onClick={() => void action.run(async () => { await writeJson(`${planningBase}/sessions/${item.id}`, "PATCH", { expected_version: item.version, pinned: !item.pinned }); setPlan(null); await refresh(); })}>{item.pinned ? "Открепить" : "Закрепить"}</button><button className="secondary-button" disabled={action.busy} onClick={() => void action.run(async () => { await writeJson(`${planningBase}/sessions/${item.id}`, "PATCH", { expected_version: item.version, cancel: true }); setPlan(null); await refresh(); })}>Отменить сессию</button></div>}</div>)}
      {!sessions.data?.length && !sessions.isPending && <p>Сессий в этом периоде нет.</p>}
      {selected.length === 1 && <button className="secondary-button" onClick={() => setEditing({ taskId: selected[0] })}>Добавить сессию вручную</button>}
      {editing && <SessionEditor key={editing.current?.id ?? editing.taskId} taskId={editing.taskId} current={editing.current} timezone={timezone} onSaved={async () => { setPlan(null); await refresh(); }} onClose={() => setEditing(null)} />}
    </section><ActionFeedback {...action} />
  </div></Modal>;
}

export function CalendarTaskSessions({ from, to, timezone }: { from: string; to: string; timezone: string }) {
  const [showSessions, setShowSessions] = useState(true);
  const [showDeadlines, setShowDeadlines] = useState(false);
  const start = dayStart(from, timezone).toISOString();
  const end = dayStart(shiftDate(to, 1), timezone).toISOString();
  const enabled = showSessions || showDeadlines;
  const query = useQuery({ queryKey: ["calendar-task-sessions", from, to, timezone, showSessions, showDeadlines], enabled, queryFn: ({ signal }) => requestJson<{ sessions: { source_event_id: string; task_id: string; title: string; starts_at: string; ends_at: string; pinned: boolean }[]; deadlines: { task_id: string; title: string; deadline_at: string; blocks_time: false }[] }>(`${planningBase}/calendar?${new URLSearchParams({ starts_at: start, ends_at: end, include_sessions: String(showSessions), include_deadlines: String(showDeadlines) })}`, { signal }) });
  return <section className="panel work-calendar" aria-label="Рабочие сессии задач"><h3>Задачи в календаре</h3>
    <label className="checkbox-label"><input type="checkbox" checked={showSessions} onChange={event => setShowSessions(event.target.checked)} />Показывать рабочие сессии</label>
    <label className="checkbox-label"><input type="checkbox" checked={showDeadlines} onChange={event => setShowDeadlines(event.target.checked)} />Показывать сроки задач</label>
    <QueryState pending={enabled && query.isPending} error={query.error} retry={() => void query.refetch()} />
    {showSessions && query.data?.sessions.map(item => <div key={item.source_event_id}><p><strong>{item.title}</strong> · {workTime(item.starts_at, timezone)} — {workTime(item.ends_at, timezone)}{item.pinned ? " · закреплена" : ""}</p><PlanningButton timezone={timezone} taskId={item.task_id} label="Открыть сессию задачи" /></div>)}
    {showDeadlines && query.data?.deadlines.map(item => <div key={item.task_id}><p><strong>Срок: {item.title}</strong> · {workTime(item.deadline_at, timezone)} · не занимает время</p><PlanningButton timezone={timezone} taskId={item.task_id} label="Планировать задачу" /></div>)}
    {enabled && query.data && !query.data.sessions.length && !query.data.deadlines.length && <p className="muted">В выбранных источниках задач нет записей на эту неделю.</p>}
    <p className="muted">Эти фильтры меняют только отображение. Рабочие сессии продолжают учитываться как занятость.</p>
  </section>;
}
