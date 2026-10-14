"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import "./workspace.css";

type CalendarEvent = {
  id: string;
  source: "official" | "personal";
  source_event_id: string;
  kind: "lesson" | "exam" | "announcement" | "personal";
  title: string;
  starts_at: string;
  ends_at: string;
  location: string | null;
  blocks_time: boolean;
  skipped: boolean;
  lesson_type: string | null;
  subject: string | null;
  rooms: string[];
};

type CalendarPayload = {
  events: CalendarEvent[];
  timezone: string;
  warnings: string[];
};

type PersonalEvent = {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string;
  location: string | null;
  blocks_time: boolean;
};

type UniversityGroup = {
  id: number;
  name: string;
  faculty_name: string;
  faculty_abbrev: string;
  speciality_name: string;
  course: number | null;
};

type AcademicProfile = {
  group: UniversityGroup;
  subgroup: number | null;
};

type GroupContext = {
  group: UniversityGroup;
  schedule_available: boolean;
  subgroups: number[];
  period: { term_label: string | null; period_label: string | null } | null;
};

const weekdays = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"];
const shortWeekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"];
const startHour = 8;
const endHour = 21;
const hourHeight = 68;

function localDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function startOfWeek(date: Date) {
  const result = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  result.setDate(result.getDate() - ((result.getDay() + 6) % 7));
  return result;
}

function shiftDate(date: Date, days: number) {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function prettyDate(date: Date, options: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat("ru-RU", options).format(date);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null;
    if (path === "/api/v1/auth/login" && response.status === 401) throw new Error("Неверная почта или пароль.");
    if (path === "/api/v1/auth/register" && response.status === 409) throw new Error("Аккаунт с такой почтой уже существует.");
    if (response.status === 401) throw new Error("Войдите в аккаунт, чтобы открыть личное пространство.");
    if (response.status === 409) throw new Error("Данные изменились. Обновите страницу и попробуйте ещё раз.");
    if (response.status === 403) throw new Error("Сессия защиты устарела. Обновите страницу и повторите действие.");
    if (response.status === 422) throw new Error(payload?.detail === "Invalid academic selection." ? "Выбери группу и подгруппу из списка." : "Проверь заполненные данные.");
    throw new Error(response.status === 503 ? "Сервис временно недоступен." : "Не удалось выполнить запрос.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function csrfToken() {
  const result = await requestJson<{ csrf_token: string }>("/api/v1/auth/csrf");
  return result.csrf_token;
}

function Icon({ name }: { name: "calendar" | "plus" | "chevron" | "logout" | "sparkle" | "clock" | "menu" | "eye" | "eye-off" | "cap" | "close" }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true as const };
  if (name === "calendar") return <svg {...common}><rect x="3.5" y="5" width="17" height="16" rx="3"/><path d="M8 3v4M16 3v4M3.5 10h17"/><path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01"/></svg>;
  if (name === "plus") return <svg {...common}><path d="M12 5v14M5 12h14"/></svg>;
  if (name === "chevron") return <svg {...common}><path d="m9 18 6-6-6-6"/></svg>;
  if (name === "logout") return <svg {...common}><path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/></svg>;
  if (name === "clock") return <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>;
  if (name === "menu") return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16"/></svg>;
  if (name === "eye") return <svg {...common}><path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.6"/></svg>;
  if (name === "eye-off") return <svg {...common}><path d="m3 3 18 18M10.6 6.2A10.8 10.8 0 0 1 12 6c6.1 0 9.5 6 9.5 6a16 16 0 0 1-3 3.5M6.2 6.3C3.8 7.8 2.5 12 2.5 12s3.4 6 9.5 6c1.1 0 2.1-.2 3-.5"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>;
  if (name === "cap") return <svg {...common}><path d="m2 9 10-5 10 5-10 5L2 9Z"/><path d="M6 11v5c3.5 2.7 8.5 2.7 12 0v-5M22 9v6"/></svg>;
  if (name === "close") return <svg {...common}><path d="m6 6 12 12M18 6 6 18"/></svg>;
  return <svg {...common}><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z"/><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></svg>;
}

function PasswordField({ id, value, onChange, autoComplete, minLength, placeholder }: { id: string; value: string; onChange: (value: string) => void; autoComplete: string; minLength: number; placeholder: string }) {
  const [visible, setVisible] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function revealPassword() {
    if (timer.current) clearTimeout(timer.current);
    setVisible(true);
    timer.current = setTimeout(() => setVisible(false), 3000);
  }

  return <div className="password-control">
    <input id={id} type={visible ? "text" : "password"} autoComplete={autoComplete} minLength={minLength} required value={value} onChange={event => onChange(event.target.value)} placeholder={placeholder} />
    <button className="password-toggle" type="button" onClick={revealPassword} aria-label={visible ? "Пароль виден, скроется через 3 секунды" : "Показать пароль на 3 секунды"} title={visible ? "Скроется через 3 секунды" : "Показать пароль на 3 секунды"}><Icon name={visible ? "eye-off" : "eye"}/></button>
  </div>;
}

function AuthPanel({ onSuccess }: { onSuccess: () => Promise<void> }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const token = await csrfToken();
      await requestJson(mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ email, password }),
      });
      await onSuccess();
    } catch (error) {
      setMessage(error instanceof Error ? (error.message.includes("Войдите") ? "Не удалось войти. Проверьте почту и пароль." : error.message) : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="auth-layout">
    <div className="auth-art" aria-hidden="true"><div className="art-orbit orbit-one"/><div className="art-orbit orbit-two"/><div className="art-card"><span className="art-dot"/><span className="art-line line-long"/><span className="art-line"/><span className="art-event"/></div><span className="art-caption">Твоё спокойное место<br/>для важных планов</span></div>
    <form className="auth-card" onSubmit={submit}>
      <span className="auth-kicker">Личное пространство Ukladen</span>
      <h1>{mode === "login" ? "Войти в Ukladen" : "Создать аккаунт"}</h1>
      <p className="auth-description">Расписание и личные планы — в одном пространстве.</p>
      <label htmlFor="email">Электронная почта</label>
      <input id="email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)} placeholder="name@example.com" />
      <label htmlFor="password">Пароль</label>
      <PasswordField id="password" value={password} onChange={setPassword} autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 12 : 1} placeholder={mode === "register" ? "Не менее 12 символов" : "Твой пароль"}/>
      {message && <p className="form-error" role="alert">{message}</p>}
      <button className="primary-button auth-submit" disabled={busy}>{busy ? "Секунду…" : mode === "login" ? "Войти" : "Зарегистрироваться"}</button>
      <p className="auth-switch">{mode === "login" ? "Впервые здесь?" : "Уже есть аккаунт?"} <button type="button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMessage(""); }}>{mode === "login" ? "Создать аккаунт" : "Войти"}</button></p>
    </form>
  </div>;
}

function GroupPicker({ profile, onClose, onSaved }: { profile: AcademicProfile | null; onClose: () => void; onSaved: (message: string) => void }) {
  const [search, setSearch] = useState("");
  const [groupId, setGroupId] = useState<number | null>(profile?.group.id ?? null);
  const [subgroup, setSubgroup] = useState(profile?.subgroup ? String(profile.subgroup) : "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const groupsQuery = useQuery({ queryKey: ["university-groups"], queryFn: () => requestJson<UniversityGroup[]>("/api/v1/academics/groups"), retry: false });
  const contextQuery = useQuery({
    queryKey: ["university-group-context", groupId],
    queryFn: () => requestJson<GroupContext>(`/api/v1/academics/groups/${groupId}/context`),
    enabled: groupId !== null,
    retry: false,
  });
  const groups = groupsQuery.data ?? [];
  const visibleGroups = groups.filter(group => {
    const needle = search.trim().toLocaleLowerCase("ru-RU");
    return !needle || `${group.name} ${group.faculty_name} ${group.faculty_abbrev} ${group.speciality_name}`.toLocaleLowerCase("ru-RU").includes(needle);
  }).slice(0, 100);
  const selectedGroup = groups.find(group => group.id === groupId) ?? profile?.group ?? null;

  async function saveSelection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (groupId === null) return;
    setSaving(true); setError("");
    try {
      const token = await csrfToken();
      await requestJson<AcademicProfile>("/api/v1/academics/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ group_id: groupId, subgroup: subgroup ? Number(subgroup) : null }),
      });
      let message = "Группа сохранена. Учебное расписание добавлено в календарь.";
      try {
        await requestJson<{ group_id: number }>("/api/v1/schedule/me/sync", { method: "POST", headers: { "X-CSRF-Token": token } });
        message = "Группа сохранена. Загружаем учебное расписание.";
      } catch {
        message = "Группа сохранена. Расписание обновится автоматически.";
      }
      onSaved(message);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Не удалось сохранить группу.");
    } finally { setSaving(false); }
  }

  return <main className="group-page">
    <header className="group-header"><a className="brand-lockup" href="/workspace"><span className="brand-mark"><Icon name="sparkle"/></span><span>ukladen</span></a><button className="cancel-button" type="button" onClick={onClose}>Вернуться в календарь</button></header>
    <div className="group-content">
      <div className="group-intro"><span className="group-icon"><Icon name="cap"/></span><span className="greeting">НАСТРОЙКА РАСПИСАНИЯ</span><h1>{profile ? "Изменить учебную группу" : "Добавь расписание учёбы"}</h1><p>Найди свою группу БГУИР — занятия появятся рядом с личными планами.</p></div>
      <div className="group-picker-layout">
        <section className="group-list-panel"><label htmlFor="group-search">Группа или факультет</label><div className="group-search-wrap"><span>⌕</span><input id="group-search" autoFocus value={search} onChange={event => setSearch(event.target.value)} placeholder="Например, 353501 или ФКСиС" /></div>
          {groupsQuery.isPending && <div className="group-loading">Загружаем список групп…</div>}
          {groupsQuery.isError && <div className="group-error" role="alert">{groupsQuery.error instanceof Error ? groupsQuery.error.message : "Не удалось загрузить список групп."}<button onClick={() => void groupsQuery.refetch()}>Повторить</button></div>}
          {!groupsQuery.isPending && !groupsQuery.isError && visibleGroups.length === 0 && <div className="group-loading">Группы не найдены. Попробуй другой запрос.</div>}
          <div className="group-options" role="listbox" aria-label="Список учебных групп">{visibleGroups.map(group => <button type="button" role="option" aria-selected={group.id === groupId} className={`group-option ${group.id === groupId ? "chosen" : ""}`} key={group.id} onClick={() => { setGroupId(group.id); setSubgroup(""); }}><span className="group-option-name">{group.name}</span><span className="group-option-details">{group.faculty_abbrev} · {group.speciality_name}{group.course ? ` · ${group.course} курс` : ""}</span><span className="group-option-check">{group.id === groupId ? "✓" : ""}</span></button>)}</div>
          {groups.length > 100 && <p className="group-limit-note">Показаны первые 100 результатов. Уточни поиск, чтобы найти свою группу.</p>}
        </section>
        <form className="group-details-panel" onSubmit={saveSelection}>
          {selectedGroup ? <>
            <span className="greeting">ВЫБРАННАЯ ГРУППА</span><h2>{selectedGroup.name}</h2><p className="group-faculty">{selectedGroup.faculty_name}</p>
            {contextQuery.isPending && <p className="group-context-note">Проверяем доступное расписание и подгруппы…</p>}
            {contextQuery.isError && <p className="group-context-note">Не удалось получить список подгрупп. Можно сохранить группу без фильтра.</p>}
            {contextQuery.data && !contextQuery.data.schedule_available && <p className="group-context-note">Для этой группы пока нет опубликованного расписания. Группу можно сохранить.</p>}
            {contextQuery.data?.schedule_available && <>
              <label htmlFor="subgroup">Подгруппа</label><select id="subgroup" value={subgroup} onChange={event => setSubgroup(event.target.value)}><option value="">Все подгруппы</option>{contextQuery.data.subgroups.map(item => <option key={item} value={item}>Подгруппа {item}</option>)}</select>
              {contextQuery.data.period?.term_label && <p className="period-note">{contextQuery.data.period.term_label}{contextQuery.data.period.period_label ? ` · ${contextQuery.data.period.period_label}` : ""}</p>}
            </>}
          </> : <div className="group-empty"><Icon name="cap"/><strong>Выбери группу слева</strong><span>Покажем найденные для неё подгруппы и учебный период.</span></div>}
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="group-actions"><button type="button" className="text-action" onClick={onClose}>Пока без группы</button><button className="primary-button" disabled={!selectedGroup || saving}>{saving ? "Сохраняем…" : profile ? "Сохранить группу" : "Продолжить"}</button></div>
        </form>
      </div>
    </div>
  </main>;
}

export function Workspace() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState(() => new Date());
  const [showEventForm, setShowEventForm] = useState(false);
  const [showGroupPicker, setShowGroupPicker] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [topAccountMenuOpen, setTopAccountMenuOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [loadingAuth, setLoadingAuth] = useState(false);

  const weekStart = useMemo(() => startOfWeek(selected), [selected]);
  const days = useMemo(() => Array.from({ length: 7 }, (_, index) => shiftDate(weekStart, index)), [weekStart]);
  const range = { from: localDate(days[0]), to: localDate(days[6]) };
  const calendarQuery = useQuery({
    queryKey: ["workspace-calendar", range.from, range.to],
    queryFn: () => requestJson<CalendarPayload>(`/api/v1/calendar/events?date_from=${range.from}&date_to=${range.to}`),
    retry: false,
  });
  const meQuery = useQuery({ queryKey: ["workspace-profile"], queryFn: () => requestJson<AcademicProfile | null>("/api/v1/academics/me"), retry: false });
  const apiError = calendarQuery.error instanceof Error ? calendarQuery.error : null;
  const needsAuth = apiError?.message.includes("Войдите") ?? false;
  const events = calendarQuery.data?.events ?? [];
  const today = localDate(new Date());
  const selectedKey = localDate(selected);
  const dateLabel = prettyDate(weekStart, { day: "numeric", month: "long" });
  const weekEndLabel = prettyDate(days[6], { day: "numeric", month: "long", year: "numeric" });
  const selectedEvents = events.filter(event => localDate(new Date(event.starts_at)) === selectedKey).sort((a, b) => a.starts_at.localeCompare(b.starts_at));

  function openCreate(date = selected) {
    setSelected(date);
    const initial = new Date(date.getFullYear(), date.getMonth(), date.getDate(), 10, 0);
    setStartValue(toDateTimeLocal(initial));
    const end = new Date(initial.getTime() + 60 * 60_000);
    setEndValue(toDateTimeLocal(end));
    setTitle(""); setLocation(""); setFormError(""); setShowEventForm(true);
  }

  const [startValue, setStartValue] = useState("");
  const [endValue, setEndValue] = useState("");

  async function reload() {
    setLoadingAuth(true);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] }),
      queryClient.invalidateQueries({ queryKey: ["workspace-profile"] }),
    ]);
    setLoadingAuth(false);
  }

  async function afterAuthentication() {
    await reload();
    try {
      const profile = await queryClient.fetchQuery({
        queryKey: ["workspace-profile"],
        queryFn: () => requestJson<AcademicProfile | null>("/api/v1/academics/me"),
      });
      if (!profile) setShowGroupPicker(true);
    } catch (error) {
      throw error instanceof Error ? error : new Error("Не удалось загрузить профиль.");
    }
  }

  async function afterGroupSaved(message: string) {
    setShowGroupPicker(false);
    setAccountMenuOpen(false);
    setTopAccountMenuOpen(false);
    setToast(message);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] }),
      queryClient.invalidateQueries({ queryKey: ["workspace-profile"] }),
    ]);
    window.setTimeout(() => setToast(""), 3600);
  }

  async function createEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true); setFormError("");
    try {
      const token = await csrfToken();
      await requestJson<PersonalEvent>("/api/v1/calendar/personal-events", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({ title, location: location || null, description: null, starts_at: new Date(startValue).toISOString(), ends_at: new Date(endValue).toISOString(), blocks_time: true }),
      });
      setShowEventForm(false); setToast("Событие добавлено");
      await queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] });
      window.setTimeout(() => setToast(""), 2600);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Не удалось сохранить событие.");
    } finally { setSaving(false); }
  }

  async function removeEvent(event: CalendarEvent) {
    if (event.source !== "personal") return;
    try {
      const token = await csrfToken();
      await requestJson<void>(`/api/v1/calendar/personal-events/${event.source_event_id}`, { method: "DELETE", headers: { "X-CSRF-Token": token } });
      setToast("Событие удалено");
      await queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] });
      window.setTimeout(() => setToast(""), 2600);
    } catch (error) { setToast(error instanceof Error ? error.message : "Не удалось удалить событие."); }
  }

  async function logout() {
    try {
      setAccountMenuOpen(false);
      setTopAccountMenuOpen(false);
      const token = await csrfToken();
      await requestJson<void>("/api/v1/auth/logout", { method: "POST", headers: { "X-CSRF-Token": token } });
      await reload();
    } catch (error) { setToast(error instanceof Error ? error.message : "Не удалось завершить сессию."); }
  }

  if (needsAuth) return <main className="workspace-auth"><AuthPanel onSuccess={afterAuthentication} /></main>;
  if (showGroupPicker) return <GroupPicker profile={meQuery.data ?? null} onClose={() => setShowGroupPicker(false)} onSaved={message => void afterGroupSaved(message)} />;

  return <main className="workspace-shell">
    <aside className="sidebar">
      <a className="brand-lockup" href="/workspace" aria-label="Ukladen — главная"><span className="brand-mark"><Icon name="sparkle" /></span><span>ukladen</span></a>
      <div className="sidebar-section-label">ПРОСТРАНСТВО</div>
      <button className="nav-item active"><Icon name="calendar"/><span>Календарь</span><span className="nav-count">7</span></button>
      <button className="nav-item muted-nav" title="Заметки появятся в следующих версиях"><span className="nav-glyph">▤</span><span>Заметки</span><span className="soon-label">скоро</span></button>
      <button className="nav-item muted-nav" title="Задачи пока не подключены"><span className="nav-glyph">◷</span><span>Задачи</span><span className="soon-label">скоро</span></button>
      <div className="sidebar-spacer"/>
      <div className="sidebar-tip"><span className="tip-icon"><Icon name="sparkle"/></span><strong>В своём ритме</strong><p>Оставь место для того, что важно именно тебе.</p></div>
      <div className="account-area"><button className="account-button" aria-expanded={accountMenuOpen} onClick={() => setAccountMenuOpen(open => !open)}><span className="avatar">U</span><span className="account-copy"><strong>Моё пространство</strong><small>{meQuery.data?.group.name ?? "Личный календарь"}</small></span><span className="account-menu">···</span></button>
        {accountMenuOpen && <div className="account-popover"><div className="popover-heading">Профиль и расписание</div><button onClick={() => { setAccountMenuOpen(false); setShowGroupPicker(true); }}><Icon name="cap"/><span>{meQuery.data ? "Сменить учебную группу" : "Выбрать учебную группу"}</span></button><button onClick={() => void logout()}><Icon name="logout"/><span>Выйти из аккаунта</span></button></div>}
      </div>
    </aside>

    <section className="main-panel">
        <header className="topbar"><button className="mobile-menu" aria-label="Меню профиля" aria-expanded={topAccountMenuOpen} onClick={() => setTopAccountMenuOpen(open => !open)}><Icon name="menu"/></button><div className="breadcrumb">Моё пространство <Icon name="chevron"/> <strong>Календарь</strong></div><div className="topbar-actions"><span className={`connection-dot ${calendarQuery.isError ? "offline" : ""}`}/><span className="connection-label">{calendarQuery.isFetching || loadingAuth ? "Синхронизация" : calendarQuery.isError ? "Нет соединения" : "Синхронизировано"}</span><button className="avatar top-avatar" aria-label="Меню профиля" aria-expanded={topAccountMenuOpen} onClick={() => setTopAccountMenuOpen(open => !open)}>U</button></div>
          {topAccountMenuOpen && <div className="top-account-popover"><div className="popover-heading">Профиль и расписание</div><button onClick={() => { setTopAccountMenuOpen(false); setShowGroupPicker(true); }}><Icon name="cap"/><span>{meQuery.data ? "Сменить учебную группу" : "Выбрать учебную группу"}</span></button><button onClick={() => void logout()}><Icon name="logout"/><span>Выйти из аккаунта</span></button></div>}
        </header>

      <div className="content-wrap">
        <div className="page-heading"><div><div className="greeting">ТВОЯ НЕДЕЛЯ</div><h1>Календарь</h1><p className="heading-subtitle">Спокойный взгляд на предстоящие дни.</p></div><button className="primary-button create-button" onClick={() => openCreate()}><Icon name="plus"/><span>Новое событие</span></button></div>

        <section className="calendar-card" aria-label="Календарь на неделю">
          <div className="calendar-toolbar"><div className="week-title"><strong>{dateLabel} — {weekEndLabel}</strong><span>{prettyDate(selected, { weekday: "long", day: "numeric", month: "long" })}</span></div><div className="calendar-controls"><button className="today-button" onClick={() => setSelected(new Date())}>Сегодня</button><div className="arrow-group"><button aria-label="Предыдущая неделя" onClick={() => setSelected(shiftDate(selected, -7))}>‹</button><button aria-label="Следующая неделя" onClick={() => setSelected(shiftDate(selected, 7))}>›</button></div><button className="view-select"><Icon name="calendar"/> Неделя <span>⌄</span></button></div></div>

          <div className="week-grid">
            <div className="time-column"><div className="day-heading spacer-heading"/><div className="all-day-label">ВЕСЬ ДЕНЬ</div>{Array.from({ length: endHour - startHour }, (_, index) => <div className="time-label" key={index}>{String(startHour + index).padStart(2, "0")}:00</div>)}</div>
            {days.map((day, dayIndex) => {
              const dayKey = localDate(day);
              const dayEvents = events.filter(item => localDate(new Date(item.starts_at)) === dayKey);
              return <div className={`day-column ${dayKey === today ? "is-today" : ""} ${dayKey === selectedKey ? "is-selected" : ""}`} key={dayKey}>
                <button className="day-heading" onClick={() => setSelected(day)}><span>{shortWeekdays[dayIndex]}</span><strong>{day.getDate()}</strong></button>
                <button className="all-day-cell" onClick={() => openCreate(day)} aria-label={`Добавить событие на ${weekdays[dayIndex]}`}/>
                <div className="day-canvas">
                  {Array.from({ length: endHour - startHour }, (_, index) => <div className="hour-line" key={index} style={{ top: `${index * hourHeight}px` }} />)}
                  {dayEvents.map(item => {
                    const start = new Date(item.starts_at); const finish = new Date(item.ends_at);
                    const top = Math.max(0, (start.getHours() - startHour + start.getMinutes() / 60) * hourHeight);
                    const height = Math.max(35, (finish.getTime() - start.getTime()) / 3_600_000 * hourHeight);
                    return <button type="button" key={item.id} className={`event-card ${item.source === "official" ? "official-event" : "personal-event"} ${item.skipped ? "skipped-event" : ""}`} style={{ top: `${top}px`, height: `${Math.min(height, 250)}px` }} onClick={() => setSelected(day)} title={`${item.title}${item.location ? ` · ${item.location}` : ""}`}>
                      <span className="event-time">{prettyDate(start, { hour: "2-digit", minute: "2-digit" })} — {prettyDate(finish, { hour: "2-digit", minute: "2-digit" })}</span><strong>{item.title}</strong>{(item.location || item.subject) && <span className="event-location">{item.location || item.subject}</span>}{item.source === "personal" && <span className="event-delete" onClick={event => { event.stopPropagation(); void removeEvent(item); }} role="button" tabIndex={0} aria-label="Удалить событие">×</span>}
                    </button>;
                  })}
                </div>
              </div>;
            })}
          </div>
          {calendarQuery.isPending && <div className="calendar-overlay"><span className="spinner"/>Загружаем расписание</div>}
          {!calendarQuery.isPending && !calendarQuery.isError && events.length === 0 && <div className="empty-note"><span className="empty-icon"><Icon name="calendar"/></span><div><strong>Неделя пока свободна</strong><span>Добавь личное событие или подключи учебную группу в профиле.</span></div><button onClick={() => openCreate()}>Добавить событие</button></div>}
          {apiError && !needsAuth && <div className="inline-error" role="alert">{apiError.message}<button onClick={() => void calendarQuery.refetch()}>Повторить</button></div>}
          {!!calendarQuery.data?.warnings.length && <p className="schedule-warning">Учебное расписание может быть неактуальным. Проверь источник перед важными планами.</p>}
        </section>

        <div className="below-grid"><section className="selected-day-card"><div className="section-title"><div><span className="greeting">ВЫБРАННЫЙ ДЕНЬ</span><h2>{prettyDate(selected, { weekday: "long", day: "numeric", month: "long" })}</h2></div><button className="text-action" onClick={() => openCreate()}>+ Событие</button></div>{selectedEvents.length ? <div className="agenda-list">{selectedEvents.map(item => <div className="agenda-row" key={item.id}><span className={`agenda-dot ${item.source === "official" ? "dot-official" : "dot-personal"}`}/><span className="agenda-time">{prettyDate(new Date(item.starts_at), { hour: "2-digit", minute: "2-digit" })}</span><span className="agenda-name">{item.title}</span><span className="agenda-place">{item.location ?? item.subject ?? ""}</span></div>)}</div> : <p className="agenda-empty">Здесь появятся события на выбранный день.</p>}</section>
          <section className="schedule-source-card"><div className="source-icon"><Icon name="cap"/></div><div className="source-copy"><span className="greeting">УЧЕБНОЕ РАСПИСАНИЕ</span><strong>{meQuery.data ? `Группа ${meQuery.data.group.name}` : "Добавь свою группу"}</strong><p>{meQuery.data ? `Подгруппа: ${meQuery.data.subgroup ?? "все"}. Официальные занятия отображаются вместе с личными планами.` : "Выбери группу, чтобы видеть пары в личном календаре."}</p></div><button aria-label="Настроить учебную группу" className="source-chevron" onClick={() => setShowGroupPicker(true)}><Icon name="chevron"/></button></section></div>
        {toast && <div className="toast" role="status">{toast}</div>}
      </div>
    </section>

    {showEventForm && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setShowEventForm(false); }}><form className="event-modal" onSubmit={createEvent}><button type="button" className="modal-close" onClick={() => setShowEventForm(false)} aria-label="Закрыть">×</button><span className="greeting">ЛИЧНЫЙ КАЛЕНДАРЬ</span><h2>Новое событие</h2><p>Добавь план в своё расписание.</p><label htmlFor="event-title">Название</label><input id="event-title" autoFocus required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder="Например, подготовка к экзамену"/><div className="form-row"><div><label htmlFor="event-start">Начало</label><input id="event-start" type="datetime-local" required value={startValue} onChange={event => setStartValue(event.target.value)}/></div><div><label htmlFor="event-end">Окончание</label><input id="event-end" type="datetime-local" required value={endValue} onChange={event => setEndValue(event.target.value)}/></div></div><label htmlFor="event-location">Место <span className="optional">необязательно</span></label><input id="event-location" value={location} onChange={event => setLocation(event.target.value)} maxLength={500} placeholder="Аудитория или место"/>{formError && <p className="form-error" role="alert">{formError}</p>}<div className="modal-actions"><button type="button" className="cancel-button" onClick={() => setShowEventForm(false)}>Отмена</button><button className="primary-button" disabled={saving}>{saving ? "Сохраняем…" : "Добавить событие"}</button></div></form></div>}
  </main>;
}

function toDateTimeLocal(date: Date) {
  const offsetDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return offsetDate.toISOString().slice(0, 16);
}
