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
  onCreate,
}: {
  dayStart: number;
  dayEnd: number;
  hourHeight: number;
  timeZone: string;
  disabled: boolean;
  onCreate: (start: string, end: string) => void;
}) {
  const [preview, setPreview] = useState<[number, number] | null>(null);
  const active = useRef<{
    anchor: number;
    current: number;
    x: number;
    y: number;
    touch: boolean;
  } | null>(null);
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
    Math.max(dayStart, Math.min(dayEnd - step, value));
  const defaultRange = (value: number): [number, number] => [
    clamp(value),
    Math.min(dayEnd, clamp(value) + 3_600_000),
  ];

  function position(event: PointerEvent<HTMLButtonElement>, round = false) {
    const offset =
      ((event.clientY - event.currentTarget.getBoundingClientRect().top) /
        hourHeight) *
      3_600_000;
    return Math.max(
      dayStart,
      Math.min(
        dayEnd,
        dayStart +
          (round ? Math.round(offset / step) : Math.floor(offset / step)) *
            step,
      ),
    );
  }
  function cancel() {
    active.current = null;
    setPreview(null);
  }
  function begin(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0 || disabled) return;
    const anchor = clamp(position(event));
    active.current = {
      anchor,
      current: anchor,
      x: event.clientX,
      y: event.clientY,
      touch: event.pointerType === "touch",
    };
    setPreview(defaultRange(anchor));
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    const gesture = active.current;
    if (!gesture) {
      if (event.pointerType === "mouse" && event.buttons === 0)
        setPreview(defaultRange(position(event)));
      return;
    }
    if (gesture.touch) {
      // Keep touch scrolling native; only a stationary tap creates a draft.
      if (Math.hypot(event.clientX - gesture.x, event.clientY - gesture.y) > 8)
        cancel();
      return;
    }
    gesture.current = position(event, true);
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
    onCreate(
      new Date(range[0]).toISOString(),
      new Date(range[1]).toISOString(),
    );
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
    const range = preview ?? defaultRange(dayStart + 10 * 3_600_000);
    const delta = event.key === "ArrowUp" ? -step : step;
    setPreview(
      event.shiftKey
        ? [
            range[0],
            Math.max(range[0] + step, Math.min(dayEnd, range[1] + delta)),
          ]
        : defaultRange(range[0] + delta),
    );
  }
  function createFromKeyboard() {
    const range = preview ?? defaultRange(dayStart + 10 * 3_600_000);
    cancel();
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
      onLostPointerCapture={cancel}
      onPointerLeave={() => {
        if (!active.current) setPreview(null);
      }}
      onFocus={() => setPreview(defaultRange(dayStart + 10 * 3_600_000))}
      onBlur={cancel}
      onKeyDown={keyboard}
      onClick={(event) => {
        if (event.detail === 0) createFromKeyboard();
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
