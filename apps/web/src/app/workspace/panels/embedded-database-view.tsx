"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { requestJson } from "@/shared/api";
import { Modal, Pager, QueryState } from "@/shared/ui";
import { dateKey, shiftDate, startOfWeek } from "../calendar-time";
import { DatabaseRecordCards, groupRecords } from "./database-record-cards";
import { displayValue, type Property, type RecordItem } from "./databases";
import type { Block } from "./notes";
import "./embedded-database-view.css";

type ViewBlock = Extract<Block, { type: "database_view" }>;
type View = { id: string; database_id: string; name: string; layout: "table" | "list" | "board" | "calendar"; query: { group_by?: string | null }; calendar_layout: "day" | "week" | "month" | null };
type Table = { items: RecordItem[]; properties: Property[]; total: number };
const pageSize = 20;

export function DatabaseViewPicker({ onClose, onSelect }: { onClose: () => void; onSelect: (view: View) => void }) {
  const [database, setDatabase] = useState("");
  const [databaseOffset, setDatabaseOffset] = useState(0);
  const [viewOffset, setViewOffset] = useState(0);
  const databases = useQuery({ queryKey: ["embed-database-options", databaseOffset],
    queryFn: ({ signal }) => requestJson<{ items: { id: string; name: string }[] }>(`/api/v1/workspace/databases?limit=50&offset=${databaseOffset}`, { signal }) });
  const views = useQuery({ queryKey: ["embed-view-options", database, viewOffset], enabled: !!database,
    queryFn: ({ signal }) => requestJson<{ items: View[] }>(`/api/v1/workspace/databases/${database}/views?limit=50&offset=${viewOffset}`, { signal }) });
  return <Modal title="Вставить вид базы" onClose={onClose}>
    <h2>Записи прямо в странице</h2><p className="muted">Вставим ссылку на сохранённый вид. Записи и страницы останутся в своей базе.</p>
    <label htmlFor="embed-database">База данных</label><select id="embed-database" value={database} onChange={event => { setDatabase(event.target.value); setViewOffset(0); }}><option value="">Выбрать базу…</option>{database && !databases.data?.items.some(item => item.id === database) && <option value={database}>Выбранная база</option>}{databases.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <QueryState pending={databases.isPending} error={databases.error} retry={() => void databases.refetch()} />
    {databases.data && <Pager offset={databaseOffset} count={databases.data.items.length} onChange={setDatabaseOffset} />}
    {database && <><h3>Сохранённые виды</h3><QueryState pending={views.isPending} error={views.error} retry={() => void views.refetch()} />
      <div className="embed-view-options">{views.data?.items.map(view => <button type="button" key={view.id} onClick={() => onSelect(view)}><strong>{view.name}</strong><span>{{ table: "Таблица", list: "Список", board: "Доска", calendar: "Календарь" }[view.layout]}</span></button>)}</div>
      {views.data?.items.length === 0 && <p className="muted">Сначала сохрани вид в этой базе, затем выбери его здесь.</p>}
      {views.data && <Pager offset={viewOffset} count={views.data.items.length} onChange={setViewOffset} />}
    </>}
  </Modal>;
}

function EmbeddedCalendar({ base, view, timeZone, onOpenPage }: { base: string; view: View; timeZone: string; onOpenPage?: (id: string) => void }) {
  const [cursor, setCursor] = useState(() => dateKey(new Date(), timeZone));
  const [offset, setOffset] = useState(0);
  const scale = view.calendar_layout ?? "week";
  const start = scale === "month" ? cursor.slice(0, 7) + "-01" : scale === "week" ? startOfWeek(cursor) : cursor;
  const monthEnd = new Date(`${start}T12:00:00Z`);
  monthEnd.setUTCMonth(monthEnd.getUTCMonth() + 1, 0);
  const end = scale === "month" ? monthEnd.toISOString().slice(0, 10) : shiftDate(start, scale === "week" ? 6 : 0);
  const entries = useQuery({ queryKey: ["embedded-view-dates", view.id, start, end], retry: false,
    queryFn: ({ signal }) => requestJson<{ entries: { id: string; page_id: string; title: string; date: { kind: "date" | "datetime"; start: string } }[] }>(`${base}/entries?date_from=${start}&date_to=${end}`, { signal }) });
  function move(direction: number) { setOffset(0); if (scale === "month") { const day = new Date(`${start}T12:00:00Z`); day.setUTCMonth(day.getUTCMonth() + direction); setCursor(day.toISOString().slice(0, 10)); } else setCursor(shiftDate(start, direction * (scale === "week" ? 7 : 1))); }
  return <>
    <div className="embedded-view-toolbar"><button type="button" className="text-action" onClick={() => move(-1)}>← Раньше</button><span>{start}{start !== end ? ` — ${end}` : ""}</span><button type="button" className="text-action" onClick={() => move(1)}>Позже →</button></div>
    <QueryState pending={entries.isPending} error={entries.error} retry={() => void entries.refetch()} />
    <div className="embedded-calendar-entries">{entries.data?.entries.slice(offset, offset + pageSize).map(entry => <div key={entry.id}><time>{entry.date.kind === "date" ? entry.date.start : new Intl.DateTimeFormat("ru", { timeZone, dateStyle: "short", timeStyle: "short" }).format(new Date(entry.date.start))}</time><button type="button" className="table-page-link" disabled={!onOpenPage} onClick={() => onOpenPage?.(entry.page_id)}>{entry.title}</button></div>)}</div>
    {entries.data?.entries.length === 0 && <p className="muted">В этом периоде нет записей.</p>}
    {entries.data && <Pager size={pageSize} offset={offset} count={entries.data.entries.slice(offset, offset + pageSize).length} onChange={setOffset} />}
  </>;
}

function EmbeddedRecordsTable({ table, groupBy, timeZone, onOpenPage }: { table: Table; groupBy?: string | null; timeZone: string; onOpenPage?: (id: string) => void }) {
  const groups = groupRecords(table.items, table.properties.find(property => property.id === groupBy)).filter(group => group.items.length || !group.name);
  return <>{groups.map(group => <div key={group.id}>{group.name && <h4>{group.name} · {group.items.length} на этой странице</h4>}
    <div className="table-scroll"><table className="records-table"><thead><tr><th>Название</th>{table.properties.map(property => <th key={property.id}>{property.name}</th>)}</tr></thead><tbody>{group.items.map(item => <tr key={item.record.id}><td><button type="button" className="table-page-link" disabled={!onOpenPage} onClick={() => onOpenPage?.(item.page.id)}>{item.page.title}</button></td>{table.properties.map(property => <td key={property.id}>{displayValue(item.record.values[property.id], property, timeZone, item)}</td>)}</tr>)}</tbody></table></div>
  </div>)}</>;
}

export function EmbeddedDatabaseView({ block, timeZone, onOpenPage, onOpenView }: { block: ViewBlock; timeZone: string; onOpenPage?: (id: string) => void; onOpenView?: (databaseId: string, viewId: string) => void }) {
  const [offset, setOffset] = useState(0);
  const base = `/api/v1/workspace/databases/${block.database_id}/views/${block.view_id}`;
  const view = useQuery({ queryKey: ["embedded-view", block.database_id, block.view_id], retry: false,
    queryFn: ({ signal }) => requestJson<View>(base, { signal }) });
  const records = useQuery({ queryKey: ["embedded-view-records", block.view_id, offset, view.data?.layout], enabled: !!view.data && view.data.layout !== "calendar", retry: false,
    queryFn: ({ signal }) => requestJson<Table>(`${base}/records?limit=${pageSize}&offset=${offset}`, { signal }) });
  return <section className="embedded-database-view" aria-label={`Встроенный вид: ${block.text || view.data?.name || "База данных"}`}>
    <header><span>{view.data ? `${view.data.name} · актуальные записи` : "Сохранённый вид"}</span>{onOpenView && <button type="button" className="text-action" onClick={() => onOpenView(block.database_id, block.view_id)}>Открыть в базе ↗</button>}</header>
    <QueryState pending={view.isPending} error={view.error} retry={() => void view.refetch()} />
    {view.error && <p className="muted">Вид или база недоступны. Остальной текст страницы можно редактировать; записи не удалены из-за этой ссылки.</p>}
    {view.data?.layout === "calendar" ? <EmbeddedCalendar key={`${view.data.id}:${timeZone}`} base={base} view={view.data} timeZone={timeZone} onOpenPage={onOpenPage} /> : view.data && <>
      <QueryState pending={records.isPending} error={records.error} retry={() => void records.refetch()} />
      {records.data && <>
        {view.data.layout === "table" ? <EmbeddedRecordsTable table={records.data} groupBy={view.data.query?.group_by} timeZone={timeZone} onOpenPage={onOpenPage} /> : <DatabaseRecordCards items={records.data.items} properties={records.data.properties} group={records.data.properties.find(property => property.id === view.data?.query.group_by)} board={view.data.layout === "board"} locked renderValue={(value, property, item) => displayValue(value, property, timeZone, item)} onOpenPage={id => onOpenPage?.(id)} />}
        {!records.data.items.length && <p className="muted">В этом виде пока нет записей.</p>}
        <div className="embedded-view-toolbar"><span className="muted">{records.data.items.length} из {records.data.total} · только чтение</span><Pager size={pageSize} offset={offset} count={records.data.items.length} onChange={setOffset} /></div>
      </>}
    </>}
  </section>;
}
