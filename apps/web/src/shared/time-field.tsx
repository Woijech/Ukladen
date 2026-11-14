"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Modal } from "./ui";

const twoDigits = (value: number) => String(value).padStart(2, "0");

function TimeColumn({ label, count, value, onChange }: {
  label: string; count: number; value: number; onChange: (value: number) => void;
}) {
  const id = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [value]);
  return <div className="time-column">
    <span id={`${id}-label`}>{label}</span>
    <div ref={ref} role="listbox" aria-labelledby={`${id}-label`} tabIndex={0}
      aria-activedescendant={`${id}-${value}`} onKeyDown={event => {
        const next = event.key === "ArrowDown" ? (value + 1) % count
          : event.key === "ArrowUp" ? (value + count - 1) % count
            : event.key === "Home" ? 0 : event.key === "End" ? count - 1 : null;
        if (next !== null) { event.preventDefault(); onChange(next); }
      }}>
      {Array.from({ length: count }, (_, index) => <div role="option" id={`${id}-${index}`}
        key={index} aria-selected={value === index} onClick={() => { ref.current?.focus(); onChange(index); }}>
        {twoDigits(index)}
      </div>)}
    </div>
  </div>;
}

export function TimeField({ label, value, onChange, disabled = false }: {
  label: string; value: string; onChange: (value: string) => void; disabled?: boolean;
}) {
  const id = useId();
  const [draft, setDraft] = useState([9, 0]);
  const [open, setOpen] = useState(false);
  return <div className="time-field field-label">
    <label htmlFor={id}>{label}</label>
    <div className="time-field-control">
      <input id={id} type="time" required value={value} disabled={disabled}
        onChange={event => onChange(event.target.value)} />
      <button type="button" className="time-field-trigger" disabled={disabled}
        aria-label={`Выбрать время: ${label}`} aria-haspopup="dialog" onClick={() => {
          setDraft(/^\d{2}:\d{2}$/.test(value) ? value.split(":").map(Number) : [9, 0]);
          setOpen(true);
        }}>
        <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M12 6v6l4 2" /></svg>
      </button>
    </div>
    {open && <Modal title={`Выбрать время: ${label}`} onClose={() => setOpen(false)}>
      <div className="time-picker">
        <h2>{label}</h2>
        <p className="muted">24-часовой формат. Часовой пояс остаётся прежним.</p>
        <output className="time-preview" aria-live="polite">{draft.map(twoDigits).join(":")}</output>
        <div className="time-columns">
          <TimeColumn label="Часы" count={24} value={draft[0]} onChange={hour => setDraft([hour, draft[1]])} />
          <TimeColumn label="Минуты" count={60} value={draft[1]} onChange={minute => setDraft([draft[0], minute])} />
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={() => setOpen(false)}>Отмена</button>
          <button type="button" className="primary-button" onClick={() => {
            onChange(draft.map(twoDigits).join(":")); setOpen(false);
          }}>Выбрать время</button>
        </div>
      </div>
    </Modal>}
  </div>;
}
