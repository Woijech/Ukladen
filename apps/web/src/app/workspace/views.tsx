"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Image from "next/image";
import dynamic from "next/dynamic";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { csrfToken, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, QueryState, useAction } from "@/shared/ui";
import { ThemeOptions } from "@/shared/theme";
const NotesPanel = dynamic(() =>
  import("./panels/notes").then((module) => module.NotesPanel),
);
import {
  MaterialsPanel,
  SearchPanel,
  NotificationsPanel,
} from "./panels/resources";
const DatabasesPanel = dynamic(() =>
  import("./panels/databases").then((module) => module.DatabasesPanel),
);
const AiPanel = dynamic(() =>
  import("./panels/ai").then((module) => module.AiPanel),
);
const TasksPanel = dynamic(() =>
  import("./tasks-panel").then((module) => module.TasksPanel),
);
import { OrganizationPanel, type EventTarget } from "./panels/organization";
import type { SectionKey } from "./navigation";
import "./utility-workspace.css";
import type { WorkspaceLocation } from "./workspace-location";

type ViewProps = {
  section: SectionKey;
  timeZone: string;
  location: WorkspaceLocation;
  onLocationChange: (location: WorkspaceLocation, replace?: boolean) => void;
  onNavigateLocation: (location: WorkspaceLocation) => void;
  onBusyChange: (busy: boolean) => void;
  onOpenPage: (id: string) => void;
  onOpenEvent: (id: string, startsAt: string, source: "personal" | "official") => Promise<void>;
  onNavigate: (section: SectionKey) => void;
  onDirtyChange: (dirty: boolean) => void;
  onChooseGroup: () => void;
  onSessionEnd: () => void;
  events: EventTarget[];
};
export function WorkspaceViews(props: ViewProps) {
  const { section, timeZone, onOpenPage, onNavigate } = props;
  if (section === "ai")
    return (
      <Suspense fallback={<p role="status">Загрузка AI…</p>}>
        <AiPanel onDirtyChange={props.onDirtyChange} onOpenPage={onOpenPage} onOpenEvent={props.onOpenEvent} />
      </Suspense>
    );
  if (section === "tasks")
    return <TasksPanel selectedId={props.location.taskId ?? null} onSelectTask={id => props.onLocationChange({ section: "tasks", taskId: id ?? undefined })} onBusyChange={props.onBusyChange} timeZone={timeZone} onSessionEnd={props.onSessionEnd} onOpenPage={onOpenPage} onDirtyChange={props.onDirtyChange} />;
  if (section === "notes")
    return (
      <NotesPanel
        selectedId={props.location.pageId ?? null}
        onSelectPage={id => props.onLocationChange({ section: "notes", pageId: id ?? undefined })}
        onBusyChange={props.onBusyChange}
        onDirtyChange={props.onDirtyChange}
      />
    );
  if (section === "materials") return <MaterialsPanel />;
  if (section === "search")
    return (
      <SearchPanel
        key={typeof window === "undefined" ? "" : window.location.search}
        onOpenPage={onOpenPage}
        onMaterials={() => onNavigate("materials")}
      />
    );
  if (section === "notifications")
    return <NotificationsPanel timeZone={timeZone} />;
  if (section === "databases")
    return <DatabasesPanel location={props.location} onNavigate={props.onNavigateLocation} onLocationChange={props.onLocationChange} onBusyChange={props.onBusyChange} timeZone={timeZone} onOpenPage={onOpenPage} onDirtyChange={props.onDirtyChange} />;
  if (section === "organization")
    return <OrganizationPanel events={props.events} onOpenPage={onOpenPage} />;
  if (section === "settings")
    return <SettingsPanel onChooseGroup={props.onChooseGroup} onDirtyChange={props.onDirtyChange} />;
  return (
    <HomePanel
      onNavigate={onNavigate}
      onOpenPage={onOpenPage}
      timeZone={timeZone}
    />
  );
}

function HomePanel({
  onNavigate,
  onOpenPage,
  timeZone,
}: {
  onNavigate: (section: SectionKey) => void;
  onOpenPage: (id: string) => void;
  timeZone: string;
}) {
  const pages = useQuery({
    queryKey: ["home-pages"],
    queryFn: ({ signal }) =>
      requestJson<{ items: { id: string; title: string }[] }>(
        "/api/v1/notes/pages?limit=5",
        { signal },
      ),
  });
  const date = new Intl.DateTimeFormat("ru", {
    timeZone,
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());
  return (
    <div className="feature-page dashboard">
      <div className="page-heading">
        <div>
          <span className="greeting">{date}</span>
          <h1>Главная</h1>
        </div>
      </div>
      <section className="home-start" aria-label="Начать работу">
        <h2>Продолжить работу</h2>
        <div className="home-work-links">
          <button className="primary-button" onClick={() => onNavigate("calendar")}>Открыть календарь</button>
          <button className="secondary-button" onClick={() => onNavigate("tasks")}>Задачи</button>
          <button className="secondary-button" onClick={() => onNavigate("notes")}>Заметки</button>
        </div>
      </section>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-toolbar">
            <h2>Твои страницы</h2>
            <button className="text-action" onClick={() => onNavigate("notes")}>
              Все заметки
            </button>
          </div>
          <QueryState
            pending={pages.isPending}
            error={pages.error}
            retry={() => void pages.refetch()}
          />
          {pages.data?.items.map((page) => (
            <button
              className="dashboard-page"
              key={page.id}
              onClick={() => onOpenPage(page.id)}
            >
              <span>▤</span>
              {page.title}
              <span>↗</span>
            </button>
          ))}
          {pages.data && !pages.data.items.length && (
            <p className="panel-note muted">Первые идеи ждут своей страницы.</p>
          )}
        </section>
        <section className="panel quick-access">
          <span className="greeting">Быстрый доступ</span>
          <button onClick={() => onNavigate("materials")}>
            <span>▱</span>
            <div>
              <strong>Материалы</strong>
              <small>Файлы и полезные ссылки</small>
            </div>
            →
          </button>
          <button onClick={() => onNavigate("databases")}>
            <span>▦</span>
            <div>
              <strong>Базы данных</strong>
              <small>Базы данных и представления</small>
            </div>
            →
          </button>
          <button onClick={() => onNavigate("notifications")}>
            <span>◷</span>
            <div>
              <strong>Уведомления</strong>
              <small>Напоминания и входящие</small>
            </div>
            →
          </button>
        </section>
      </div>
    </div>
  );
}

type Profile = {
  id: string;
  email: string;
  display_name: string | null;
  timezone: string;
  locale: string;
  avatar_url: string | null;
  updated_at: string;
};
function SettingsPanel({ onChooseGroup, onDirtyChange }: { onChooseGroup: () => void; onDirtyChange: (dirty: boolean) => void }) {
  const profile = useQuery({
    queryKey: ["settings-profile"],
    queryFn: ({ signal }) =>
      requestJson<Profile>("/api/v1/users/me", { signal }),
  });
  return (
    <div className="feature-page settings-page">
      <div className="page-heading">
        <div>
          <h1>Настройки</h1>
          <p className="heading-subtitle">Профиль, внешний вид и расписание.</p>
        </div>
      </div>
      <QueryState
        pending={profile.isPending}
        error={profile.error}
        retry={() => void profile.refetch()}
      />
      <nav className="settings-sections" aria-label="Разделы настроек">
        <a href="#profile-settings">Профиль</a><a href="#appearance-settings">Оформление</a><a href="#schedule-settings">Расписание</a><a href="#assistant-settings">AI</a>
      </nav>
      {profile.data && (
        <section id="profile-settings" aria-label="Профиль">
          <AvatarSettings profile={profile.data} />
          <ProfileForm key={profile.data.id} profile={profile.data} onDirtyChange={onDirtyChange} />
        </section>
      )}
      <section id="appearance-settings" className="panel setting-section">
        <div>
          <h2>Внешний вид</h2>
          <p>
            Светлая, тёмная или системная тема. Сохраняется только настройка
            оформления.
          </p>
        </div>
        <ThemeOptions />
      </section>
      <section id="schedule-settings" className="panel setting-section">
        <div>
          <h2>Учебное расписание</h2>
          <p>
            Группа БГУИР необязательна. Личные события и страницы работают без
            неё.
          </p>
        </div>
        <button className="secondary-button" onClick={onChooseGroup}>
          Настроить группу
        </button>
      </section>
      <section id="assistant-settings" className="panel setting-section">
        <div>
          <h2>Помощник Ukladen</h2>
          <p>
            Модели, подключения и инструкции для чатов.
            Доступность моделей зависит от настройки сервера.
          </p>
        </div>
        <a className="secondary-button" href="/workspace/ai?tab=settings">Настроить AI</a>
      </section>
    </div>
  );
}
function ProfileForm({ profile, onDirtyChange }: { profile: Profile; onDirtyChange: (dirty: boolean) => void }) {
  const [name, setName] = useState(profile.display_name ?? "");
  const [confirmed, setConfirmed] = useState(profile.display_name ?? "");
  const dirty = name !== confirmed;
  const dirtyCallback = useRef(onDirtyChange);
  useEffect(() => { dirtyCallback.current = onDirtyChange; }, [onDirtyChange]);
  useEffect(() => {
    dirtyCallback.current(dirty);
    const prevent = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", prevent);
    return () => { dirtyCallback.current(false); window.removeEventListener("beforeunload", prevent); };
  }, [dirty]);
  const action = useAction();
  const client = useQueryClient();
  return (
    <form
      className="panel profile-form"
      onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        void action.run(async () => {
          await writeJson("/api/v1/users/me", "PATCH", {
            display_name: values.get("name") || null,
          });
          setConfirmed(name);
          await client.invalidateQueries({ queryKey: ["settings-profile"] });
          window.dispatchEvent(new Event("ukladen:profile-updated"));
        });
      }}
    >
      <fieldset className="profile-fields" disabled={action.busy}>
      <h2>Личный профиль</h2>
      <p className="muted">{profile.email}</p>
      <label className="field-label" htmlFor="profile-name">
        Имя
      </label>
      <input
        className="ui-input"
        id="profile-name"
        name="name"
        value={name}
        onChange={event => { setName(event.target.value); dirtyCallback.current(event.target.value !== confirmed); }}
        maxLength={100}
        placeholder="Как к тебе обращаться?"
      />
      <p className="muted">Часовой пояс: Минск (Europe/Minsk).</p>
      <ActionFeedback error={dirty ? action.error : ""} notice="" />
      <p className="profile-save-state muted" role="status">{action.busy ? "Сохраняем…" : dirty ? action.error ? "Ошибка сохранения" : "Есть изменения" : "Сохранено"}</p>
      <button className="primary-button" disabled={action.busy || !dirty}>
        {action.busy ? "Сохраняем…" : "Сохранить профиль"}
      </button>
      </fieldset>
    </form>
  );
}

function AvatarSettings({ profile }: { profile: Profile }) {
  const action = useAction();
  const client = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  async function updated() {
    await client.invalidateQueries({ queryKey: ["settings-profile"] });
    window.dispatchEvent(new Event("ukladen:profile-updated"));
  }
  return (
    <section className="panel avatar-settings">
      <div className="profile-avatar">
        {profile.avatar_url ? (
          <Image
            src={`/api/v1/users/me/avatar?revision=${encodeURIComponent(profile.updated_at)}`}
            alt="Ваш аватар"
            width={64}
            height={64}
            unoptimized
          />
        ) : (
          <span>
            {(profile.display_name || profile.email)[0].toUpperCase()}
          </span>
        )}
      </div>
      <div>
        <h2>Фото профиля</h2>
        <p className="muted">
          JPEG, PNG или WebP · до 2 МБ. Фото доступно только в твоём аккаунте.
        </p>
        <label className="secondary-button avatar-file-label">
          Изменить фото
          <input
            className="sr-only"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            disabled={action.busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              void action.run(async () => {
                if (
                  !file.size ||
                  file.size > 2 * 1024 * 1024 ||
                  !["image/jpeg", "image/png", "image/webp"].includes(file.type)
                )
                  throw new Error(
                    "Выберите JPEG, PNG или WebP размером до 2 МБ.",
                  );
                const token = await csrfToken();
                await requestJson("/api/v1/users/me/avatar", {
                  method: "PUT",
                  headers: { "X-CSRF-Token": token, "Content-Type": file.type },
                  body: file,
                });
                await updated();
              }, "Фото обновлено");
            }}
          />
        </label>
        {profile.avatar_url && (
          <button
            className="text-action danger-text"
            onClick={() => setConfirm(true)}
          >
            Удалить фото
          </button>
        )}
        <ActionFeedback {...action} />
        {confirm && (
          <div className="confirm-inline">
            <p>Удалить фото профиля?</p>
            <button
              className="secondary-button"
              onClick={() => setConfirm(false)}
            >
              Отмена
            </button>{" "}
            <button
              className="danger-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await writeJson("/api/v1/users/me/avatar", "DELETE");
                  setConfirm(false);
                  await updated();
                }, "Фото удалено")
              }
            >
              Удалить
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
