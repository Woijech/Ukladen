"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  Pager,
  QueryState,
  useAction,
} from "@/shared/ui";
import type { PageSummary } from "./notes";
export type EventTarget = {
  source: "personal" | "official";
  source_event_id: string;
  title: string;
};
type Organization = {
  id: string;
  name: string;
  color: string | null;
  version: number;
};
type Member = {
  membership: {
    id: string;
    target_type: "page" | "personal" | "official";
    target_id: string;
  };
  target: { title: string; trashed_at?: string | null; starts_at?: string };
};

export function OrganizationPanel({
  events,
  onOpenPage,
}: {
  events: EventTarget[];
  onOpenPage: (id: string) => void;
}) {
  const [kind, setKind] = useState<"collections" | "tags">("collections");
  const [selected, setSelected] = useState<Organization | null>(null);
  const [offset, setOffset] = useState(0);
  const [memberOffset, setMemberOffset] = useState(0);
  const [editing, setEditing] = useState<Organization | "new" | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [adding, setAdding] = useState(false);
  const [targetType, setTargetType] = useState("page");
  const base = `/api/v1/workspace/${kind}`;
  const client = useQueryClient();
  const action = useAction();
  const items = useQuery({
    queryKey: ["organizations", kind, offset],
    queryFn: ({ signal }) =>
      requestJson<{ items: Organization[] }>(
        `${base}?limit=50&offset=${offset}`,
        { signal },
      ),
  });
  const members = useQuery({
    queryKey: ["members", kind, selected?.id, memberOffset],
    queryFn: ({ signal }) =>
      requestJson<{ items: Member[] }>(
        `${base}/${selected!.id}/members?limit=50&offset=${memberOffset}`,
        { signal },
      ),
    enabled: !!selected,
  });
  const pages = useQuery({
    queryKey: ["member-page-options"],
    queryFn: ({ signal }) =>
      requestJson<{ items: PageSummary[] }>("/api/v1/notes/pages?limit=200", {
        signal,
      }),
    enabled: adding,
  });
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["organizations"] }),
      client.invalidateQueries({ queryKey: ["members"] }),
    ]);
  }
  return (
    <div className="feature-page">
      <div className="page-heading">
        <div>
          <span className="greeting">СВЯЗИ, КОТОРЫЕ ВЫБИРАЕШЬ ТЫ</span>
          <h1>Коллекции и теги</h1>
          <p className="heading-subtitle">
            Объединяй страницы и события без копирования.
          </p>
        </div>
        <button className="primary-button" onClick={() => setEditing("new")}>
          + {kind === "collections" ? "Коллекция" : "Тег"}
        </button>
      </div>
      <div className="segmented-control organization-tabs">
        <button
          className={kind === "collections" ? "selected" : ""}
          onClick={() => {
            setKind("collections");
            setSelected(null);
            setOffset(0);
          }}
        >
          Коллекции
        </button>
        <button
          className={kind === "tags" ? "selected" : ""}
          onClick={() => {
            setKind("tags");
            setSelected(null);
            setOffset(0);
          }}
        >
          Теги
        </button>
      </div>
      <div className="organization-layout">
        <aside className="panel">
          <QueryState
            pending={items.isPending}
            error={items.error}
            retry={() => void items.refetch()}
          />
          {items.data?.items.map((item) => (
            <button
              key={item.id}
              className={`tree-row ${selected?.id === item.id ? "selected" : ""}`}
              onClick={() => {
                setSelected(item);
                setMemberOffset(0);
              }}
            >
              <span
                className="organization-dot"
                style={{ background: item.color ?? "var(--accent)" }}
              />
              {item.name}
            </button>
          ))}
          {items.data && !items.data.items.length && (
            <p className="tree-empty muted">
              {kind === "collections" ? "Пока нет коллекций" : "Пока нет тегов"}
            </p>
          )}
          {items.data && (offset || items.data.items.length === 50) ? (
            <Pager
              offset={offset}
              count={items.data.items.length}
              onChange={setOffset}
            />
          ) : null}
        </aside>
        <section className="panel">
          {selected ? (
            <>
              <div className="panel-toolbar">
                <h2>{selected.name}</h2>
                <div className="row-actions">
                  <button
                    className="text-action"
                    onClick={() => setEditing(selected)}
                  >
                    Изменить
                  </button>
                  <button
                    className="text-action danger-text"
                    onClick={() => setDeleting(true)}
                  >
                    Удалить
                  </button>
                  <button
                    className="secondary-button"
                    onClick={() => setAdding(true)}
                  >
                    + Добавить
                  </button>
                </div>
              </div>
              <QueryState
                pending={members.isPending}
                error={members.error}
                retry={() => void members.refetch()}
              />
              {members.data && !members.data.items.length && (
                <EmptyState title="Выбери, что здесь будет">
                  <p>
                    Добавь страницы или события. Вложенные и связанные объекты
                    автоматически не добавляются.
                  </p>
                  <button
                    className="primary-button"
                    onClick={() => setAdding(true)}
                  >
                    Добавить участника
                  </button>
                </EmptyState>
              )}
              {members.data?.items.map((item) => (
                <div className="resource-row" key={item.membership.id}>
                  <span className="file-icon">
                    {item.membership.target_type === "page" ? "▤" : "▦"}
                  </span>
                  <div className="resource-copy">
                    {item.membership.target_type === "page" ? (
                      <button
                        className="table-page-link"
                        onClick={() => onOpenPage(item.membership.target_id)}
                      >
                        {item.target.title}
                      </button>
                    ) : (
                      <strong>{item.target.title}</strong>
                    )}
                    <p>
                      {item.membership.target_type === "page"
                        ? item.target.trashed_at
                          ? "Страница в корзине"
                          : "Страница"
                        : item.membership.target_type === "official"
                          ? "Событие IIS"
                          : "Личное событие"}
                    </p>
                  </div>
                  <button
                    className="text-action"
                    disabled={action.busy}
                    onClick={() =>
                      void action.run(async () => {
                        await writeJson(
                          `${base}/${selected.id}/members/${item.membership.target_type}/${item.membership.target_id}`,
                          "DELETE",
                        );
                        await refresh();
                      }, "Связь удалена. Объект сохранён.")
                    }
                  >
                    Убрать связь
                  </button>
                </div>
              ))}
              {members.data &&
              (memberOffset || members.data.items.length === 50) ? (
                <Pager
                  offset={memberOffset}
                  count={members.data.items.length}
                  onChange={setMemberOffset}
                />
              ) : null}
            </>
          ) : (
            <EmptyState title="Твоя организация, твои правила" icon="#">
              <p>
                Коллекции и теги ссылаются на объекты. Удаление коллекции не
                удалит её содержимое.
              </p>
            </EmptyState>
          )}
        </section>
      </div>
      <ActionFeedback {...action} />
      {editing && (
        <Modal
          title={editing === "new" ? "Создать" : "Изменить"}
          onClose={() => setEditing(null)}
        >
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              void action.run(async () => {
                const item = await writeJson<Organization>(
                  editing === "new" ? base : `${base}/${editing.id}`,
                  editing === "new" ? "POST" : "PATCH",
                  {
                    name: values.get("name"),
                    color: values.get("color"),
                    ...(editing === "new"
                      ? {}
                      : { expected_version: editing.version }),
                  },
                );
                setSelected(item);
                await refresh();
                setEditing(null);
              });
            }}
          >
            <h2>
              {editing === "new" ? "Новая организация" : "Изменить название"}
            </h2>
            <label htmlFor="organization-name">Название</label>
            <input
              id="organization-name"
              name="name"
              required
              maxLength={100}
              defaultValue={editing === "new" ? "" : editing.name}
              autoFocus
            />
            <label htmlFor="organization-color">Цвет метки</label>
            <input
              id="organization-color"
              name="color"
              type="color"
              defaultValue={
                editing === "new" ? "#8971a9" : (editing.color ?? "#8971a9")
              }
            />
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button className="primary-button" disabled={action.busy}>
                Сохранить
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && selected && (
        <Modal title="Удалить организацию" onClose={() => setDeleting(false)}>
          <h2>Удалить «{selected.name}»?</h2>
          <p>
            Будут удалены только название и связи. Страницы и события
            сохранятся.
          </p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setDeleting(false)}
            >
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await writeJson(
                    `${base}/${selected.id}?expected_version=${selected.version}`,
                    "DELETE",
                  );
                  setSelected(null);
                  setDeleting(false);
                  await refresh();
                }, "Удалено")
              }
            >
              Удалить
            </button>
          </div>
        </Modal>
      )}
      {adding && selected && (
        <Modal title="Добавить связь" onClose={() => setAdding(false)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const value = new FormData(event.currentTarget).get("target");
              void action.run(async () => {
                await writeJson(
                  `${base}/${selected.id}/members/${targetType}/${value}`,
                  "PUT",
                );
                await refresh();
                setAdding(false);
              });
            }}
          >
            <h2>Добавить в «{selected.name}»</h2>
            <label htmlFor="member-type">Тип объекта</label>
            <select
              id="member-type"
              value={targetType}
              onChange={(event) => setTargetType(event.target.value)}
            >
              <option value="page">Страница</option>
              <option value="personal">Личное событие</option>
              <option value="official">Событие IIS</option>
            </select>
            <label htmlFor="member-target">Объект</label>
            <QueryState
              pending={targetType === "page" && pages.isPending}
              error={pages.error}
              retry={() => void pages.refetch()}
            />
            <select id="member-target" name="target" required key={targetType}>
              <option value="">Выбрать…</option>
              {targetType === "page"
                ? pages.data?.items.map((page) => (
                    <option value={page.id} key={page.id}>
                      {page.title}
                    </option>
                  ))
                : events
                    .filter((event) => event.source === targetType)
                    .map((event) => (
                      <option
                        value={event.source_event_id}
                        key={event.source_event_id}
                      >
                        {event.title}
                      </option>
                    ))}
            </select>
            <p className="muted">
              {targetType === "page"
                ? "Первые 200 активных страниц."
                : "События выбранной недели календаря."}{" "}
              Добавление сохраняет только явную связь.
            </p>
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button className="primary-button" disabled={action.busy}>
                Добавить
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
