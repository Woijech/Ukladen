"use client";

import {
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent,
  type KeyboardEvent,
} from "react";

const step = 15 * 60_000;

export function CalendarSelection({
  dayStart,
  dayEnd,
  hourHeight,
  timeZone,
  disabled,
  occupied = [],
  onCreate,
}: {
  dayStart: number;
  dayEnd: number;
  hourHeight: number;
  timeZone: string;
  disabled: boolean;
  occupied?: { starts_at: string; ends_at: string }[];
  onCreate: (start: string, end: string) => void;
}) {
  const [preview, setPreview] = useState<[number, number] | null>(null);
  const active = useRef<{
    anchor: number;
    current: number;
    x: number;
    y: number;
    touch: boolean;
    bounds: [number, number];
  } | null>(null);
  const pendingRange = useRef<[number, number] | null>(null);
  const keyboardPreview = useRef<HTMLSpanElement>(null);
  const scrollPreview = useRef(false);
  useLayoutEffect(() => {
    if (scrollPreview.current) {
      keyboardPreview.current?.scrollIntoView({
        block: "nearest",
        inline: "nearest",
      });
      scrollPreview.current = false;
    }
  }, [preview]);
  const clock = (value: number) =>
    new Intl.DateTimeFormat("ru", {
      timeZone,
      hour: "2-digit",
      minute: "2-digit",
      timeZoneName: "shortOffset",
    }).format(new Date(value));
  const label = new Intl.DateTimeFormat("ru", {
    timeZone,
    day: "numeric",
    month: "long",
  }).format(new Date(dayStart));
  const clamp = (value: number) =>
    Math.max(dayStart, Math.min(dayEnd - 60_000, value));
  function freeWindow(value: number): [number, number] | null {
    let lower = dayStart;
    let upper = dayEnd;
    for (const event of occupied) {
      const start = Date.parse(event.starts_at);
      const end = Date.parse(event.ends_at);
      if (value >= start && value < end) return null;
      if (end <= value) lower = Math.max(lower, end);
      if (start > value) upper = Math.min(upper, start);
    }
    return upper > lower ? [lower, upper] : null;
  }
  function defaultRange(value: number): [number, number] | null {
    const start = clamp(value);
    const bounds = freeWindow(start);
    return bounds ? [start, Math.min(bounds[1], start + 3_600_000)] : null;
  }
  function keyboardRange(value = dayStart + 10 * 3_600_000, direction = 1) {
    for (let point = value; point >= dayStart && point < dayEnd; point += direction * step) {
      const range = defaultRange(point);
      if (range) return range;
    }
    return null;
  }
  function initialRange() {
    return keyboardRange() ?? keyboardRange(dayStart + 10 * 3_600_000 - step, -1);
  }
  function position(event: PointerEvent<HTMLButtonElement>, snap: "floor" | "round" | "none" = "floor") {
    const offset = ((event.clientY - event.currentTarget.getBoundingClientRect().top) / hourHeight) * 3_600_000;
    const delta = snap === "none" ? offset : (snap === "round" ? Math.round(offset / step) : Math.floor(offset / step)) * step;
    return Math.max(dayStart, Math.min(dayEnd, dayStart + delta));
  }
  function pointerRange(event: PointerEvent<HTMLButtonElement>) {
    const bounds = freeWindow(position(event, "none"));
    return bounds ? defaultRange(Math.max(bounds[0], position(event))) : null;
  }
  function cancel() {
    active.current = null;
    pendingRange.current = null;
    setPreview(null);
  }
  function begin(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || disabled) return;
    const range = pointerRange(event);
    if (!range) { cancel(); return; }
    const anchor = range[0];
    active.current = {
      anchor,
      current: anchor,
      x: event.clientX,
      y: event.clientY,
      touch: event.pointerType === "touch",
      bounds: freeWindow(anchor)!,
    };
    setPreview(range);
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    const gesture = active.current;
    if (!gesture) {
      if (event.pointerType === "mouse" && event.buttons === 0)
        setPreview(pointerRange(event));
      return;
    }
    if (gesture.touch) {
      // Keep touch scrolling native; only a stationary tap creates a draft.
      if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 8)
        cancel();
      return;
    }
    gesture.current = Math.max(gesture.bounds[0], Math.min(gesture.bounds[1], position(event, "round")));
    setPreview(
      gesture.current === gesture.anchor
        ? defaultRange(gesture.anchor)
        : [
            Math.min(gesture.anchor, gesture.current),
            Math.max(gesture.anchor, gesture.current),
          ],
    );
  }
  function finish() {
    const gesture = active.current;
    if (!gesture) return;
    const range =
      gesture.current === gesture.anchor
        ? defaultRange(gesture.anchor)
        : [
            Math.min(gesture.anchor, gesture.current),
            Math.max(gesture.anchor, gesture.current),
          ];
    cancel();
    if (range) pendingRange.current = [range[0], range[1]];
  }
  function keyboard(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      cancel();
      return;
    }
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    scrollPreview.current = true;
    const range = preview ?? initialRange();
    if (!range) return;
    const delta = event.key === "ArrowUp" ? -step : step;
    const bounds = freeWindow(range[0]);
    if (!bounds) { setPreview(keyboardRange(range[0], delta > 0 ? 1 : -1)); return; }
    setPreview(
      event.shiftKey
        ? [
            range[0],
            Math.max(range[0] + Math.min(step, bounds[1] - range[0]), Math.min(bounds[1], range[1] + delta)),
          ]
        : keyboardRange(range[0] + delta, delta > 0 ? 1 : -1) ?? range,
    );
  }
  function createFromKeyboard() {
    const range = preview ?? initialRange();
    cancel();
    if (!range) return;
    onCreate(
      new Date(range[0]).toISOString(),
      new Date(range[1]).toISOString(),
    );
  }
  return (
    <button
      type="button"
      className="calendar-selection"
      disabled={disabled}
      aria-label={`Создать событие · ${label}${preview ? ` · ${clock(preview[0])} – ${clock(preview[1])}` : ""}`}
      aria-describedby="calendar-create-help"
      onPointerDown={begin}
      onPointerMove={move}
      onPointerUp={finish}
      onPointerCancel={cancel}
      onLostPointerCapture={() => { if (active.current) cancel(); }}
      onPointerLeave={() => {
        if (!active.current) setPreview(null);
      }}
      onFocus={() => setPreview(initialRange())}
      onBlur={cancel}
      onKeyDown={keyboard}
      onClick={(event) => {
        if (event.detail === 0) createFromKeyboard();
        else if (pendingRange.current) {
          const [start, end] = pendingRange.current;
          pendingRange.current = null;
          // Open after the completed click so touch cannot activate the new dialog underneath.
          onCreate(new Date(start).toISOString(), new Date(end).toISOString());
        }
      }}
    >
      {preview && (
        <span
          ref={keyboardPreview}
          className="calendar-selection-preview"
          style={{
            top: ((preview[0] - dayStart) / 3_600_000) * hourHeight,
            height: ((preview[1] - preview[0]) / 3_600_000) * hourHeight,
          }}
        >
          <span>
            + {clock(preview[0])} – {clock(preview[1])}
          </span>
        </span>
      )}
    </button>
  );
}
