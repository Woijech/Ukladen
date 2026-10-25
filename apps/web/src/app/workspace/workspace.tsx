"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import Image from "next/image";
import dynamic from "next/dynamic";
import { ThemeToggle } from "@/shared/theme";
import { Modal } from "@/shared/ui";
import { EventExtras } from "./panels/event-extras";
import { Navigation, NavIcon, sections, type SectionKey } from "./navigation";
import {
  RequestError,
  SessionExpiredError,
  requestJson,
  csrfToken,
} from "@/shared/api";
import { Brand } from "@/shared/brand";
import { GoogleAuth } from "@/shared/google-auth";
import { GoogleLinkDialog } from "@/shared/google-link-dialog";
import logo from "@/shared/assets/ukladen-logo.png";
import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  dateKey,
  dateTimeLocal,
  dayStart,
  localInstants,
  prettyDate as formatDate,
  resolveLocalTime,
  shiftDate,
  startOfWeek,
} from "./calendar-time";
import "./workspace.css";

const WorkspaceViews = dynamic(
  () => import("./views").then((module) => module.WorkspaceViews),
  {
    loading: () => (
      <div
        className="skeleton-stack"
        role="status"
        aria-label="Загрузка раздела"
      >
        <span />
        <span />
      </div>
    ),
  },
);

type CalendarEvent = {
  id: string;
  source: "official" | "personal";
  source_event_id: string;
  kind: "lesson" | "exam" | "announcement" | "personal";
  title: string;
  description: string | null;
  version: number;
  starts_at: string;
  ends_at: string;
  location: string | null;
  blocks_time: boolean;
  skipped: boolean;
  lesson_type: string | null;
  subject: string | null;
  subject_full_name: string | null;
  rooms: string[];
  teacher_names: string[];
};

type ScheduleSyncStatus = {
  group_id: number;
  group_number: string;
  status:
    | "not_synced"
    | "syncing"
    | "ready"
    | "unpublished"
    | "error"
    | "unsupported";
  last_attempt_at: string | null;
  last_success_at: string | null;
  error_code: string | null;
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

const weekdays = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
  "Воскресенье",
];
const shortWeekdays = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"];
const hourHeight = 54;

function daySegments(events: CalendarEvent[], dayStart: Date, dayEnd: Date) {
  const start = dayStart.getTime();
  const end = dayEnd.getTime();
  return events
    .filter(
      (event) =>
        Date.parse(event.starts_at) < end && Date.parse(event.ends_at) > start,
    )
    .map((event) => ({
      ...event,
      originalEvent: event,
      starts_at: new Date(
        Math.max(start, Date.parse(event.starts_at)),
      ).toISOString(),
      ends_at: new Date(Math.min(end, Date.parse(event.ends_at))).toISOString(),
    }));
}

function eventColumns(events: CalendarEvent[]) {
  const sorted = [...events].sort((a, b) =>
    a.starts_at.localeCompare(b.starts_at),
  );
  const columns = new Map<string, { lane: number; count: number }>();
  let cluster: CalendarEvent[] = [];
  let clusterEnd = 0;
  const placeCluster = () => {
    const laneEnds: number[] = [];
    const placements: Array<{ event: CalendarEvent; lane: number }> = [];
    for (const event of cluster) {
      const start = new Date(event.starts_at).getTime();
      const end = new Date(event.ends_at).getTime();
      let lane = laneEnds.findIndex((value) => value <= start);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = end;
      placements.push({ event, lane });
    }
    for (const placement of placements)
      columns.set(placement.event.id, {
        lane: placement.lane,
        count: laneEnds.length,
      });
    cluster = [];
    clusterEnd = 0;
  };
  for (const event of sorted) {
    const start = new Date(event.starts_at).getTime();
    const end = new Date(event.ends_at).getTime();
    if (cluster.length && start >= clusterEnd) placeCluster();
    cluster.push(event);
    clusterEnd = Math.max(clusterEnd, end);
  }
  if (cluster.length) placeCluster();
  return columns;
}

type SyncRequest = {
  baseline: ScheduleSyncStatus;
  startedAt: number;
  message: string;
};

function isSyncComplete(
  status: ScheduleSyncStatus | undefined,
  request: SyncRequest | null = null,
) {
  if (!status) return false;
  const attemptTime = status.last_attempt_at
    ? Date.parse(status.last_attempt_at)
    : 0;
  if (request) {
    if (status.group_id !== request.baseline.group_id) return false;
    const previousAttempt = request.baseline.last_attempt_at
      ? Date.parse(request.baseline.last_attempt_at)
      : 0;
    const previousSuccess = request.baseline.last_success_at
      ? Date.parse(request.baseline.last_success_at)
      : 0;
    const successTime = status.last_success_at
      ? Date.parse(status.last_success_at)
      : 0;
    if (
      !(
        attemptTime > previousAttempt ||
        successTime > previousSuccess ||
        (request.baseline.status === "syncing" &&
          attemptTime === previousAttempt)
      )
    )
      return false;
  }
  return status.status === "ready"
    ? Boolean(
        status.last_success_at &&
          Date.parse(status.last_success_at) >= attemptTime,
      )
    : ["unpublished", "error", "unsupported"].includes(status.status);
}

function scheduleStatusMessage(status: ScheduleSyncStatus) {
  if (status.status === "unpublished")
    return "Для этой группы IIS не публикует расписание.";
  if (status.status === "error")
    return "IIS не ответил или вернул неожиданный ответ. Проверьте подключение и повторите синхронизацию.";
  const unsupported: Record<string, string> = {
    unsupported_split_precedence:
      "Сохранён отказ предыдущего импорта split-занятий. Повторите синхронизацию, чтобы заново загрузить расписание.",
    unsupported_undated_exception:
      "В ответе IIS есть исключение без даты; его нельзя безопасно поставить в календарь.",
    unsupported_invalid_period:
      "IIS вернул некорректные границы периода расписания.",
    unsupported_missing_week_numbers:
      "У повторяющегося занятия IIS не указал номера учебных недель.",
    unsupported_nonlocal_source_time:
      "IIS вернул время занятия с неподдерживаемым часовым поясом.",
    unsupported_invalid_time:
      "В ответе IIS время окончания занятия не позже времени начала.",
    unsupported_unknown_weekday: "IIS вернул неизвестный день недели.",
    unsupported_invalid_date: "IIS вернул некорректную дату занятия.",
    unsupported_too_many_events:
      "Импорт IIS превысил безопасный предел количества занятий.",
    unsupported_invalid_academic_year:
      "В расписании IIS есть дата до начала поддерживаемого учебного года.",
    unsupported_missing_group:
      "В ответе IIS отсутствует идентификатор учебной группы.",
    unsupported_invalid_event:
      "В расписании IIS есть занятие с некорректным временем или подгруппой.",
  };
  return (
    unsupported[status.error_code ?? ""] ??
    "IIS вернул запись расписания, которую текущий импортёр не может безопасно преобразовать в занятие."
  );
}

function Icon({
  name,
}: {
  name:
    | "calendar"
    | "plus"
    | "chevron"
    | "logout"
    | "sparkle"
    | "clock"
    | "menu"
    | "eye"
    | "eye-off"
    | "cap"
    | "close";
}) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true as const,
  };
  if (name === "calendar")
    return (
      <svg {...common}>
        <rect x="3.5" y="5" width="17" height="16" rx="3" />
        <path d="M8 3v4M16 3v4M3.5 10h17" />
        <path d="M8 14h.01M12 14h.01M16 14h.01M8 17h.01M12 17h.01" />
      </svg>
    );
  if (name === "plus")
    return (
      <svg {...common}>
        <path d="M12 5v14M5 12h14" />
      </svg>
    );
  if (name === "chevron")
    return (
      <svg {...common}>
        <path d="m9 18 6-6-6-6" />
      </svg>
    );
  if (name === "logout")
    return (
      <svg {...common}>
        <path d="M10 17l5-5-5-5M15 12H3" />
        <path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6" />
      </svg>
    );
  if (name === "clock")
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </svg>
    );
  if (name === "menu")
    return (
      <svg {...common}>
        <path d="M4 7h16M4 12h16M4 17h16" />
      </svg>
    );
  if (name === "eye")
    return (
      <svg {...common}>
        <path d="M2.5 12s3.4-6 9.5-6 9.5 6 9.5 6-3.4 6-9.5 6-9.5-6-9.5-6Z" />
        <circle cx="12" cy="12" r="2.6" />
      </svg>
    );
  if (name === "eye-off")
    return (
      <svg {...common}>
        <path d="m3 3 18 18M10.6 6.2A10.8 10.8 0 0 1 12 6c6.1 0 9.5 6 9.5 6a16 16 0 0 1-3 3.5M6.2 6.3C3.8 7.8 2.5 12 2.5 12s3.4 6 9.5 6c1.1 0 2.1-.2 3-.5" />
        <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      </svg>
    );
  if (name === "cap")
    return (
      <svg {...common}>
        <path d="m2 9 10-5 10 5-10 5L2 9Z" />
        <path d="M6 11v5c3.5 2.7 8.5 2.7 12 0v-5M22 9v6" />
      </svg>
    );
  if (name === "close")
    return (
      <svg {...common}>
        <path d="m6 6 12 12M18 6 6 18" />
      </svg>
    );
  return (
    <svg {...common}>
      <path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z" />
      <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
    </svg>
  );
}

function PasswordField({
  id,
  value,
  onChange,
  autoComplete,
  minLength,
  placeholder,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  minLength: number;
  placeholder: string;
}) {
  const [visible, setVisible] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  function revealPassword() {
    if (timer.current) clearTimeout(timer.current);
    setVisible(true);
    timer.current = setTimeout(() => setVisible(false), 3000);
  }

  return (
    <div className="password-control">
      <input
        id={id}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        minLength={minLength}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      <button
        className="password-toggle"
        type="button"
        onClick={revealPassword}
        aria-label={
          visible
            ? "Пароль виден, скроется через 3 секунды"
            : "Показать пароль на 3 секунды"
        }
        title={
          visible ? "Скроется через 3 секунды" : "Показать пароль на 3 секунды"
        }
      >
        <Icon name={visible ? "eye-off" : "eye"} />
      </button>
    </div>
  );
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
      await requestJson(
        mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": token,
          },
          body: JSON.stringify({ email, password }),
        },
      );
      if (mode === "register") {
        setPassword("");
        window.location.replace("/auth/complete-registration");
        return;
      }
      await onSuccess();
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message.includes("Войдите")
            ? "Не удалось войти. Проверьте почту и пароль."
            : error.message
          : "Не удалось войти.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <div className="auth-art" aria-hidden="true">
        <div className="art-orbit orbit-one" />
        <div className="art-orbit orbit-two" />
        <Image
          className="auth-art-logo"
          src={logo}
          alt=""
          width={340}
          height={340}
          sizes="(max-width: 760px) 1px, 340px"
        />
        <span className="art-caption">
          Твоё спокойное место
          <br />
          для важных планов
        </span>
      </div>
      <form className="auth-card" onSubmit={submit}>
        <Brand />
        <h1>{mode === "login" ? "Войти в Ukladen" : "Создать аккаунт"}</h1>
        <p className="auth-description">
          Расписание и личные планы — в одном пространстве.
        </p>
        <label htmlFor="email">Электронная почта</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="name@example.com"
        />
        <label htmlFor="password">Пароль</label>
        <PasswordField
          id="password"
          value={password}
          onChange={setPassword}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={mode === "register" ? 12 : 1}
          placeholder={
            mode === "register" ? "Не менее 12 символов" : "Твой пароль"
          }
        />
        {mode === "login" && (
          <a className="auth-recovery" href="/auth/reset-password">
            Забыли пароль?
          </a>
        )}
        {message && (
          <p className="form-error" role="alert">
            {message}
          </p>
        )}
        <button className="primary-button auth-submit" disabled={busy}>
          {busy
            ? "Секунду…"
            : mode === "login"
              ? "Войти"
              : "Зарегистрироваться"}
        </button>
        <GoogleAuth />
        <p className="auth-switch">
          {mode === "login" ? "Впервые здесь?" : "Уже есть аккаунт?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setMessage("");
            }}
          >
            {mode === "login" ? "Создать аккаунт" : "Войти"}
          </button>
        </p>
      </form>
    </div>
  );
}

function GroupPicker({
  profile,
  timeZone,
  onClose,
  onSaved,
}: {
  profile: AcademicProfile | null;
  timeZone: string;
  onClose: () => void;
  onSaved: (
    syncAccepted: boolean,
    baseline: ScheduleSyncStatus,
    startedAt: number,
  ) => void;
}) {
  const [search, setSearch] = useState("");
  const [groupId, setGroupId] = useState<number | null>(
    profile?.group.id ?? null,
  );
  const [subgroup, setSubgroup] = useState(
    profile?.subgroup ? String(profile.subgroup) : "",
  );
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const groupsQuery = useQuery({
    queryKey: ["university-groups"],
    queryFn: () => requestJson<UniversityGroup[]>("/api/v1/academics/groups"),
    retry: false,
  });
  const contextQuery = useQuery({
    queryKey: ["university-group-context", groupId],
    queryFn: () =>
      requestJson<GroupContext>(`/api/v1/academics/groups/${groupId}/context`),
    enabled: groupId !== null,
    retry: false,
  });
  const groups = groupsQuery.data ?? [];
  const visibleGroups = groups
    .filter((group) => {
      const needle = search.trim().toLocaleLowerCase("ru-RU");
      return (
        !needle ||
        `${group.name} ${group.faculty_name} ${group.faculty_abbrev} ${group.speciality_name}`
          .toLocaleLowerCase("ru-RU")
          .includes(needle)
      );
    })
    .slice(0, 100);
  const selectedGroup =
    groups.find((group) => group.id === groupId) ?? profile?.group ?? null;

  async function saveSelection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (groupId === null || !selectedGroup) return;
    setSaving(true);
    setError("");
    try {
      const day = dateKey(new Date(), timeZone);
      let baseline: ScheduleSyncStatus = {
        group_id: selectedGroup.id,
        group_number: selectedGroup.name,
        status: "not_synced",
        last_attempt_at: null,
        last_success_at: null,
        error_code: null,
      };
      try {
        baseline = (
          await requestJson<{ source: ScheduleSyncStatus }>(
            `/api/v1/schedule/groups/${selectedGroup.name}/events?date_from=${day}&date_to=${day}`,
          )
        ).source;
      } catch (error) {
        // The stored group-events API returns 404 until the first import creates its source.
        if (!(error instanceof RequestError && error.status === 404))
          throw error;
      }
      const startedAt = Date.now();
      const token = await csrfToken();
      await requestJson<AcademicProfile>("/api/v1/academics/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify({
          group_id: groupId,
          subgroup: subgroup ? Number(subgroup) : null,
        }),
      });
      let syncAccepted = false;
      try {
        await requestJson<{ group_id: number }>("/api/v1/schedule/me/sync", {
          method: "POST",
          headers: { "X-CSRF-Token": token },
        });
        syncAccepted = true;
      } catch {
        syncAccepted = false;
      }
      onSaved(syncAccepted, baseline, startedAt);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Не удалось сохранить группу.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="group-page">
      <header className="group-header">
        <a className="brand-lockup" href="/workspace">
          <Brand />
        </a>
        <button className="cancel-button" type="button" onClick={onClose}>
          Вернуться в календарь
        </button>
      </header>
      <div className="group-content">
        <div className="group-intro">
          <span className="group-icon">
            <Icon name="cap" />
          </span>
          <span className="greeting">НАСТРОЙКА РАСПИСАНИЯ</span>
          <h1>
            {profile ? "Изменить учебную группу" : "Добавь расписание учёбы"}
          </h1>
          <p>
            Найди свою группу БГУИР — занятия появятся рядом с личными планами.
          </p>
        </div>
        <div className="group-picker-layout">
          <section className="group-list-panel">
            <label htmlFor="group-search">Группа или факультет</label>
            <div className="group-search-wrap">
              <span>⌕</span>
              <input
                id="group-search"
                autoFocus
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Например, 353501 или ФКСиС"
              />
            </div>
            {groupsQuery.isPending && (
              <div className="group-loading">Загружаем список групп…</div>
            )}
            {groupsQuery.isError && (
              <div className="group-error" role="alert">
                {groupsQuery.error instanceof Error
                  ? groupsQuery.error.message
                  : "Не удалось загрузить список групп."}
                <button onClick={() => void groupsQuery.refetch()}>
                  Повторить
                </button>
              </div>
            )}
            {!groupsQuery.isPending &&
              !groupsQuery.isError &&
              visibleGroups.length === 0 && (
                <div className="group-loading">
                  Группы не найдены. Попробуй другой запрос.
                </div>
              )}
            <div
              className="group-options"
              role="listbox"
              aria-label="Список учебных групп"
            >
              {visibleGroups.map((group) => (
                <button
                  type="button"
                  role="option"
                  aria-selected={group.id === groupId}
                  className={`group-option ${group.id === groupId ? "chosen" : ""}`}
                  key={group.id}
                  onClick={() => {
                    setGroupId(group.id);
                    setSubgroup("");
                  }}
                >
                  <span className="group-option-name">{group.name}</span>
                  <span className="group-option-details">
                    {group.faculty_abbrev} · {group.speciality_name}
                    {group.course ? ` · ${group.course} курс` : ""}
                  </span>
                  <span className="group-option-check">
                    {group.id === groupId ? "✓" : ""}
                  </span>
                </button>
              ))}
            </div>
            {groups.length > 100 && (
              <p className="group-limit-note">
                Показаны первые 100 результатов. Уточни поиск, чтобы найти свою
                группу.
              </p>
            )}
          </section>
          <form className="group-details-panel" onSubmit={saveSelection}>
            {selectedGroup ? (
              <>
                <span className="greeting">ВЫБРАННАЯ ГРУППА</span>
                <h2>{selectedGroup.name}</h2>
                <p className="group-faculty">{selectedGroup.faculty_name}</p>
                {contextQuery.isPending && (
                  <p className="group-context-note">
                    Проверяем доступное расписание и подгруппы…
                  </p>
                )}
                {contextQuery.isError && (
                  <p className="group-context-note">
                    Не удалось получить список подгрупп. Можно сохранить группу
                    без фильтра.
                  </p>
                )}
                {contextQuery.data && !contextQuery.data.schedule_available && (
                  <p className="group-context-note">
                    Для этой группы пока нет опубликованного расписания. Группу
                    можно сохранить.
                  </p>
                )}
                {contextQuery.data?.schedule_available && (
                  <>
                    <label htmlFor="subgroup">Подгруппа</label>
                    <select
                      id="subgroup"
                      value={subgroup}
                      onChange={(event) => setSubgroup(event.target.value)}
                    >
                      <option value="">Все подгруппы</option>
                      {contextQuery.data.subgroups.map((item) => (
                        <option key={item} value={item}>
                          Подгруппа {item}
                        </option>
                      ))}
                    </select>
                    {contextQuery.data.period?.term_label && (
                      <p className="period-note">
                        {contextQuery.data.period.term_label}
                        {contextQuery.data.period.period_label
                          ? ` · ${contextQuery.data.period.period_label}`
                          : ""}
                      </p>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="group-empty">
                <Icon name="cap" />
                <strong>Выбери группу слева</strong>
                <span>
                  Покажем найденные для неё подгруппы и учебный период.
                </span>
              </div>
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <div className="group-actions">
              <button type="button" className="text-action" onClick={onClose}>
                Пока без группы
              </button>
              <button
                className="primary-button"
                disabled={!selectedGroup || saving}
              >
                {saving
                  ? "Сохраняем…"
                  : profile
                    ? "Сохранить группу"
                    : "Продолжить"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}

type SessionUser = {
  id: string;
  timezone: string;
  display_name?: string | null;
  email?: string;
  avatar_url?: string | null;
  updated_at?: string;
};

export function Workspace({ initialSection = "calendar" }: { initialSection?: SectionKey }) {
  const [onboarding, setOnboarding] = useState(false);
  const session = useQuery({
    queryKey: ["workspace-session"],
    queryFn: async ({ signal }) => {
      try {
        return await requestJson<SessionUser>("/api/v1/users/me", { signal });
      } catch (error) {
        if (error instanceof SessionExpiredError) return null;
        throw error;
      }
    },
    staleTime: 0,
    gcTime: 0,
  });
  const client = useQueryClient();
  const refreshSession = session.refetch;
  useEffect(() => {
    const refresh = () => {
      void refreshSession();
    };
    window.addEventListener("ukladen:profile-updated", refresh);
    return () => window.removeEventListener("ukladen:profile-updated", refresh);
  }, [refreshSession]);
  function endSession() {
    setOnboarding(false);
    client.setQueryData(["workspace-session"], null);
  }
  if (session.isPending)
    return (
      <main className="workspace-auth" role="status">
        Проверяем сессию…
      </main>
    );
  if (session.isError)
    return (
      <main className="workspace-auth">
        <p role="alert">Не удалось проверить сессию.</p>
        <button onClick={() => void session.refetch()}>Повторить</button>
      </main>
    );
  if (!session.data)
    return (
      <main className="workspace-auth">
        <div className="theme-corner">
          <ThemeToggle />
        </div>
        <AuthPanel
          onSuccess={async () => {
            const profile = await requestJson<AcademicProfile | null>(
              "/api/v1/academics/me",
            );
            setOnboarding(!profile);
            await session.refetch({ throwOnError: true });
          }}
        />
      </main>
    );
  return (
    <SessionWorkspace
      initialSection={initialSection}
      key={`${session.data.id}:${session.data.timezone}`}
      userTimeZone={session.data.timezone}
      user={session.data}
      checkingSession={session.isFetching}
      onSessionEnd={endSession}
      onboarding={onboarding}
    />
  );
}

function SessionWorkspace({
  initialSection,
  userTimeZone,
  user,
  checkingSession,
  onSessionEnd,
  onboarding,
}: {
  initialSection: SectionKey;
  userTimeZone: string;
  user: SessionUser;
  checkingSession: boolean;
  onSessionEnd: () => void;
  onboarding: boolean;
}) {
  // A session owns both its cache and mounted forms; neither survives an account switch.
  const [client] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({
          onError: (error) => {
            if (error instanceof SessionExpiredError) onSessionEnd();
          },
        }),
        defaultOptions: { queries: { staleTime: 30_000, retry: false } },
      }),
  );
  useEffect(
    () => () => {
      void client.cancelQueries();
      client.clear();
    },
    [client],
  );
  useEffect(() => {
    window.addEventListener("ukladen:session-expired", onSessionEnd);
    return () =>
      window.removeEventListener("ukladen:session-expired", onSessionEnd);
  }, [onSessionEnd]);
  return (
    <div hidden={checkingSession}>
      <QueryClientProvider client={client}>
        <CalendarWorkspace
          initialSection={initialSection}
          userTimeZone={userTimeZone}
          user={user}
          onSessionEnd={onSessionEnd}
          onboarding={onboarding}
        />
      </QueryClientProvider>
    </div>
  );
}

function CalendarWorkspace({
  initialSection,
  userTimeZone,
  user,
  onSessionEnd,
  onboarding,
}: {
  initialSection: SectionKey;
  userTimeZone: string;
  user: SessionUser;
  onSessionEnd: () => void;
  onboarding: boolean;
}) {
  const queryClient = useQueryClient();
  const [section, setSection] = useState<SectionKey>(initialSection);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileNavigation, setMobileNavigation] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pendingSection, setPendingSection] = useState<SectionKey | null>(null);
  const [pageToOpen, setPageToOpen] = useState<string | null>(null);
  function navigate(next: SectionKey) {
    if (next === section) {
      setMobileNavigation(false);
      return;
    }
    if (dirty) {
      setPendingSection(next);
      return;
    }
    setSection(next);
    setMobileNavigation(false);
  }
  function openPage(id: string) {
    setPageToOpen(id);
    navigate("notes");
  }
  const calendarScroll = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState(() =>
    dateKey(new Date(), userTimeZone),
  );
  const [viewMenuOpen, setViewMenuOpen] = useState(false);
  const [calendarView, setCalendarView] = useState<"week" | "day">("week");
  const [showEventForm, setShowEventForm] = useState(false);
  const [showGroupPicker, setShowGroupPicker] = useState(onboarding);
  const [showGoogleLink, setShowGoogleLink] = useState(false);
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const [topAccountMenuOpen, setTopAccountMenuOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [syncRequest, setSyncRequest] = useState<SyncRequest | null>(null);
  const [syncRequestError, setSyncRequestError] = useState("");
  const [syncCheckedAt, setSyncCheckedAt] = useState(0);
  const [deletingEvent, setDeletingEvent] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<CalendarEvent | null>(
    null,
  );
  const [showPersonal, setShowPersonal] = useState(true);
  const [showOfficial, setShowOfficial] = useState(true);
  const [officialEvent, setOfficialEvent] = useState<CalendarEvent | null>(
    null,
  );
  const [editingEvent, setEditingEvent] = useState<CalendarEvent | null>(null);

  const weekStart = useMemo(() => startOfWeek(selected), [selected]);
  const days = useMemo(
    () => Array.from({ length: 7 }, (_, index) => shiftDate(weekStart, index)),
    [weekStart],
  );
  const range = { from: days[0], to: days[6] };
  const calendarQuery = useQuery({
    queryKey: ["workspace-calendar", range.from, range.to],
    queryFn: ({ signal }) =>
      requestJson<CalendarPayload>(
        `/api/v1/calendar/events?date_from=${range.from}&date_to=${range.to}`,
        { signal },
      ),
    retry: false,
  });
  const meQuery = useQuery({
    queryKey: ["workspace-profile"],
    queryFn: ({ signal }) =>
      requestJson<AcademicProfile | null>("/api/v1/academics/me", { signal }),
    retry: false,
  });
  const syncStatusQuery = useQuery({
    queryKey: ["schedule-sync-status", meQuery.data?.group.id],
    queryFn: ({ signal }) =>
      requestJson<ScheduleSyncStatus>("/api/v1/schedule/me/sync-status", {
        signal,
      }),
    enabled: Boolean(meQuery.data?.group.id),
    refetchInterval: (query) =>
      (syncRequest && !isSyncComplete(query.state.data, syncRequest)) ||
      query.state.data?.status === "syncing"
        ? 3000
        : false,
    retry: false,
  });
  const apiError =
    calendarQuery.error instanceof Error ? calendarQuery.error : null;
  const needsAuth = apiError?.message.includes("Войдите") ?? false;
  const allEvents = calendarQuery.data?.events ?? [];
  const events = allEvents.filter((event) =>
    event.source === "personal" ? showPersonal : showOfficial,
  );
  const timeZone = calendarQuery.data?.timezone ?? userTimeZone;
  const prettyDate = (
    date: Date | string,
    options: Intl.DateTimeFormatOptions = {},
  ) => formatDate(date, timeZone, options);
  const boundaries = useMemo(
    () =>
      [...days, shiftDate(days[6], 1)].map((day) => dayStart(day, timeZone)),
    [days, timeZone],
  );
  const dayHours = days.map(
    (_, index) =>
      (boundaries[index + 1].getTime() - boundaries[index].getTime()) /
      3_600_000,
  );
  const gridHours = Math.ceil(Math.max(24, ...dayHours));
  const clockChangeWeek = dayHours.some((hours) => hours !== 24);
  const today = dateKey(new Date(), timeZone);
  const selectedKey = selected;
  const dateLabel = prettyDate(weekStart, { day: "numeric", month: "long" });
  const weekEndLabel = prettyDate(days[6], {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  const selectedEvents = daySegments(
    events,
    boundaries[days.indexOf(selected)],
    boundaries[days.indexOf(selected) + 1],
  ).sort((a, b) => a.starts_at.localeCompare(b.starts_at));

  useEffect(() => {
    if (calendarScroll.current)
      calendarScroll.current.scrollTop = 8 * hourHeight;
  }, [range.from, showGroupPicker, section]);

  const syncStatus =
    syncStatusQuery.data?.group_id === meQuery.data?.group.id
      ? syncStatusQuery.data
      : undefined;
  const attemptTime = syncStatus?.last_attempt_at
    ? Date.parse(syncStatus.last_attempt_at)
    : 0;
  const syncCompleted = isSyncComplete(syncStatus, syncRequest);
  const syncStartedAt =
    syncRequest?.startedAt ??
    (syncStatus?.status === "syncing" ? attemptTime : 0);
  const syncTimedOut =
    !syncCompleted &&
    syncStartedAt > 0 &&
    syncCheckedAt >= syncStartedAt + 180_000;
  const syncPending =
    !syncCompleted &&
    !syncTimedOut &&
    Boolean(syncRequest || syncStatus?.status === "syncing");
  const syncFinished = Boolean(
    syncRequest &&
      syncCompleted &&
      syncStatus?.status === "ready" &&
      !calendarQuery.isError,
  );
  const syncWaiting = syncTimedOut || syncStatus?.status === "unpublished";
  const syncNotice =
    syncRequestError ||
    (syncStatusQuery.isError && (syncRequest || syncPending)
      ? "Не удалось проверить статус IIS. Продолжаем проверять; можно повторить запрос позже."
      : syncPending
        ? (syncRequest?.message ?? "IIS синхронизирует расписание…")
        : syncTimedOut
          ? "Импорт ещё выполняется. Продолжаем проверять статус; расписание появится после завершения синхронизации."
          : syncFinished
            ? "Расписание синхронизировано."
            : syncRequest &&
                syncCompleted &&
                syncStatus?.status === "ready" &&
                calendarQuery.isError
              ? "IIS завершил импорт, но календарь пока не удалось обновить. Повторите загрузку календаря."
              : syncStatus &&
                  ["unsupported", "error", "unpublished"].includes(
                    syncStatus.status,
                  )
                ? scheduleStatusMessage(syncStatus)
                : "");

  useEffect(() => {
    if (!syncStartedAt || syncCompleted) return;
    const timer = setTimeout(
      () => setSyncCheckedAt(Date.now()),
      Math.max(0, syncStartedAt + 180_000 - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [syncStartedAt, syncCompleted]);

  useEffect(() => {
    if (syncStatus?.status === "ready")
      void queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] });
  }, [
    syncStatus?.group_id,
    syncStatus?.status,
    syncStatus?.last_success_at,
    queryClient,
  ]);

  function openCreate(date = selected) {
    setEditingEvent(null);
    setSelected(date);
    setStartValue(`${date}T10:00`);
    setEndValue(`${date}T11:00`);
    setStartInstant("");
    setEndInstant("");
    setTitle("");
    setLocation("");
    setDescription("");
    setFormError("");
    setShowEventForm(true);
  }

  const [startValue, setStartValue] = useState("");
  const [endValue, setEndValue] = useState("");
  const [startInstant, setStartInstant] = useState("");
  const [endInstant, setEndInstant] = useState("");
  const startOptions = useMemo(
    () => localInstants(startValue, timeZone, editingEvent?.starts_at),
    [startValue, timeZone, editingEvent?.starts_at],
  );
  const endOptions = useMemo(
    () => localInstants(endValue, timeZone, editingEvent?.ends_at),
    [endValue, timeZone, editingEvent?.ends_at],
  );

  async function retryScheduleSync() {
    setSyncRequestError("");
    try {
      const baseline = await requestJson<ScheduleSyncStatus>(
        "/api/v1/schedule/me/sync-status",
      );
      const startedAt = Date.now();
      const token = await csrfToken();
      await requestJson<{ group_id: number }>("/api/v1/schedule/me/sync", {
        method: "POST",
        headers: { "X-CSRF-Token": token },
      });
      setSyncRequest({
        baseline,
        startedAt,
        message: "Запрос принят. Проверяем результат синхронизации IIS…",
      });
      await queryClient.invalidateQueries({
        queryKey: ["schedule-sync-status"],
      });
    } catch (error) {
      setSyncRequest(null);
      setSyncRequestError(
        error instanceof Error
          ? error.message
          : "Не удалось запустить синхронизацию IIS.",
      );
    }
  }

  async function afterGroupSaved(
    syncAccepted: boolean,
    baseline: ScheduleSyncStatus,
    startedAt: number,
  ) {
    setShowGroupPicker(false);
    setAccountMenuOpen(false);
    setTopAccountMenuOpen(false);
    setSyncRequestError("");
    setSyncRequest({
      baseline,
      startedAt,
      message: syncAccepted
        ? "Группа выбрана. IIS загружает расписание…"
        : "Группа сохранена. Ждём фоновую синхронизацию расписания…",
    });
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] }),
      queryClient.invalidateQueries({ queryKey: ["workspace-profile"] }),
      queryClient.invalidateQueries({ queryKey: ["schedule-sync-status"] }),
    ]);
  }

  function openEvent(item: CalendarEvent) {
    if (item.source === "official") {
      setOfficialEvent(item);
      return;
    }
    setEditingEvent(item);
    setTitle(item.title);
    setLocation(item.location ?? "");
    setDescription(item.description ?? "");
    setStartValue(dateTimeLocal(new Date(item.starts_at), timeZone));
    setStartInstant(new Date(item.starts_at).toISOString());
    setEndValue(dateTimeLocal(new Date(item.ends_at), timeZone));
    setEndInstant(new Date(item.ends_at).toISOString());
    setFormError("");
    setShowEventForm(true);
  }

  async function createEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const startsAt = resolveLocalTime(
        startValue,
        timeZone,
        startInstant,
        editingEvent?.starts_at,
      );
      const endsAt = resolveLocalTime(
        endValue,
        timeZone,
        endInstant,
        editingEvent?.ends_at,
      );
      if (Date.parse(endsAt) <= Date.parse(startsAt))
        throw new Error("Окончание должно быть позже начала.");
      const token = await csrfToken();
      if (editingEvent) {
        await requestJson<PersonalEvent>(
          `/api/v1/calendar/personal-events/${editingEvent.source_event_id}`,
          {
            method: "PATCH",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": token,
            },
            body: JSON.stringify({
              expected_version: editingEvent.version,
              title,
              location: location || null,
              description: description || null,
              starts_at: startsAt,
              ends_at: endsAt,
            }),
          },
        );
      } else {
        await requestJson<PersonalEvent>("/api/v1/calendar/personal-events", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": token,
          },
          body: JSON.stringify({
            title,
            location: location || null,
            description: description || null,
            starts_at: startsAt,
            ends_at: endsAt,
            blocks_time: true,
          }),
        });
      }
      setShowEventForm(false);
      setEditingEvent(null);
      setToast(editingEvent ? "Событие обновлено" : "Событие добавлено");
      await queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] });
      window.setTimeout(() => setToast(""), 2600);
    } catch (error) {
      setFormError(
        error instanceof Error
          ? error.message
          : "Не удалось сохранить событие.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function removeEvent(event: CalendarEvent) {
    if (event.source !== "personal" || deletingEvent) return;
    setDeletingEvent(true);
    setDeleteError("");
    try {
      const token = await csrfToken();
      await requestJson<void>(
        `/api/v1/calendar/personal-events/${event.source_event_id}`,
        { method: "DELETE", headers: { "X-CSRF-Token": token } },
      );
      setShowEventForm(false);
      setEditingEvent(null);
      setPendingDelete(null);
      setToast("Событие удалено");
      await queryClient.invalidateQueries({ queryKey: ["workspace-calendar"] });
      window.setTimeout(() => setToast(""), 2600);
    } catch (error) {
      setDeleteError(
        error instanceof Error ? error.message : "Не удалось удалить событие.",
      );
    } finally {
      setDeletingEvent(false);
    }
  }

  async function logout() {
    try {
      setAccountMenuOpen(false);
      setTopAccountMenuOpen(false);
      const token = await csrfToken();
      await requestJson<void>("/api/v1/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": token },
      });
      onSessionEnd();
    } catch (error) {
      setToast(
        error instanceof Error ? error.message : "Не удалось завершить сессию.",
      );
    }
  }

  if (showGroupPicker)
    return (
      <GroupPicker
        profile={meQuery.data ?? null}
        timeZone={timeZone}
        onClose={() => setShowGroupPicker(false)}
        onSaved={(accepted, baseline, startedAt) =>
          void afterGroupSaved(accepted, baseline, startedAt)
        }
      />
    );

  return (
    <main
      className={`workspace-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
    >
      <aside className="sidebar">
        <a
          className="brand-lockup"
          href="/workspace"
          aria-label="Ukladen — главная"
        >
          <Brand />
        </a>
        <button
          className="sidebar-collapse icon-button"
          aria-label={
            sidebarCollapsed
              ? "Развернуть боковую панель"
              : "Свернуть боковую панель"
          }
          onClick={() => setSidebarCollapsed((value) => !value)}
        >
          <Icon name="menu" />
        </button>
        <Navigation active={section} onNavigate={navigate} />
        <div className="sidebar-spacer" />
        <button
          className="nav-item settings-nav"
          aria-label="Настройки"
          onClick={() => navigate("settings")}
        >
          <Icon name="menu" />
          <span>Настройки</span>
        </button>
        <div className="account-area">
          <button
            className="account-button"
            aria-label="Профиль в боковой панели"
            aria-expanded={accountMenuOpen}
            onClick={() => setAccountMenuOpen((open) => !open)}
          >
            <span className="avatar">
              {user.display_name?.[0]?.toUpperCase() ||
                user.email?.[0]?.toUpperCase() ||
                "U"}
            </span>
            <span className="account-copy">
              <strong>
                {user.display_name ||
                  user.email?.split("@")[0] ||
                  "Моё пространство"}
              </strong>
              <small>{meQuery.data?.group.name ?? "Личный календарь"}</small>
            </span>
            <span className="account-menu">···</span>
          </button>
          {accountMenuOpen && (
            <div className="account-popover">
              <div className="popover-heading">Профиль и расписание</div>
              <button
                onClick={() => {
                  setAccountMenuOpen(false);
                  setShowGroupPicker(true);
                }}
              >
                <Icon name="cap" />
                <span>
                  {meQuery.data
                    ? "Сменить учебную группу"
                    : "Выбрать учебную группу"}
                </span>
              </button>
              <button
                onClick={() => {
                  setAccountMenuOpen(false);
                  setShowGoogleLink(true);
                }}
              >
                Связать с Google
              </button>
              <button onClick={() => void logout()}>
                <Icon name="logout" />
                <span>Выйти из аккаунта</span>
              </button>
            </div>
          )}
        </div>
      </aside>

      <section className="main-panel">
        <header className="topbar">
          <button
            className="mobile-navigation-button icon-button"
            aria-label="Открыть навигацию"
            onClick={() => setMobileNavigation(true)}
          >
            <Icon name="menu" />
          </button>
          <button
            className="mobile-menu"
            aria-label="Меню профиля"
            aria-expanded={topAccountMenuOpen}
            onClick={() => setTopAccountMenuOpen((open) => !open)}
          >
            <Icon name="menu" />
          </button>
          <div className="breadcrumb">
            Моё пространство <Icon name="chevron" />{" "}
            <strong>
              {sections.find((item) => item.id === section)?.title}
            </strong>
          </div>
          <div className="topbar-actions">
            <button
              className="top-search icon-button"
              aria-label="Поиск по пространству"
              onClick={() => navigate("search")}
            >
              <span aria-hidden="true">⌕</span>
              <span>Поиск</span>
            </button>
            <button
              className="icon-button notification-shortcut"
              aria-label="Открыть уведомления"
              onClick={() => navigate("notifications")}
            >
              <NavIcon
                path={
                  sections.find((item) => item.id === "notifications")!.icon
                }
              />
            </button>
            <ThemeToggle />
            <span
              className={`connection-dot ${calendarQuery.isError ? "offline" : ""}`}
            />
            <span className="connection-label">
              {syncPending
                ? "Загрузка расписания"
                : calendarQuery.isFetching
                  ? "Синхронизация"
                  : calendarQuery.isError
                    ? "Нет соединения"
                    : "Синхронизировано"}
            </span>
            <button
              className="avatar top-avatar"
              aria-label="Меню профиля"
              aria-expanded={topAccountMenuOpen}
              onClick={() => setTopAccountMenuOpen((open) => !open)}
            >
              U
            </button>
          </div>
          {topAccountMenuOpen && (
            <div className="top-account-popover">
              <div className="popover-heading">Профиль и расписание</div>
              <button
                onClick={() => {
                  setTopAccountMenuOpen(false);
                  setShowGroupPicker(true);
                }}
              >
                <Icon name="cap" />
                <span>
                  {meQuery.data
                    ? "Сменить учебную группу"
                    : "Выбрать учебную группу"}
                </span>
              </button>
              <button
                onClick={() => {
                  setTopAccountMenuOpen(false);
                  setShowGoogleLink(true);
                }}
              >
                Связать с Google
              </button>
              <button onClick={() => void logout()}>
                <Icon name="logout" />
                <span>Выйти из аккаунта</span>
              </button>
            </div>
          )}
        </header>

        <div className="content-wrap">
          {section === "calendar" ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="greeting">ТВОЯ НЕДЕЛЯ</div>
                  <h1>Календарь</h1>
                  <p className="heading-subtitle">
                    Спокойный взгляд на предстоящие дни.
                  </p>
                </div>
                <button
                  className="primary-button create-button"
                  onClick={() => openCreate()}
                >
                  <Icon name="plus" />
                  <span>Новое событие</span>
                </button>
              </div>

              <section
                className="calendar-card"
                aria-label="Календарь на неделю"
              >
                <div className="calendar-toolbar">
                  <div className="week-title">
                    <strong>
                      {dateLabel} — {weekEndLabel}
                    </strong>
                    <span>
                      {prettyDate(selected, {
                        weekday: "long",
                        day: "numeric",
                        month: "long",
                      })}{" "}
                      · {timeZone}
                    </span>
                  </div>
                  <div className="calendar-controls">
                    <button
                      className="today-button"
                      onClick={() => setSelected(dateKey(new Date(), timeZone))}
                    >
                      Сегодня
                    </button>
                    <div className="arrow-group">
                      <button
                        aria-label={
                          calendarView === "week"
                            ? "Предыдущая неделя"
                            : "Предыдущий день"
                        }
                        onClick={() =>
                          setSelected(
                            shiftDate(
                              selected,
                              calendarView === "week" ? -7 : -1,
                            ),
                          )
                        }
                      >
                        ‹
                      </button>
                      <button
                        aria-label={
                          calendarView === "week"
                            ? "Следующая неделя"
                            : "Следующий день"
                        }
                        onClick={() =>
                          setSelected(
                            shiftDate(
                              selected,
                              calendarView === "week" ? 7 : 1,
                            ),
                          )
                        }
                      >
                        ›
                      </button>
                    </div>
                    <div className="view-picker">
                      <button
                        type="button"
                        className="view-select"
                        aria-haspopup="menu"
                        aria-expanded={viewMenuOpen}
                        aria-controls="calendar-view-menu"
                        onClick={() => setViewMenuOpen((open) => !open)}
                      >
                        <Icon name="calendar" />{" "}
                        {calendarView === "week" ? "Неделя" : "День"}{" "}
                        <span>⌄</span>
                      </button>
                      {viewMenuOpen && (
                        <div
                          className="view-menu"
                          id="calendar-view-menu"
                          role="menu"
                          aria-label="Вид календаря"
                        >
                          <div className="view-menu-title">Вид календаря</div>
                          <button
                            type="button"
                            role="menuitemradio"
                            aria-checked={calendarView === "week"}
                            onClick={() => {
                              setCalendarView("week");
                              setViewMenuOpen(false);
                            }}
                          >
                            <span>Неделя</span>
                            <small>7 дней</small>
                            {calendarView === "week" && (
                              <strong aria-hidden="true">✓</strong>
                            )}
                          </button>
                          <button
                            type="button"
                            role="menuitemradio"
                            aria-checked={calendarView === "day"}
                            onClick={() => {
                              setCalendarView("day");
                              setViewMenuOpen(false);
                            }}
                          >
                            <span>День</span>
                            <small>Выбранный день</small>
                            {calendarView === "day" && (
                              <strong aria-hidden="true">✓</strong>
                            )}
                          </button>
                          <button type="button" role="menuitem" disabled>
                            <span>Месяц</span>
                            <small>Пока недоступен</small>
                          </button>
                          <p>
                            Это настройка отображения календаря. Расписание IIS
                            загружается отдельно и показывается здесь после
                            успешного импорта.
                          </p>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div
                  className="calendar-legend"
                  aria-label="Отображаемые источники"
                >
                  <label>
                    <input
                      type="checkbox"
                      checked={showPersonal}
                      onChange={(event) =>
                        setShowPersonal(event.target.checked)
                      }
                    />
                    <span className="legend-dot personal-dot" />
                    Личные события
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={showOfficial}
                      onChange={(event) =>
                        setShowOfficial(event.target.checked)
                      }
                    />
                    <span className="legend-dot official-dot" />
                    Расписание IIS
                  </label>
                  <small>Фильтры меняют только отображение</small>
                </div>
                <div
                  className="calendar-scroll"
                  ref={calendarScroll}
                  role="region"
                  aria-label="Часы календаря"
                  tabIndex={0}
                >
                  <div
                    className={`week-grid ${calendarView === "day" ? "single-day-grid" : ""}`}
                  >
                    <div className="time-column">
                      <div className="day-heading spacer-heading" />
                      <div className="all-day-label">
                        {clockChangeWeek ? "ОТ 00:00" : "ВЕСЬ ДЕНЬ"}
                      </div>
                      {Array.from({ length: gridHours }, (_, index) => (
                        <div className="time-label" key={index}>
                          {clockChangeWeek
                            ? `+${index} ч`
                            : `${String(index).padStart(2, "0")}:00`}
                        </div>
                      ))}
                    </div>
                    {days.map((day, dayIndex) => {
                      const dayKey = day;
                      const dayEvents = daySegments(
                        events,
                        boundaries[dayIndex],
                        boundaries[dayIndex + 1],
                      );
                      const columns = eventColumns(dayEvents);
                      if (calendarView === "day" && dayKey !== selectedKey)
                        return null;
                      return (
                        <div
                          className={`day-column ${dayKey === today ? "is-today" : ""} ${dayKey === selectedKey ? "is-selected" : ""}`}
                          key={dayKey}
                        >
                          <button
                            className="day-heading"
                            onClick={() => setSelected(day)}
                          >
                            <span>{shortWeekdays[dayIndex]}</span>
                            <strong>{Number(day.slice(-2))}</strong>
                          </button>
                          <button
                            className="all-day-cell"
                            onClick={() => openCreate(day)}
                            aria-label={`Добавить событие на ${weekdays[dayIndex]}`}
                          />
                          <div
                            className="day-canvas"
                            style={{
                              height: `${dayHours[dayIndex] * hourHeight}px`,
                            }}
                          >
                            {Array.from(
                              { length: Math.ceil(dayHours[dayIndex]) },
                              (_, index) => (
                                <div
                                  className="hour-line"
                                  key={index}
                                  style={{ top: `${index * hourHeight}px` }}
                                >
                                  {clockChangeWeek && (
                                    <span className="day-hour-label">
                                      {prettyDate(
                                        new Date(
                                          boundaries[dayIndex].getTime() +
                                            index * 3_600_000,
                                        ),
                                        {
                                          hour: "2-digit",
                                          minute: "2-digit",
                                          timeZoneName: "shortOffset",
                                        },
                                      )}
                                    </span>
                                  )}
                                </div>
                              ),
                            )}
                            {dayEvents.map((segment) => {
                              const item = segment.originalEvent;
                              const start = new Date(segment.starts_at);
                              const finish = new Date(segment.ends_at);
                              const top =
                                ((start.getTime() -
                                  boundaries[dayIndex].getTime()) /
                                  3_600_000) *
                                hourHeight;
                              const height = Math.max(
                                1,
                                ((finish.getTime() - start.getTime()) /
                                  3_600_000) *
                                  hourHeight,
                              );
                              const column = columns.get(item.id) ?? {
                                lane: 0,
                                count: 1,
                              };
                              const left = `calc(${(column.lane * 100) / column.count}% + 3px)`;
                              const right = `calc(${((column.count - column.lane - 1) * 100) / column.count}% + 3px)`;
                              return (
                                <button
                                  type="button"
                                  key={item.id}
                                  className={`event-card ${item.source === "official" ? "official-event" : "personal-event"} ${item.skipped ? "skipped-event" : ""}`}
                                  style={{
                                    top: `${top}px`,
                                    height: `${height}px`,
                                    left,
                                    right,
                                  }}
                                  onClick={() => {
                                    setSelected(day);
                                    openEvent(item);
                                  }}
                                  aria-label={`${item.title}, ${prettyDate(new Date(item.starts_at), { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })} — ${prettyDate(new Date(item.ends_at), { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })}`}
                                  title={`${item.title}${item.location ? ` · ${item.location}` : ""}`}
                                >
                                  <span className="event-time">
                                    {Date.parse(segment.starts_at) >
                                      Date.parse(item.starts_at) && "↪ "}
                                    {prettyDate(start, {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })}{" "}
                                    —{" "}
                                    {prettyDate(finish, {
                                      hour: "2-digit",
                                      minute: "2-digit",
                                    })}
                                  </span>
                                  <strong>{item.title}</strong>
                                  {height >= 76 &&
                                    (item.location || item.subject) && (
                                      <span className="event-location">
                                        {item.location || item.subject}
                                      </span>
                                    )}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
                {calendarQuery.isPending && (
                  <div className="calendar-overlay">
                    <span className="spinner" />
                    Загружаем расписание
                  </div>
                )}
                {!calendarQuery.isPending &&
                  !calendarQuery.isError &&
                  events.length === 0 && (
                    <div className="empty-note">
                      <span className="empty-icon">
                        <Icon name="calendar" />
                      </span>
                      <div>
                        <strong>
                          {allEvents.length
                            ? "События скрыты фильтрами"
                            : "На этой неделе пока нет событий"}
                        </strong>
                        <span>
                          {allEvents.length
                            ? "Включи нужный источник, чтобы снова увидеть события. Занятость не изменилась."
                            : "Добавь личное событие или подключи учебную группу в профиле."}
                        </span>
                      </div>
                      <button onClick={() => openCreate()}>
                        Добавить событие
                      </button>
                    </div>
                  )}
                {apiError && !needsAuth && (
                  <div className="inline-error" role="alert">
                    {apiError.message}
                    <button onClick={() => void calendarQuery.refetch()}>
                      Повторить
                    </button>
                  </div>
                )}
                {!!calendarQuery.data?.warnings.length && (
                  <p className="schedule-warning">
                    Учебное расписание может быть неактуальным. Проверь источник
                    перед важными планами.
                  </p>
                )}
                {syncNotice && (
                  <div
                    className={`schedule-sync-notice ${syncPending ? "is-loading" : syncFinished ? "is-success" : syncWaiting ? "is-loading" : "is-error"}`}
                    role="status"
                  >
                    {syncPending && <span className="spinner" />}
                    <span>{syncNotice}</span>
                    {!syncPending && meQuery.data && (
                      <button
                        type="button"
                        className="sync-retry-button"
                        onClick={() => void retryScheduleSync()}
                      >
                        Повторить синхронизацию
                      </button>
                    )}
                  </div>
                )}
              </section>

              <div className="below-grid">
                <section className="selected-day-card">
                  <div className="section-title">
                    <div>
                      <span className="greeting">ВЫБРАННЫЙ ДЕНЬ</span>
                      <h2>
                        {prettyDate(selected, {
                          weekday: "long",
                          day: "numeric",
                          month: "long",
                        })}
                      </h2>
                    </div>
                    <button
                      className="text-action"
                      onClick={() => openCreate()}
                    >
                      + Событие
                    </button>
                  </div>
                  {selectedEvents.length ? (
                    <div className="agenda-list">
                      {selectedEvents.map((item) => (
                        <button
                          type="button"
                          className="agenda-row"
                          key={item.id}
                          onClick={() => openEvent(item.originalEvent)}
                        >
                          <span
                            className={`agenda-dot ${item.source === "official" ? "dot-official" : "dot-personal"}`}
                          />
                          <span className="agenda-time">
                            {Date.parse(item.starts_at) >
                              Date.parse(item.originalEvent.starts_at) && "↪ "}
                            {prettyDate(new Date(item.starts_at), {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </span>
                          <span className="agenda-name">{item.title}</span>
                          <span className="agenda-place">
                            {item.location ?? item.subject ?? ""}
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="agenda-empty">
                      Здесь появятся события на выбранный день.
                    </p>
                  )}
                </section>
                <section className="schedule-source-card">
                  <div className="source-icon">
                    <Icon name="cap" />
                  </div>
                  <div className="source-copy">
                    <span className="greeting">УЧЕБНОЕ РАСПИСАНИЕ</span>
                    <strong>
                      {meQuery.data
                        ? `Группа ${meQuery.data.group.name}`
                        : "Добавь свою группу"}
                    </strong>
                    <p>
                      {meQuery.data
                        ? `Подгруппа: ${meQuery.data.subgroup ?? "все"}. Официальные занятия отображаются вместе с личными планами.`
                        : "Выбери группу, чтобы видеть пары в личном календаре."}
                    </p>
                  </div>
                  <button
                    aria-label="Настроить учебную группу"
                    className="source-chevron"
                    onClick={() => setShowGroupPicker(true)}
                  >
                    <Icon name="chevron" />
                  </button>
                </section>
              </div>
            </>
          ) : (
            <WorkspaceViews
              section={section}
              timeZone={timeZone}
              pageToOpen={pageToOpen}
              onOpenPage={openPage}
              onOpenEvent={async (id, startsAt, source) => {
                if (dirty) throw new Error("Отправь или очисти черновик перед переходом к событию.");
                const day = dateKey(new Date(startsAt), timeZone);
                const calendar = await requestJson<CalendarPayload>(
                  `/api/v1/calendar/events?date_from=${day}&date_to=${day}&include_hidden=true`,
                );
                const item = calendar.events.find((event) => event.source === source && event.source_event_id === id);
                if (!item) throw new Error("Событие изменилось или больше недоступно. Открой календарь для проверки.");
                setSelected(day);
                navigate("calendar");
                openEvent(item);
              }}
              onNavigate={navigate}
              onDirtyChange={setDirty}
              onChooseGroup={() => setShowGroupPicker(true)}
              events={allEvents}
            />
          )}
          {toast && (
            <div className="toast" role="status">
              {toast}
            </div>
          )}
          {showGoogleLink && (
            <GoogleLinkDialog
              onClose={() => setShowGoogleLink(false)}
              onSessionEnd={onSessionEnd}
            />
          )}
        </div>
      </section>

      {showEventForm && (
        <Modal
          title={editingEvent ? "Изменить событие" : "Новое событие"}
          onClose={() => setShowEventForm(false)}
        >
          <form className="event-modal" onSubmit={createEvent}>
            <span className="greeting">ЛИЧНЫЙ КАЛЕНДАРЬ</span>
            <h2>{editingEvent ? "Изменить событие" : "Новое событие"}</h2>
            <p>
              {editingEvent
                ? "Можно изменить личный план. Учебные пары остаются без изменений."
                : "Личное событие можно поставить в любое время, даже одновременно с парой."}
            </p>
            <p className="calendar-timezone">Часовой пояс: {timeZone}</p>
            <label htmlFor="event-title">Название</label>
            <input
              id="event-title"
              autoFocus
              required
              maxLength={200}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Например, подготовка к экзамену"
            />
            <div className="form-row">
              <div>
                <label htmlFor="event-start">Начало</label>
                <input
                  id="event-start"
                  type="datetime-local"
                  required
                  value={startValue}
                  onChange={(event) => {
                    setStartValue(event.target.value);
                    setStartInstant("");
                  }}
                />
                {startOptions.length > 1 && (
                  <select
                    aria-label="Смещение начала"
                    required
                    value={startInstant}
                    onChange={(event) => setStartInstant(event.target.value)}
                  >
                    <option value="" disabled>
                      Выберите смещение
                    </option>
                    {startOptions.map((instant) => (
                      <option key={instant} value={instant}>
                        {prettyDate(new Date(instant), {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZoneName: "shortOffset",
                        })}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div>
                <label htmlFor="event-end">Окончание</label>
                <input
                  id="event-end"
                  type="datetime-local"
                  required
                  value={endValue}
                  onChange={(event) => {
                    setEndValue(event.target.value);
                    setEndInstant("");
                  }}
                />
                {endOptions.length > 1 && (
                  <select
                    aria-label="Смещение окончания"
                    required
                    value={endInstant}
                    onChange={(event) => setEndInstant(event.target.value)}
                  >
                    <option value="" disabled>
                      Выберите смещение
                    </option>
                    {endOptions.map((instant) => (
                      <option key={instant} value={instant}>
                        {prettyDate(new Date(instant), {
                          hour: "2-digit",
                          minute: "2-digit",
                          timeZoneName: "shortOffset",
                        })}
                      </option>
                    ))}
                  </select>
                )}
              </div>
            </div>
            <label htmlFor="event-location">
              Место <span className="optional">необязательно</span>
            </label>
            <input
              id="event-location"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              maxLength={500}
              placeholder="Аудитория или место"
            />
            <label htmlFor="event-description">
              Описание <span className="optional">необязательно</span>
            </label>
            <textarea
              id="event-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={10000}
              placeholder="Подробности личного события"
            />
            {formError && (
              <p className="form-error" role="alert">
                {formError}
              </p>
            )}
            <div className="modal-actions">
              <button
                type="button"
                className="cancel-button"
                onClick={() => setShowEventForm(false)}
              >
                Отмена
              </button>
              {editingEvent && (
                <button
                  type="button"
                  className="cancel-button"
                  onClick={() => setPendingDelete(editingEvent)}
                >
                  Удалить
                </button>
              )}
              <button className="primary-button" disabled={saving}>
                {saving
                  ? "Сохраняем…"
                  : editingEvent
                    ? "Сохранить"
                    : "Добавить событие"}
              </button>
            </div>
            {editingEvent && (
              <EventExtras
                event={editingEvent}
                onOpenPage={(id) => {
                  setShowEventForm(false);
                  openPage(id);
                }}
              />
            )}
          </form>
        </Modal>
      )}
      {officialEvent && (
        <Modal
          title="Детали учебного события"
          onClose={() => setOfficialEvent(null)}
        >
          <section
            className="event-modal event-readonly"
            aria-labelledby="official-event-title"
          >
            <span className="greeting">РАСПИСАНИЕ IIS · ТОЛЬКО ПРОСМОТР</span>
            <h2 id="official-event-title">
              {officialEvent.subject_full_name ||
                officialEvent.subject ||
                officialEvent.title}
            </h2>
            <p>
              {prettyDate(new Date(officialEvent.starts_at), {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </p>
            <dl>
              <div>
                <dt>Время</dt>
                <dd>
                  {prettyDate(new Date(officialEvent.starts_at), {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}{" "}
                  —{" "}
                  {prettyDate(new Date(officialEvent.ends_at), {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </dd>
              </div>
              {officialEvent.lesson_type && (
                <div>
                  <dt>Вид занятия</dt>
                  <dd>{officialEvent.lesson_type}</dd>
                </div>
              )}
              {officialEvent.rooms.length > 0 && (
                <div>
                  <dt>Аудитория</dt>
                  <dd>{officialEvent.rooms.join(", ")}</dd>
                </div>
              )}
              {officialEvent.teacher_names.length > 0 && (
                <div>
                  <dt>Преподаватель</dt>
                  <dd>{officialEvent.teacher_names.join(", ")}</dd>
                </div>
              )}
              {officialEvent.description && (
                <div>
                  <dt>Примечание</dt>
                  <dd>{officialEvent.description}</dd>
                </div>
              )}
              <div>
                <dt>Статус</dt>
                <dd>
                  {officialEvent.skipped
                    ? "Отменено или пропущено в календаре"
                    : "Источник: расписание БГУИР"}
                </dd>
              </div>
            </dl>
            <EventExtras
              event={officialEvent}
              onOpenPage={(id) => {
                setOfficialEvent(null);
                openPage(id);
              }}
            />
            <div className="modal-actions">
              <button
                type="button"
                className="primary-button"
                onClick={() => setOfficialEvent(null)}
              >
                Закрыть
              </button>
            </div>
          </section>
        </Modal>
      )}
      {pendingDelete && (
        <Modal title="Удалить событие" onClose={() => setPendingDelete(null)}>
          <h2>Удалить личное событие?</h2>
          {deleteError && (
            <p className="form-error" role="alert">
              {deleteError}
            </p>
          )}
          <p>
            «{pendingDelete.title}» будет удалено вместе с его напоминаниями.
            Связанные страницы сохранятся.
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setPendingDelete(null)}
            >
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={deletingEvent}
              onClick={() => void removeEvent(pendingDelete)}
            >
              Удалить событие
            </button>
          </div>
        </Modal>
      )}
      {mobileNavigation && (
        <Modal title="Навигация" onClose={() => setMobileNavigation(false)}>
          <Brand />
          <Navigation
            active={section}
            onNavigate={navigate}
            footer={
              <button className="nav-item" onClick={() => navigate("settings")}>
                Настройки
              </button>
            }
          />
        </Modal>
      )}
      {pendingSection && (
        <Modal
          title="Несохранённые изменения"
          onClose={() => setPendingSection(null)}
        >
          <h2>Оставить изменения?</h2>
          <p>
            На странице есть несохранённый текст. Сохраните его перед переходом
            или продолжите без сохранения.
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setPendingSection(null)}
            >
              Остаться
            </button>
            <button
              className="danger-button"
              onClick={() => {
                setDirty(false);
                setSection(pendingSection);
                setPendingSection(null);
                setMobileNavigation(false);
              }}
            >
              Перейти без сохранения
            </button>
          </div>
        </Modal>
      )}
    </main>
  );
}
