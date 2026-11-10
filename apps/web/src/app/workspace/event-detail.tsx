"use client";

import { useEffect, useRef } from "react";
import type { CalendarEvent } from "./workspace";
import { prettyDate } from "./calendar-time";
import { EventExtras } from "./panels/event-extras";

export function EventDetail({
  event,
  timeZone,
  onBack,
  onEdit,
  onMove,
  onOpenPage,
  onOpenEvent,
}: {
  event: CalendarEvent;
  timeZone: string;
  onBack: () => void;
  onEdit: () => void;
  onMove: () => void;
  onOpenPage: (id: string) => void;
  onOpenEvent: (
    id: string,
    startsAt: string,
    source: "personal" | "official",
  ) => Promise<void>;
}) {
  const official = event.source === "official";
  const back = useRef<HTMLButtonElement>(null);
  useEffect(() => { back.current?.focus(); }, [event.id]);
  return (
    <article
      className="event-detail feature-page"
      aria-label="Страница события"
    >
      <header className="event-detail-toolbar">
        <button ref={back} className="text-action" onClick={onBack}>
          ← К календарю
        </button>
        {!official && (
          <button className="secondary-button" onClick={onEdit}>
            Изменить событие
          </button>
        )}
        {!official && (
          <button className="text-action" onClick={onMove}>Перенести событие</button>
        )}
      </header>
      <div className="event-detail-sheet">
        <span className="greeting">
          {official ? "Расписание IIS" : "Личный календарь"}
        </span>
        <h1>{event.title}</h1>
        {official &&
          event.subject_full_name &&
          event.subject_full_name !== event.title && (
            <p>{event.subject_full_name}</p>
          )}
        <dl className="event-detail-facts">
          <div>
            <dt>Начало</dt>
            <dd>
              {prettyDate(new Date(event.starts_at), timeZone, {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit",
                timeZoneName: "shortOffset",
              })}
            </dd>
          </div>
          <div>
            <dt>Окончание</dt>
            <dd>
              {prettyDate(new Date(event.ends_at), timeZone, {
                day: "numeric",
                month: "long",
                hour: "2-digit",
                minute: "2-digit",
                timeZoneName: "shortOffset",
              })}
            </dd>
          </div>
          {(event.location || event.rooms.length > 0) && (
            <div>
              <dt>Место</dt>
              <dd>{event.location || event.rooms.join(", ")}</dd>
            </div>
          )}
          {official &&
            event.rooms.length > 0 &&
            event.location &&
            event.location !== event.rooms.join(", ") && (
              <div>
                <dt>Аудитория IIS</dt>
                <dd>{event.rooms.join(", ")}</dd>
              </div>
            )}
          {event.lesson_type && (
            <div>
              <dt>Вид занятия</dt>
              <dd>{event.lesson_type}</dd>
            </div>
          )}
          {event.teacher_names.length > 0 && (
            <div>
              <dt>Преподаватель</dt>
              <dd>{event.teacher_names.join(", ")}</dd>
            </div>
          )}
          <div>
            <dt>Время в календаре</dt>
            <dd>
              {event.skipped
                ? "Пропущено"
                : event.blocks_time
                  ? "Занято"
                  : "Не занимает время"}
            </dd>
          </div>
        </dl>
        {event.description && (
          <section className="event-detail-description">
            <h2>Описание</h2>
            <p>{event.description}</p>
          </section>
        )}
        {official && (
          <p className="muted">
            Официальное событие IIS · только просмотр. Связанные заметки
            принадлежат тебе и сохраняются отдельно.
          </p>
        )}
        <EventExtras
          key={event.id}
          event={event}
          expanded
          onOpenPage={onOpenPage}
          onOpenEvent={onOpenEvent}
        />
      </div>
    </article>
  );
}
