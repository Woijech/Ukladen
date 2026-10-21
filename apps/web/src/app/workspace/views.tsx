"use client";

import { useState } from "react";
import Image from "next/image";
import dynamic from "next/dynamic";
import symbol from "@/shared/assets/ukladen-avatar.png";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { csrfToken, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, QueryState, useAction } from "@/shared/ui";
import { ThemeToggle } from "@/shared/theme";
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
import { OrganizationPanel, type EventTarget } from "./panels/organization";
import type { SectionKey } from "./navigation";

type ViewProps = {
  section: SectionKey;
  timeZone: string;
  pageToOpen: string | null;
  onOpenPage: (id: string) => void;
  onNavigate: (section: SectionKey) => void;
  onDirtyChange: (dirty: boolean) => void;
  onChooseGroup: () => void;
  events: EventTarget[];
};
export function WorkspaceViews(props: ViewProps) {
  const { section, timeZone, onOpenPage, onNavigate } = props;
  if (section === "notes")
    return (
      <NotesPanel
        key={props.pageToOpen}
        initialPage={props.pageToOpen}
        onDirtyChange={props.onDirtyChange}
      />
    );
  if (section === "materials") return <MaterialsPanel />;
  if (section === "search")
    return (
      <SearchPanel
        onOpenPage={onOpenPage}
        onMaterials={() => onNavigate("materials")}
      />
    );
  if (section === "notifications")
    return <NotificationsPanel timeZone={timeZone} />;
  if (section === "databases")
    return <DatabasesPanel timeZone={timeZone} onOpenPage={onOpenPage} />;
  if (section === "organization")
    return <OrganizationPanel events={props.events} onOpenPage={onOpenPage} />;
  if (section === "settings")
    return <SettingsPanel onChooseGroup={props.onChooseGroup} />;
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
          <h1>Место для самого важного</h1>
          <p className="heading-subtitle">Немного ясности для нового дня.</p>
        </div>
      </div>
      <div className="dashboard-hero panel">
        <div>
          <span className="greeting">В СВОЁМ РИТМЕ</span>
          <h2>
            Не нужно держать
            <br />
            всё в голове.
          </h2>
          <p>
            Посмотри планы, запиши мысль или вернись к материалам. Здесь всё
            твоё.
          </p>
          <button
            className="primary-button"
            onClick={() => onNavigate("calendar")}
          >
            Открыть календарь →
          </button>
        </div>
        <div className="dashboard-mark" aria-hidden="true">
          <Image src={symbol} alt="" width={200} height={200} />
        </div>
      </div>
      <div className="dashboard-grid">
        <section className="panel">
          <div className="panel-toolbar">
            <h2>Твои страницы</h2>
            <button className="text-action" onClick={() => onNavigate("notes")}>
              Все заметки →
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
          <span className="greeting">БЫСТРЫЙ ДОСТУП</span>
          <button onClick={() => onNavigate("materials")}>
            <span>▱</span>
            <div>
              <strong>Твоя библиотека</strong>
              <small>Файлы и полезные ссылки</small>
            </div>
            →
          </button>
          <button onClick={() => onNavigate("databases")}>
            <span>▦</span>
            <div>
              <strong>Своя система</strong>
              <small>Базы данных и представления</small>
            </div>
            →
          </button>
          <button onClick={() => onNavigate("notifications")}>
            <span>◷</span>
            <div>
              <strong>Ничего не упустить</strong>
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
function SettingsPanel({ onChooseGroup }: { onChooseGroup: () => void }) {
  const profile = useQuery({
    queryKey: ["settings-profile"],
    queryFn: ({ signal }) =>
      requestJson<Profile>("/api/v1/users/me", { signal }),
  });
  return (
    <div className="feature-page settings-page">
      <div className="page-heading">
        <div>
          <span className="greeting">СДЕЛАЙ ПРОСТРАНСТВО СВОИМ</span>
          <h1>Настройки</h1>
          <p className="heading-subtitle">Профиль, внешний вид и расписание.</p>
        </div>
      </div>
      <QueryState
        pending={profile.isPending}
        error={profile.error}
        retry={() => void profile.refetch()}
      />
      {profile.data && (
        <>
          <AvatarSettings profile={profile.data} />
          <ProfileForm key={profile.data.id} profile={profile.data} />
        </>
      )}
      <section className="panel setting-section">
        <div>
          <h2>Внешний вид</h2>
          <p>
            Светлая, тёмная или системная тема. Сохраняется только настройка
            оформления.
          </p>
        </div>
        <ThemeToggle />
      </section>
      <section className="panel setting-section">
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
      <section className="panel setting-section">
        <div>
          <h2>AI Assistant</h2>
          <p>
            В разработке. Чат, источники, предложения действий и отзывные
            разрешения появятся после подключения серверного AI-модуля.
          </p>
        </div>
        <span className="status-pill">Пока недоступен</span>
      </section>
    </div>
  );
}
function ProfileForm({ profile }: { profile: Profile }) {
  const [timeZone, setTimeZone] = useState(profile.timezone);
  const action = useAction();
  const client = useQueryClient();
  const zones = Array.from(
    new Set(["UTC", profile.timezone, ...Intl.supportedValuesOf("timeZone")]),
  );
  return (
    <form
      className="panel profile-form"
      onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        void action.run(async () => {
          await writeJson("/api/v1/users/me", "PATCH", {
            display_name: values.get("name") || null,
            timezone: timeZone,
          });
          await client.invalidateQueries({ queryKey: ["settings-profile"] });
          window.dispatchEvent(new Event("ukladen:profile-updated"));
        });
      }}
    >
      <h2>Личный профиль</h2>
      <p className="muted">{profile.email}</p>
      <label className="field-label" htmlFor="profile-name">
        Имя
      </label>
      <input
        className="ui-input"
        id="profile-name"
        name="name"
        defaultValue={profile.display_name ?? ""}
        maxLength={100}
        placeholder="Как к тебе обращаться?"
      />
      <label className="field-label" htmlFor="profile-timezone">
        Часовой пояс календаря
      </label>
      <select
        className="ui-input"
        id="profile-timezone"
        value={timeZone}
        onChange={(event) => setTimeZone(event.target.value)}
      >
        {zones.map((zone) => (
          <option key={zone} value={zone}>
            {zone}
          </option>
        ))}
      </select>
      <p className="muted">
        Изменяет отображение дат. Сохранённые события остаются в своих исходных
        моментах времени.
      </p>
      <ActionFeedback {...action} />
      <button className="primary-button" disabled={action.busy}>
        Сохранить профиль
      </button>
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
