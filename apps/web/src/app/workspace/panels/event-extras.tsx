"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Pager, QueryState, useAction } from "@/shared/ui";
import type { PageSummary } from "./notes";
import { PageAttachments } from "./attachments";

export function EventExtras({
  event,
  onOpenPage,
  expanded = false,
  onOpenEvent,
}: {
  event: {
    source: "personal" | "official";
    source_event_id: string;
    starts_at: string;
    skipped: boolean;
  };
  onOpenPage: (id: string) => void;
  expanded?: boolean;
  onOpenEvent?: (
    id: string,
    startsAt: string,
    source: "personal" | "official",
  ) => Promise<void>;
}) {
  const base = `/api/v1/relations/calendar-events/${event.source}/${event.source_event_id}/pages`;
  const [open, setOpen] = useState(expanded);
  const [offset, setOffset] = useState(0);
  const [minutesValue, setMinutesValue] = useState("15");
  const client = useQueryClient();
  const action = useAction();
  const pages = useQuery({
    queryKey: ["event-page-options"],
    queryFn: ({ signal }) =>
      requestJson<{ items: PageSummary[] }>("/api/v1/notes/pages?limit=200", {
        signal,
      }),
    enabled: open,
  });
  const links = useQuery({
    queryKey: ["event-pages", event.source, event.source_event_id, offset],
    queryFn: ({ signal }) =>
      requestJson<{ items: { page: PageSummary }[] }>(
        `${base}?limit=200&offset=${offset}`,
        {
          signal,
        },
      ),
    enabled: open,
  });
  async function refresh() {
    await client.invalidateQueries({
      queryKey: ["event-pages", event.source, event.source_event_id],
    });
  }
  return (
    <section className="event-extras">
      {!expanded && (
        <button
          className="text-action"
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? "Скрыть связи и напоминания ↑" : "Заметки и напоминания ↓"}
        </button>
      )}
      {open && (
        <>
          <h2>Заметки события</h2>
          <QueryState
            pending={links.isPending}
            error={links.error}
            retry={() => void links.refetch()}
          />
          {links.data?.items.map((item) => (
            <div className="event-linked-page" key={item.page.id}>
              <div className="relation-row">
                <button
                  type="button"
                  className="table-page-link"
                  onClick={() => onOpenPage(item.page.id)}
                >
                  {item.page.title}
                  {item.page.trashed_at ? " · в корзине" : ""}
                </button>
                <button
                  type="button"
                  className="text-action"
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      await writeJson(`${base}/${item.page.id}`, "DELETE");
                      await refresh();
                    }, "Связь удалена. Страница сохранена.")
                  }
                >
                  Убрать связь
                </button>
              </div>
              {expanded && (
                <>
                  <PageAttachments
                    pageId={item.page.id}
                    readonly={!!item.page.trashed_at}
                  />
                  {onOpenEvent && (
                    <RelatedEvents
                      pageId={item.page.id}
                      current={event}
                      onOpenEvent={onOpenEvent}
                    />
                  )}
                </>
              )}
            </div>
          ))}
          {links.data && (offset > 0 || links.data.items.length === 200) ? (
            <Pager
              offset={offset}
              count={links.data.items.length}
              size={200}
              onChange={setOffset}
            />
          ) : null}
          {links.data?.items.length === 0 && (
            <p className="muted">Пока без связанных страниц.</p>
          )}
          <div className="event-link-form">
            <label
              className="field-label"
              htmlFor={`event-page-${event.source_event_id}`}
            >
              Добавить существующую страницу
            </label>
            <select
              className="ui-input"
              id={`event-page-${event.source_event_id}`}
              defaultValue=""
              disabled={action.busy || pages.isPending}
              onChange={(input) => {
                const id = input.target.value;
                if (id)
                  void action.run(async () => {
                    await writeJson(`${base}/${id}`, "PUT");
                    await refresh();
                  });
                input.target.value = "";
              }}
            >
              <option value="">Выбрать страницу…</option>
              {pages.data?.items
                .filter(
                  (page) =>
                    !links.data?.items.some((item) => item.page.id === page.id),
                )
                .map((page) => (
                  <option key={page.id} value={page.id}>
                    {page.title}
                  </option>
                ))}
            </select>
            <QueryState
              pending={false}
              error={pages.error}
              retry={() => void pages.refetch()}
            />
            <p className="muted">
              Показаны первые 200 активных страниц. Связь не меняет их
              содержимое.
            </p>
            <button
              type="button"
              className="secondary-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  const result = await writeJson<{ page: PageSummary }>(
                    base,
                    "POST",
                    { title: "Заметка к событию" },
                  );
                  await refresh();
                  await client.invalidateQueries({ queryKey: ["pages"] });
                  onOpenPage(result.page.id);
                }, "Страница создана")
              }
            >
              + Создать заметку к событию
            </button>
          </div>
          <h2>Напоминание</h2>
          <p className="muted">
            Появится во входящих Ukladen. Это одноразовое напоминание об этом
            событии.
          </p>
          <div className="reminder-create">
            <label htmlFor={`reminder-offset-${event.source_event_id}`}>
              За сколько минут
            </label>
            <input
              className="ui-input"
              id={`reminder-offset-${event.source_event_id}`}
              type="number"
              min={0}
              max={43200}
              step={1}
              value={minutesValue}
              onChange={(input) => setMinutesValue(input.target.value)}
            />
            <button
              type="button"
              className="secondary-button"
              disabled={action.busy || event.skipped}
              onClick={() => {
                const minutes = Number(minutesValue);
                void action.run(async () => {
                  if (
                    !minutesValue ||
                    !Number.isInteger(minutes) ||
                    minutes < 0 ||
                    minutes > 43200
                  )
                    throw new Error("Укажите целое число от 0 до 43200.");
                  if (
                    Date.parse(event.starts_at) - minutes * 60_000 <=
                    Date.now()
                  )
                    throw new Error(
                      "Время напоминания уже прошло. Выберите будущее событие или меньший интервал.",
                    );
                  await writeJson("/api/v1/reminders", "POST", {
                    source: event.source,
                    event_id: event.source_event_id,
                    minutes_before: minutes,
                  });
                  await client.invalidateQueries({ queryKey: ["reminders"] });
                }, "Напоминание создано");
              }}
            >
              Напомнить
            </button>
          </div>
          <ActionFeedback {...action} />
        </>
      )}
    </section>
  );
}

function RelatedEvents({
  pageId,
  current,
  onOpenEvent,
}: {
  pageId: string;
  current: { source: "personal" | "official"; source_event_id: string };
  onOpenEvent: (
    id: string,
    startsAt: string,
    source: "personal" | "official",
  ) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const action = useAction();
  const query = useQuery({
    queryKey: ["related-page-events", pageId, offset],
    queryFn: ({ signal }) =>
      requestJson<{
        items: {
          event: {
            source: "personal" | "official";
            event_id: string;
            title: string;
            starts_at: string;
            source_status: string;
          };
        }[];
      }>(
        `/api/v1/relations/pages/${pageId}/calendar-events?limit=50&offset=${offset}`,
        { signal },
      ),
    enabled: open,
  });
  const events =
    query.data?.items.filter(
      ({ event }) =>
        event.source !== current.source ||
        event.event_id !== current.source_event_id,
    ) ?? [];
  return (
    <section className="related-event-list">
      <button
        type="button"
        className="text-action"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        Связанные события этой заметки {open ? "↑" : "↓"}
      </button>
      {open && (
        <>
          <p className="muted">
            События, к которым прикреплена эта же заметка.
          </p>
          <QueryState
            pending={query.isPending}
            error={query.error}
            retry={() => void query.refetch()}
          />
          {query.data && !events.length && (
            <p className="muted">Других связанных событий здесь нет.</p>
          )}
          {events.map(({ event }) => (
            <div
              className="relation-row"
              key={`${event.source}:${event.event_id}`}
            >
              <button
                type="button"
                className="table-page-link"
                disabled={action.busy || event.source_status !== "active"}
                onClick={() =>
                  void action.run(
                    () =>
                      onOpenEvent(
                        event.event_id,
                        event.starts_at,
                        event.source,
                      ),
                    "Событие открыто",
                  )
                }
              >
                {event.title}
              </button>
              {event.source_status !== "active" && (
                <small>Историческая связь</small>
              )}
            </div>
          ))}
          {query.data && (offset > 0 || query.data.items.length === 50) ? (
            <Pager
              offset={offset}
              count={query.data.items.length}
              onChange={setOffset}
            />
          ) : null}
          <ActionFeedback {...action} />
        </>
      )}
    </section>
  );
}
