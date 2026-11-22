"use client";

import { useState, type ReactNode } from "react";
import type { Property, RecordItem, Value } from "./databases";

export function groupRecords(items: RecordItem[], property?: Property) {
  if (!property) return [{ id: "all", name: "", items }];
  const choices = property.kind === "checkbox"
    ? [{ id: "true", name: "Отмечено" }, { id: "false", name: "Не отмечено" }]
    : property.options;
  return [...choices, { id: "empty", name: "Без значения" }].map(choice => ({
    ...choice,
    items: items.filter(item => {
      const value = item.record.values[property.id];
      return choice.id === "empty" ? value == null : String(value) === choice.id;
    }),
  }));
}

export function DatabaseRecordCards({ items, properties, group, board, locked, renderValue, onOpenPage, onEdit }: {
  items: RecordItem[]; properties: Property[]; group?: Property; board: boolean; locked: boolean;
  renderValue: (value: Value, property: Property, item: RecordItem) => ReactNode;
  onOpenPage: (id: string) => void; onEdit?: (item: RecordItem) => void;
}) {
  const [showEmpty, setShowEmpty] = useState(false);
  const groups = groupRecords(items, group).filter(item => (board && showEmpty) || item.items.length);
  return <>
    {board && <label className="inline-check database-empty-groups"><input type="checkbox" checked={showEmpty} onChange={event => setShowEmpty(event.target.checked)} />Показывать пустые группы</label>}
    <div className={board ? "database-board" : "database-record-list"} aria-label={board ? "Доска записей" : "Список записей"}>
    {groups.map(column => <section key={column.id} className="database-record-group" aria-label={column.name || "Записи"}>
      {column.name && <h3>{column.name}<span>{column.items.length}</span></h3>}
      <div className="database-record-group-items">{column.items.map(item => <article key={item.record.id}>
        <button type="button" className="table-page-link" onClick={() => onOpenPage(item.page.id)}>{item.page.title}</button>
        <dl>{properties.filter(property => property.id !== group?.id).map(property => <div key={property.id}><dt>{property.name}</dt><dd>{renderValue(item.record.values[property.id], property, item)}</dd></div>)}</dl>
        {onEdit && <button type="button" className="text-action" disabled={locked || !!item.record.trashed_at || !properties.some(property => !["formula", "rollup"].includes(property.kind))} onClick={() => onEdit(item)}>Изменить поля</button>}
      </article>)}</div>
      {board && !column.items.length && <p className="muted">Нет записей на этой странице</p>}
    </section>)}
  </div></>;
}
