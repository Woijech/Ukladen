"use client";

import { useEffect, useRef, useState } from "react";
import { dateKey, prettyDate, shiftDate, startOfWeek } from "./calendar-time";

export function CalendarMonth({ selected, timeZone, onSelect }: {
  selected: string; timeZone: string; onSelect: (day: string) => void;
}) {
  const [month, setMonth] = useState(selected.slice(0, 7) + "-01");
  const [focused, setFocused] = useState<string | null>(null);
  const grid = useRef<HTMLDivElement>(null);
  const today = dateKey(new Date(), timeZone);
  const first = startOfWeek(month);
  function changeMonth(amount: number) {
    const date = new Date(`${month}T12:00:00Z`);
    date.setUTCMonth(date.getUTCMonth() + amount);
    setMonth(date.toISOString().slice(0, 10));
  }
  useEffect(() => {
    if (focused) grid.current?.querySelector<HTMLButtonElement>(`[data-day="${focused}"]`)?.focus();
  }, [focused]);
  return <div className="calendar-month">
    <div className="month-heading">
      <button type="button" aria-label="Предыдущий месяц" onClick={() => changeMonth(-1)}>‹</button>
      <strong aria-live="polite">{prettyDate(month, timeZone, { month: "long", year: "numeric" })}</strong>
      <button type="button" aria-label="Следующий месяц" onClick={() => changeMonth(1)}>›</button>
    </div>
    <div className="month-weekdays" aria-hidden="true">{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(day => <span key={day}>{day}</span>)}</div>
    <div className="month-days" ref={grid} role="group" aria-label="Выбрать дату">
      {Array.from({ length: 42 }, (_, i) => shiftDate(first, i)).map(day => <button
        type="button" key={day} data-day={day} aria-label={prettyDate(day, timeZone, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
        aria-current={day === today ? "date" : undefined} aria-pressed={selected === day}
        className={day.slice(0, 7) !== month.slice(0, 7) ? "outside-month" : undefined}
        tabIndex={day === (focused ?? (selected.slice(0, 7) === month.slice(0, 7) ? selected : month)) ? 0 : -1}
        onClick={() => onSelect(day)} onKeyDown={event => {
          let next: string | null = null;
          if (event.key === "ArrowLeft") next = shiftDate(day, -1);
          if (event.key === "ArrowRight") next = shiftDate(day, 1);
          if (event.key === "ArrowUp") next = shiftDate(day, -7);
          if (event.key === "ArrowDown") next = shiftDate(day, 7);
          if (event.key === "Home") next = startOfWeek(day);
          if (event.key === "End") next = shiftDate(startOfWeek(day), 6);
          if (event.key === "PageUp" || event.key === "PageDown") {
            const date = new Date(`${day.slice(0, 7)}-01T12:00:00Z`);
            date.setUTCMonth(date.getUTCMonth() + (event.key === "PageDown" ? 1 : -1));
            next = date.toISOString().slice(0, 10);
          }
          if (next) { event.preventDefault(); setMonth(next.slice(0, 7) + "-01"); setFocused(next); }
        }}>{Number(day.slice(-2))}</button>)}
    </div>
  </div>;
}
