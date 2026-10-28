"use client";

import { useRef, useState, type PointerEvent, type KeyboardEvent } from "react";
import { prettyDate } from "./calendar-time";
import type { CalendarEvent } from "./workspace";

type Edge = "starts_at" | "ends_at";
type Resize = {
  event: CalendarEvent;
  edge: Edge;
  value: number;
  y: number;
  scroll: number;
  pointer: boolean;
};
const step = 15 * 60_000;

export function CalendarCard({
  event,
  dayStart,
  dayEnd,
  lane,
  count,
  hourHeight,
  timeZone,
  disabled,
  onOpen,
  onResize,
}: {
  event: CalendarEvent;
  dayStart: number;
  dayEnd: number;
  lane: number;
  count: number;
  hourHeight: number;
  timeZone: string;
  disabled: boolean;
  onOpen: () => void;
  onResize: (event: CalendarEvent, edge: Edge, value: string) => Promise<void>;
}) {
  const [preview, setPreview] = useState<Resize | null>(null);
  const active = useRef<Resize | null>(null);
  const [committing, setCommitting] = useState(false);
  const start =
    preview?.edge === "starts_at" ? preview.value : Date.parse(event.starts_at);
  const end =
    preview?.edge === "ends_at" ? preview.value : Date.parse(event.ends_at);
  const clippedStart = Math.max(start, dayStart);
  const clippedEnd = Math.min(end, dayEnd);
  const height = Math.max(
    1,
    ((clippedEnd - clippedStart) / 3_600_000) * hourHeight,
  );
  const format = (instant: number) =>
    prettyDate(new Date(instant), timeZone, {
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "shortOffset",
    });
  function cancel() {
    active.current = null;
    setPreview(null);
  }
  function change(session: Resize, value: number) {
    const minimum =
      session.edge === "starts_at"
        ? dayStart
        : Math.max(dayStart, Date.parse(session.event.starts_at) + 60_000);
    const maximum =
      session.edge === "ends_at"
        ? dayEnd
        : Math.min(dayEnd, Date.parse(session.event.ends_at) - 60_000);
    const next = {
      ...session,
      value: Math.max(minimum, Math.min(maximum, value)),
    };
    active.current = next;
    setPreview(next);
  }
  async function commit() {
    const session = active.current;
    active.current = null;
    if (!session || session.value === Date.parse(session.event[session.edge])) {
      setPreview(null);
      return;
    }
    setCommitting(true);
    try {
      await onResize(
        session.event,
        session.edge,
        new Date(session.value).toISOString(),
      );
    } finally {
      setPreview(null);
      setCommitting(false);
    }
  }
  function beginResize(input: PointerEvent<HTMLButtonElement>) {
    if (input.button !== 0 || disabled || committing) return;
    const edge = input.currentTarget.dataset.edge as Edge;
    input.preventDefault();
    input.stopPropagation();
    input.currentTarget.focus();
    input.currentTarget.setPointerCapture(input.pointerId);
    const scroll =
      input.currentTarget.closest(".calendar-scroll")?.scrollTop ?? 0;
    const session = {
      event,
      edge,
      value: Date.parse(event[edge]),
      y: input.clientY,
      scroll,
      pointer: true,
    };
    active.current = session;
    setPreview(session);
  }
  function moveResize(input: PointerEvent<HTMLButtonElement>) {
    const session = active.current;
    if (!session?.pointer) return;
    const scroll =
      input.currentTarget.closest(".calendar-scroll")?.scrollTop ?? 0;
    const delta =
      Math.round(
        (((input.clientY - session.y + scroll - session.scroll) / hourHeight) *
          60) /
          15,
      ) * step;
    change(session, Date.parse(session.event[session.edge]) + delta);
  }
  function endResize(input: PointerEvent<HTMLButtonElement>) {
    input.stopPropagation();
    if (active.current?.pointer) void commit();
  }
  function lostCapture() {
    if (active.current?.pointer) cancel();
  }
  function blurHandle() {
    if (active.current && !active.current.pointer) cancel();
  }
  function resizeKeys(input: KeyboardEvent<HTMLButtonElement>) {
    if (input.key === "Escape") {
      input.preventDefault();
      cancel();
      return;
    }
    if (input.key === "Enter") {
      input.preventDefault();
      void commit();
      return;
    }
    if (!["ArrowUp", "ArrowDown"].includes(input.key)) return;
    input.preventDefault();
    const edge = input.currentTarget.dataset.edge as Edge;
    const session = active.current ?? {
      event,
      edge,
      value: Date.parse(event[edge]),
      y: 0,
      scroll: 0,
      pointer: false,
    };
    change(session, session.value + (input.key === "ArrowDown" ? step : -step));
  }
  return (
    <div
      className={`event-card ${event.source === "official" ? "official-event" : "personal-event"} ${event.skipped ? "skipped-event" : ""} ${preview ? "resizing-event" : ""}`}
      style={{
        top: `${((clippedStart - dayStart) / 3_600_000) * hourHeight}px`,
        height: `${height}px`,
        left: `calc(${(lane * 100) / count}% + 3px)`,
        right: `calc(${((count - lane - 1) * 100) / count}% + 3px)`,
      }}
    >
      <button
        type="button"
        className="event-card-open"
        disabled={committing}
        onClick={() => {
          if (!active.current) onOpen();
        }}
        title={`${event.title}${event.location ? ` · ${event.location}` : ""}`}
        aria-label={`${event.title}, ${prettyDate(new Date(event.starts_at), timeZone, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })} — ${prettyDate(new Date(event.ends_at), timeZone, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })}`}
      >
        <span className="event-time">
          {clippedStart > start && "↪ "}
          {prettyDate(new Date(clippedStart), timeZone, {
            hour: "2-digit",
            minute: "2-digit",
          })}{" "}
          —{" "}
          {prettyDate(new Date(clippedEnd), timeZone, {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        <strong>{event.title}</strong>
        {height >= 76 && (event.location || event.subject) && (
          <span className="event-location">
            {event.location || event.subject}
          </span>
        )}
      </button>
      {event.source === "personal" &&
        (["starts_at", "ends_at"] as const)
          .filter((edge) =>
            edge === "starts_at"
              ? start >= dayStart &&
                (height >= 24 || preview?.edge === "starts_at")
              : end <= dayEnd,
          )
          .map((edge) => {
            const value = edge === "starts_at" ? start : end;
            return (
              <button
                key={edge}
                type="button"
                role="slider"
                className={`event-resize-handle resize-${edge}`}
                aria-label={`${edge === "starts_at" ? "Изменить начало" : "Изменить окончание"}: ${event.title}`}
                aria-orientation="vertical"
                aria-valuemin={
                  edge === "starts_at"
                    ? dayStart
                    : Math.max(dayStart, start + 60_000)
                }
                aria-valuemax={
                  edge === "ends_at" ? dayEnd : Math.min(dayEnd, end - 60_000)
                }
                aria-valuenow={value}
                aria-valuetext={format(value)}
                aria-describedby="calendar-resize-help"
                disabled={disabled || committing}
                onClick={(input) => {
                  input.preventDefault();
                  input.stopPropagation();
                }}
                data-edge={edge}
                onPointerDown={beginResize}
                onPointerMove={moveResize}
                onPointerUp={endResize}
                onPointerCancel={cancel}
                onLostPointerCapture={lostCapture}
                onBlur={blurHandle}
                onKeyDown={resizeKeys}
              >
                <span aria-hidden="true" />
              </button>
            );
          })}
      {preview && (
        <span className="sr-only" role="status">
          {format(start)} — {format(end)}. Enter — сохранить, Escape — отменить.
        </span>
      )}
    </div>
  );
}
