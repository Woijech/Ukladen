"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { requestJson } from "@/shared/api";
import { Pager, QueryState } from "@/shared/ui";
import type { Property } from "./databases";

function numericFields(properties: Property[]) {
  const fields = properties.filter(property => property.kind === "number");
  return fields.map((property, index) => ({ ...property, label: fields.filter(item => item.name === property.name).length > 1 ? `${property.name} [${index + 1}]` : property.name }));
}

export function formulaExpression(expression: string, properties: Property[], encode: boolean) {
  const fields = numericFields(properties);
  return expression.replace(/\bprop\s*\(\s*("(?:[^"\\]|\\.)*"|'[^']*')\s*\)/g, (original, quoted: string) => {
    let value: string;
    try { value = quoted.startsWith('"') ? JSON.parse(quoted) : quoted.slice(1, -1); } catch { return original; }
    const field = fields.find(item => (encode ? item.label : item.id) === value);
    return field ? `prop(${JSON.stringify(encode ? field.id : field.label)})` : original;
  });
}

export function CalculationFields({ kind, properties, editing, base }: { kind: Property["kind"]; properties: Property[]; editing?: Property; base: string }) {
  const [offset, setOffset] = useState(0);
  const [target, setTarget] = useState(editing?.relation_database_id ?? "");
  const [relation, setRelation] = useState(editing?.calculation?.relation_property_id ?? "");
  const [valueProperty, setValueProperty] = useState(editing?.calculation?.value_property_id ?? "");
  const [operation, setOperation] = useState(editing?.calculation?.operation ?? "count");
  const [expression, setExpression] = useState(formulaExpression(editing?.calculation?.expression ?? "", properties, false));
  const databases = useQuery({ queryKey: ["relation-database-options", offset], enabled: kind === "relation",
    queryFn: ({ signal }) => requestJson<{ items: { id: string; name: string }[] }>(`/api/v1/workspace/databases?limit=50&offset=${offset}`, { signal }) });
  const selected = properties.find(property => property.id === relation);
  const fields = useQuery({ queryKey: ["rollup-property-options", base, selected?.relation_database_id], enabled: kind === "rollup" && operation !== "count" && !!selected?.relation_database_id,
    queryFn: ({ signal }) => requestJson<{ items: Property[] }>(`/api/v1/workspace/databases/${selected!.relation_database_id}/properties`, { signal }) });
  if (kind === "relation") return <>
    <label htmlFor="relation-database">База со связанными записями</label><select id="relation-database" name="relation_database_id" required value={target} onChange={event => setTarget(event.target.value)}>
      <option value="">Выбрать базу…</option>
      {target && !databases.data?.items.some(item => item.id === target) && <option value={target}>Выбранная база</option>}
      {databases.data?.items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select><QueryState pending={databases.isPending} error={databases.error} retry={() => void databases.refetch()} />
    {databases.data && <Pager offset={offset} count={databases.data.items.length} onChange={setOffset} />}
    <p className="muted">Связь сохраняет ссылки на записи. Страницы остаются в своих базах; обратная связь автоматически не создаётся.</p>
  </>;
  if (kind === "formula") return <>
    <label htmlFor="formula-expression">Выражение</label><textarea id="formula-expression" name="formula_expression" rows={3} required maxLength={2000} value={expression} onChange={event => setExpression(event.target.value)} placeholder='Например: prop("Цена") * 2' />
    <label htmlFor="formula-insert">Подставить числовое поле</label><select id="formula-insert" value="" onChange={event => { if (event.target.value) setExpression(current => current + `prop(${JSON.stringify(event.target.value)})`); }}><option value="">Выбрать поле…</option>{numericFields(properties).map(item => <option key={item.id} value={item.label}>{item.label}</option>)}</select>
    <p className="muted">Числа, скобки и + − * / %. Значение вычисляется при чтении. При пустом входе или делении на ноль появится объяснение ошибки.</p>
  </>;
  if (kind === "rollup") return <>
    <label htmlFor="rollup-relation">Через какую связь</label><select id="rollup-relation" name="rollup_relation" required value={relation} onChange={event => { setRelation(event.target.value); setValueProperty(""); }}><option value="">Выбрать поле связи…</option>{relation && !properties.some(item => item.id === relation && item.kind === "relation") && <option value={relation}>Недоступная связь — выбери другую</option>}{properties.filter(item => item.kind === "relation").map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <label htmlFor="rollup-operation">Что посчитать</label><select id="rollup-operation" name="rollup_operation" value={operation} onChange={event => setOperation(event.target.value)}>{[["count", "Количество записей"], ["sum", "Сумма"], ["average", "Среднее"], ["min", "Минимум"], ["max", "Максимум"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
    {operation !== "count" && <><label htmlFor="rollup-value">Числовое поле связанных записей</label><select id="rollup-value" name="rollup_value" required value={valueProperty} onChange={event => setValueProperty(event.target.value)}><option value="">Выбрать поле…</option>{valueProperty && !fields.data?.items.some(item => item.id === valueProperty && item.kind === "number") && <option value={valueProperty}>{fields.isPending ? "Выбранное поле" : "Недоступное поле — выбери другое"}</option>}{fields.data?.items.filter(item => item.kind === "number").map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><QueryState pending={!!selected?.relation_database_id && fields.isPending} error={fields.error} retry={() => void fields.refetch()} /></>}
    <p className="muted">Сводное значение считается по явно связанным записям. Оно не меняет исходные поля.</p>
  </>;
  return null;
}

export function RelationField({ property, value, titles, onTouched }: { property: Property; value: string[]; titles: Record<string, string>; onTouched: () => void }) {
  const [selected, setSelected] = useState(value);
  const [offset, setOffset] = useState(0);
  const query = useQuery({ queryKey: ["relation-record-options", property.relation_database_id, offset], enabled: !!property.relation_database_id,
    queryFn: ({ signal }) => requestJson<{ items: { record: { id: string }; page: { title: string; trashed_at: string | null } }[] }>(`/api/v1/workspace/databases/${property.relation_database_id}/records?limit=50&offset=${offset}`, { signal }) });
  const names = { ...titles, ...Object.fromEntries(query.data?.items.map(item => [item.record.id, item.page.title]) ?? []) };
  function toggle(id: string) { onTouched(); setSelected(current => current.includes(id) ? current.filter(item => item !== id) : current.length < 100 ? [...current, id] : current); }
  return <div className="relation-field" role="group" aria-label={property.name}>
    {selected.map(id => <input key={id} type="hidden" name={property.id} value={id} />)}
    <p className="muted">Выбрано {selected.length} из 100</p>
    {selected.length > 0 && <div className="relation-selected">{selected.map(id => <button type="button" className="text-action" key={id} onClick={() => toggle(id)} aria-label={`Убрать связь: ${names[id] ?? "недоступная запись"}`}>{names[id] ?? "Недоступная запись"} ×</button>)}</div>}
    <QueryState pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
    {query.data?.items.filter(item => !item.page.trashed_at).map(item => <label className="inline-check" key={item.record.id}><input type="checkbox" checked={selected.includes(item.record.id)} disabled={selected.length >= 100 && !selected.includes(item.record.id)} onChange={() => toggle(item.record.id)} />{item.page.title}</label>)}
    {query.data && <Pager offset={offset} count={query.data.items.length} onChange={setOffset} />}
  </div>;
}
