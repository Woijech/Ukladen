"use client";

import { useState } from "react";
import type { Source } from "./ai-api";
import { SourceViewer } from "./ai-sources";
import type { DiagnosticEvent } from "./ai-run-analysis";

export type ContextSize = { characters: number; bytes: number };
export type ContextInput = { parts: Record<string, ContextSize>; fingerprints?: Record<string, string>; tools: (ContextSize & { name: string })[]; tool_mode: string; message_count: number };
export const contextLabels: Record<string, string> = {
  system: "Системные инструкции и контекст", tool_schemas: "Схемы инструментов", history: "История", current_request: "Текущее сообщение", tool_results: "Ответы инструментов", assistant_calls: "Сообщения и вызовы модели",
};
export function eventValue(event?: DiagnosticEvent): Record<string, unknown> | undefined {
  const value = event?.payload.value;
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}

export function ContextComposition({ input, previous }: { input: ContextInput; previous?: ContextInput }) {
  const parts = Object.entries(input.parts).sort((a, b) => b[1].bytes - a[1].bytes);
  const total = parts.reduce((sum, [, size]) => sum + size.bytes, 0);
  const previousTotal = previous ? Object.values(previous.parts).reduce((sum, size) => sum + size.bytes, 0) : null;
  const repeated = previous && input.fingerprints ? parts.filter(([name, size]) => size.bytes > 2 && input.fingerprints?.[name] === previous.fingerprints?.[name]) : [];
  return <section className="context-composition" aria-label="Из чего состоит запрос">
    <h4>Из чего состоит запрос</h4><p className="muted">Измеренные байты, не токены. Провайдер сообщает токены для всего вызова; точное распределение по частям неизвестно. Сериализация и токенизация дают разные единицы измерения.</p>
    <div className="context-bar" role="img" aria-label={parts.map(([name, size]) => `${contextLabels[name] ?? name}: ${size.bytes} байт`).join(", ")}>{parts.map(([name, size], index) => <span key={name} className={`context-color-${index % 6}`} style={{ width: `${total ? size.bytes / total * 100 : 0}%` }} />)}</div>
    <ul className="context-legend">{parts.map(([name, size], index) => <li key={name}><span className={`context-key context-color-${index % 6}`} />{contextLabels[name] ?? name}<strong>{size.bytes.toLocaleString("ru")} Б · {total ? Math.round(size.bytes / total * 100) : 0}%</strong></li>)}</ul>
    <div className="context-findings"><h5>Измеренные факты</h5><ul>
      {!!parts.length && <li>Самая крупная часть: {contextLabels[parts[0][0]] ?? parts[0][0]} — {parts[0][1].bytes.toLocaleString("ru")} байт.</li>}
      {previousTotal !== null && <li>Изменение объёма к предыдущему вызову: {total - previousTotal > 0 ? "+" : ""}{(total - previousTotal).toLocaleString("ru")} байт.</li>}
      {repeated.length > 0 && <li>Повторно переданы без изменений: {repeated.map(([name]) => contextLabels[name] ?? name).join(", ")}. Это не доказывает повторную оплату: учитывай кеш провайдера.</li>}
      {input.tools.length > 12 && <li>В запросе схемы {input.tools.length} инструментов.</li>}
    </ul>
    {parts.some(([name, size]) => size.bytes > ({ system: 8000, history: 24000, tool_schemas: 12000, tool_results: 32000 }[name] ?? Infinity)) && <p>Предположение для проверки: крупные инструкции, история или результаты инструментов могут увеличивать расход. Пороги подсказки: 8 / 24 / 12 / 32 КБ соответственно. Размер в байтах не доказывает причину стоимости или ненужность данных.</p>}
    </div>
  </section>;
}

export function ContextInspector({ events, attempt }: { events: DiagnosticEvent[]; attempt: number }) {
  const [source, setSource] = useState<Source | null>(null);
  const parts = events.filter(event => event.kind === "context_part" && eventValue(event)?.attempt === attempt);
  const instructions = eventValue(events.findLast(event => event.kind === "instructions" && eventValue(event)?.attempt === attempt));
  const rag = eventValue(events.findLast(event => event.kind === "source_context" && eventValue(event)?.attempt === attempt));
  const analysis = eventValue(events.findLast(event => event.kind === "source_analysis" && eventValue(event)?.attempt === attempt));
  const sources = Array.isArray(rag?.sources) ? rag.sources as Source[] : [];
  return <section className="context-inspector" aria-label={`Инспектор контекста шага ${attempt}`}>
    <h4>Инспектор контекста</h4>
    <p className="muted">Состав после middleware, непосредственно перед сериализацией провайдером. Персональные инструкции и дополнительный контекст включены в системное сообщение; отдельной developer-роли в этом pipeline нет.</p>
    {!parts.length && <p>Отдельные части для этого запуска не записаны. Историческое содержимое не восстанавливается.</p>}
    {parts.map((event, index) => { const part = eventValue(event)!; const size = part.size as ContextSize; return <details key={index}><summary>{contextLabels[String(part.name)] ?? String(part.name)} · {size?.bytes?.toLocaleString("ru")} Б</summary><pre className="ai-diagnostic-json">{typeof part.content === "string" ? part.content : JSON.stringify(part.content, null, 2)}</pre></details>; })}
    {instructions && <details><summary>Персональные инструкции, включённые в system</summary><pre className="ai-diagnostic-json">{String(instructions.personal_instructions || "Не заданы")}</pre></details>}
    {rag && <details><summary>Источники и RAG · {sources.length} ссылок · {String(rag.analysis_bytes)} Б анализа</summary>
      <p>Выбранные источники показаны ниже. Фактически отправленные фрагменты находятся в системном сообщении и ответах инструментов выше; наличие ссылки само по себе не доказывает передачу всего документа.</p>
      {sources.map((item, index) => <button type="button" className="text-action" key={index} onClick={() => setSource(item)}>{item.title || item.id}</button>)}
      {Array.isArray(rag.results) && <ul>{(rag.results as { tool: string; bytes: number; source_count: number; returned_items: number | null }[]).map((item, index) => <li key={index}>{item.tool} · {item.bytes.toLocaleString("ru")} Б · источников: {item.source_count}{item.returned_items !== null ? ` · элементов: ${item.returned_items}` : ""}</li>)}</ul>}
      {analysis && <details><summary>Анализ, включённый в system</summary><pre className="ai-diagnostic-json">{JSON.stringify(analysis.content, null, 2)}</pre></details>}
    </details>}
    {events.some(event => event.kind === "context_part" && event.payload.truncated) && <p role="status">Некоторые части превысили лимит захвата. Их превью доступно в журнале; полное содержимое не сохранено.</p>}
    {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
  </section>;
}
