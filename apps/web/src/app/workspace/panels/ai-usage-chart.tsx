"use client";

import { useState } from "react";

export type DailyUsage = { label: string; runs: number; input_tokens: number | null; output_tokens: number | null; fake?: boolean };
const count = (value: number | null) => value === null ? "неизвестно" : value.toLocaleString("ru");
export function UsageChart({ daily, from, to }: { daily: DailyUsage[]; from: string; to: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const rows: DailyUsage[] = [];
  for (let day = from; day <= to && rows.length < 31;) {
    rows.push(daily.find(row => row.label === day && !row.fake) ?? { label: day, runs: 0, input_tokens: 0, output_tokens: 0 });
    const next = new Date(`${day}T12:00:00Z`); next.setUTCDate(next.getUTCDate() + 1); day = next.toISOString().slice(0, 10);
  }
  const max = Math.max(1, ...rows.map(row => row.runs));
  const current = rows.find(row => row.label === selected);
  const date = (value: string) => new Intl.DateTimeFormat("ru", { timeZone: "Europe/Minsk", day: "numeric", month: "short" }).format(new Date(`${value}T12:00:00Z`));
  return <section className="usage-chart" aria-label="Использование по дням">
    <div className="panel-toolbar"><h3>Использование по дням</h3><span className="muted">Запросы</span></div>
    <p className="usage-chart-detail" aria-live="polite">{current ? `${date(current.label)} · ${current.runs} запросов · вход: ${count(current.input_tokens)} · выход: ${count(current.output_tokens)}` : "Выбери день, чтобы увидеть подробности"}</p>
    <div className="usage-bars" role="group" aria-label="График запросов">
      {rows.map(row => <button type="button" key={row.label} className={`usage-day ${selected === row.label ? "is-selected" : ""}`} aria-pressed={selected === row.label}
        aria-label={`${date(row.label)}: ${row.runs} запросов, вход ${count(row.input_tokens)}, выход ${count(row.output_tokens)}`}
        onMouseEnter={() => setSelected(row.label)} onFocus={() => setSelected(row.label)} onClick={() => setSelected(row.label)}>
        <span className="usage-bar" style={{ height: `${row.runs ? Math.max(3, row.runs / max * 100) : 1}%` }} />
      </button>)}
    </div>
    <div className="usage-chart-axis"><span>{date(from)}</span><span>{date(to)}</span></div>
    {!rows.some(row => row.runs) && <p className="muted">За этот период запросов нет.</p>}
  </section>;
}
