"use client";

import { useState, type CSSProperties } from "react";
import { Modal } from "@/shared/ui";
import { CalendarMonth } from "./calendar-month";
import { dateKey, dateTimeLocal, localInstants, prettyDate, resolveLocalTime, shiftDate } from "./calendar-time";

type Range = { start: string; end: string; startInstant: string; endInstant: string };
export function EventTimeStrip({ value, timeZone, originalStart, originalEnd, onChange }: {
  value: Range; timeZone: string; originalStart?: string; originalEnd?: string;
  onChange: (value: Range) => void;
}) {
  const [draft, setDraft] = useState(value);
  const [active, setActive] = useState<"start" | "end">("start");
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({});
  const [error, setError] = useState("");
  const current = draft[active];
  const day = current.slice(0, 10);
  const clock = current.slice(11);
  const options = localInstants(`${day}T${normalize(clock) ?? clock}`, timeZone, active === "start" ? originalStart : originalEnd);
  const choice = active === "start" ? draft.startInstant : draft.endInstant;
  function setCurrent(next: string) {
    setError("");
    setDraft(previous => ({ ...previous, [active]: next, [active === "start" ? "startInstant" : "endInstant"]: "" }));
  }
  function normalize(input: string) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(input) ?? /^(\d{1,2})(\d{2})$/.exec(input);
    return match && +match[1] < 24 && +match[2] < 60 ? `${match[1].padStart(2, "0")}:${match[2]}` : null;
  }
  function adjust(minutes: number) {
    const normalized = normalize(clock);
    if (!normalized) { setError("Введи время в формате 09:37."); return; }
    const date = new Date(`${day}T${normalized}:00Z`);
    date.setUTCMinutes(date.getUTCMinutes() + minutes);
    setCurrent(date.toISOString().slice(0, 16));
  }
  function duration(minutes: number) {
    try {
      const start = resolveLocalTime(draft.start, timeZone, draft.startInstant, originalStart);
      const end = new Date(Date.parse(start) + minutes * 60_000);
      setDraft(previous => ({ ...previous, end: dateTimeLocal(end, timeZone), endInstant: end.toISOString() }));
      setError("");
    } catch (cause) { setError((cause as Error).message); }
  }
  function apply() {
    try {
      const normalized = normalize(clock);
      if (!normalized) throw new Error("Введи время в формате 09:37.");
      const next = { ...draft, [active]: `${day}T${normalized}` };
      const start = resolveLocalTime(next.start, timeZone, next.startInstant, originalStart);
      const end = resolveLocalTime(next.end, timeZone, next.endInstant, originalEnd);
      if (Date.parse(end) <= Date.parse(start)) throw new Error("Окончание должно быть позже начала. Выбери следующий день или другое время.");
      onChange({ ...next, startInstant: start, endInstant: end });
      setOpen(false);
    } catch (cause) { setError((cause as Error).message); }
  }
  const label = (wall: string) => `${prettyDate(wall.slice(0, 10), timeZone, { day: "numeric", month: "short" })} · ${wall.slice(11)}`;
  let durationLabel = "Выбери начало и окончание";
  try {
    const start = resolveLocalTime(draft.start, timeZone, draft.startInstant, originalStart);
    const end = resolveLocalTime(draft.end, timeZone, draft.endInstant, originalEnd);
    const minutes = (Date.parse(end) - Date.parse(start)) / 60_000;
    if (minutes > 0) durationLabel = `${Math.round(minutes)} мин · фактическая длительность`;
  } catch { /* Incomplete local values remain editable until Apply. */ }
  return <div className="event-time-strip">
    <span className="field-label">Дата и время</span>
    <div className="time-strip-triggers">
      {(["start", "end"] as const).map(endpoint => <button type="button" key={endpoint}
        aria-label={endpoint === "start" ? "Выбрать начало" : "Выбрать окончание"}
        aria-haspopup="dialog" onClick={event => {
          const box = event.currentTarget.getBoundingClientRect();
          const top = Math.max(8, Math.min(box.bottom + 8, window.innerHeight - 800));
          setPosition({ left: Math.max(8, Math.min(box.left, window.innerWidth - 408)), top, maxHeight: window.innerHeight - top - 8 });
          setDraft(value); setActive(endpoint); setError(""); setOpen(true);
        }}><small>{endpoint === "start" ? "Начало" : "Окончание"}</small><strong>{label(value[endpoint])}</strong></button>)}
    </div>
    {open && <Modal title="Дата и время события" className="temporal-dialog" style={position} onClose={() => setOpen(false)}>
      <div className="temporal-editor" onKeyDown={event => {
        if (event.key === "Enter" && event.target instanceof HTMLInputElement && !event.nativeEvent.isComposing) { event.preventDefault(); apply(); }
      }}>
        <h2>Дата и время</h2>
        <div className="temporal-endpoints" role="group" aria-label="Часть интервала">
          <button type="button" aria-pressed={active === "start"} onClick={() => setActive("start")}>Начало</button>
          <button type="button" aria-pressed={active === "end"} onClick={() => setActive("end")}>Окончание</button>
        </div>
        <CalendarMonth key={day.slice(0, 7)} selected={day} timeZone={timeZone} onSelect={next => setCurrent(`${next}T${clock}`)} />
        <div className="temporal-date-actions">
          <button type="button" onClick={() => setCurrent(`${dateKey(new Date(), timeZone)}T${clock}`)}>Сегодня</button>
          <button type="button" onClick={() => setCurrent(`${shiftDate(dateKey(new Date(), timeZone), 1)}T${clock}`)}>Завтра</button>
          {active === "end" && <button type="button" onClick={() => setCurrent(`${shiftDate(draft.start.slice(0, 10), 1)}T${clock}`)}>Следующий день</button>}
        </div>
        <div className="clock-stepper">
          <div><button type="button" aria-label="На час позже" onClick={() => adjust(60)}>+</button><span>Часы</span><button type="button" aria-label="На час раньше" onClick={() => adjust(-60)}>−</button></div>
          <label>Время<input type="text" inputMode="numeric" autoComplete="off" aria-label="Точное время" aria-describedby="temporal-clock-help" value={clock} maxLength={5}
            onChange={event => setCurrent(`${day}T${event.target.value}`)} onBlur={() => { const normalized = normalize(clock); if (normalized && normalized !== clock) setCurrent(`${day}T${normalized}`); }} /></label>
          <div><button type="button" aria-label="На минуту позже" onClick={() => adjust(1)}>+</button><span>Минуты</span><button type="button" aria-label="На минуту раньше" onClick={() => adjust(-1)}>−</button></div>
        </div>
        <p id="temporal-clock-help" className="temporal-entry-hint">Можно набрать 0937 → 09:37</p>
        <div className="minute-presets" role="group" aria-label="Быстрый выбор минут">
          {["00", "15", "30", "45"].map(minute => <button type="button" key={minute} onClick={() => setCurrent(`${day}T${clock.split(":")[0].padStart(2, "0")}:${minute}`)}>{minute}</button>)}
          <button type="button" onClick={() => adjust(-5)}>−5 мин</button><button type="button" onClick={() => adjust(5)}>+5 мин</button>
        </div>
        {options.length === 0 && <p className="temporal-error">Время неполное или не существует в этом часовом поясе.</p>}
        {options.length > 1 && <label className="field-label">Повторяющийся час<select aria-label="Смещение выбранного времени" value={options.includes(choice) ? choice : ""} onChange={event => setDraft(previous => ({ ...previous, [active === "start" ? "startInstant" : "endInstant"]: event.target.value }))}>
          <option value="" disabled>Выбери смещение</option>{options.map(instant => <option key={instant} value={instant}>{prettyDate(new Date(instant), timeZone, { hour: "2-digit", minute: "2-digit", timeZoneName: "shortOffset" })}</option>)}
        </select></label>}
        <div className="temporal-duration"><span>{durationLabel}</span><div role="group" aria-label="Длительность события">{[30, 60, 90].map(minutes => <button type="button" key={minutes} onClick={() => duration(minutes)}>{minutes} мин</button>)}</div></div>
        <p className="temporal-zone">{prettyDate(day, timeZone, { day: "numeric", month: "long", year: "numeric" })} · {timeZone}{options.length === 1 ? ` · ${prettyDate(new Date(options[0]), timeZone, { timeZoneName: "shortOffset" }).split(", ").at(-1)}` : ""}</p>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="temporal-actions"><button type="button" className="secondary-button" onClick={() => setOpen(false)}>Отмена</button><button type="button" className="primary-button" onClick={apply}>Применить</button></div>
      </div>
    </Modal>}
  </div>;
}
