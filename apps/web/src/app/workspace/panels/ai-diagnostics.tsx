"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, Pager, QueryState, useAction } from "@/shared/ui";
import { aiBase, runLabels, type Run } from "./ai-api";
import { AiRunAnalysis, type DiagnosticEvent } from "./ai-run-analysis";

export const diagnosticCases = [
  { id: "demo", title: "Проверка механизма без API", prompt: "Проверь тестовый инструмент.", expected: "Демо: fake_double получает 7; ответ 14. Проверяет механизм, а не качество модели." },
  { id: "calendar", title: "Расписание на завтра", prompt: "Какие у меня завтра пары? Укажи дату, часовой пояс и источник. Если событий нет, так и скажи.", expected: "get_calendar_events; дата в часовом поясе профиля; ответ совпадает с календарём." },
  { id: "rag", title: "Ответ по документу", prompt: "Объясни основные понятия из выбранного документа. Приведи подтверждающие фрагменты и обозначь, чего в нём нет.", expected: "Сначала выбери тестовую страницу или материал через источники. Проверь найденные фрагменты и ссылки." },
  { id: "missing", title: "Недостаточно данных", prompt: "Какой у меня результат экзамена по предмету «Тестовый неизвестный предмет»? Не придумывай отсутствующие данные.", expected: "Нет выдуманных оценок; честное обозначение недоступности личных оценок IIS." },
  { id: "action", title: "Подтверждение действия", prompt: "Предложи создать задачу «QA: проверить AI» без срока. До моего подтверждения ничего не меняй.", expected: "Только предложение до подтверждения; после подтверждения ровно одна задача. Удали тестовую задачу вручную после проверки." },
];
type Summary = {
  id: string; conversation_id: string | null; model: string; provider: string;
  status: Run["status"]; created_at: string; finished_at: string | null;
  captured: boolean; verdict: string; credential_source: string;
};
type Trace = {
  captured: boolean; truncated: boolean; verdict: string; note: string;
  events: DiagnosticEvent[];
};
type Detail = { run: Run & { conversation_id: string | null; created_at: string; finished_at: string | null }; trace: Trace };
const verdicts: Record<string, string> = { unreviewed: "Не оценено", passed: "Пройдено", failed: "Ошибка" };
const eventLabels: Record<string, string> = {
  model_input: "Состав входного контекста", model_usage: "Учёт токенов шага",
  provider_request: "Параметры отправки провайдеру", provider_usage: "Токены и кеш провайдера",
  tool_policy: "Инструмент заблокирован правилами запроса",
  model_request: "Запрос к модели", model_response: "Ответ модели", model_failure: "Ошибка модели",
  tool_request: "Вызов инструмента", tool_response: "Результат инструмента", tool_failure: "Ошибка инструмента", provider_failure: "Ошибка провайдера",
};
const duration = (start: string, end?: string | null) => end ? `${Math.max(0, (Date.parse(end) - Date.parse(start)) / 1000).toFixed(2)} с` : "Выполняется";

export function AiDiagnostics({ onCreate, onOpenChat }: { onCreate: (scenario: string) => void; onOpenChat: (id: string) => void }) {
  const [status, setStatus] = useState("");
  const [days, setDays] = useState(7);
  const [offset, setOffset] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const [scenario, setScenario] = useState("demo");
  const access = useQuery({ queryKey: ["ai-diagnostic-access"], queryFn: ({ signal }) => requestJson<{ allowed: boolean; user_id: string }>(`${aiBase}/diagnostics/access`, { signal }) });
  const list = useQuery({
    queryKey: ["ai-diagnostic-runs", status, days, offset], enabled: access.data?.allowed === true,
    queryFn: ({ signal }) => requestJson<{ items: Summary[]; has_more: boolean }>(`${aiBase}/diagnostics/runs?days=${days}&limit=20&offset=${offset}${status ? `&status=${status}` : ""}`, { signal }),
    refetchInterval: access.data?.allowed ? 5000 : false,
  });
  const selected = diagnosticCases.find((item) => item.id === scenario)!;
  return <section className="stack ai-diagnostics">
    <h2>Диагностика AI</h2>
    <QueryState pending={access.isPending} error={access.error} retry={() => void access.refetch()} />
    {access.data && !access.data.allowed && <p role="alert">Доступ закрыт. Оператор должен добавить UUID твоего аккаунта в AI_DIAGNOSTIC_ADMIN_IDS на сервере. Твой UUID: <code>{access.data.user_id}</code>.</p>}
    {access.data?.allowed && <>
      <div className="panel stack">
        <h3>Запустить проверку</h3>
        <p>Будет создан отдельный чат с подробным захватом на 7 дней. По умолчанию выбрана демонстрация без внешнего API. Создание чата не вызывает модель: запрос отправляется вручную в чате.</p>
        <label className="field-label">Сценарий<select className="ui-input" value={scenario} onChange={(event) => setScenario(event.target.value)}>{diagnosticCases.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
        <p>{selected.prompt}</p><p className="muted">Проверить: {selected.expected}</p>
        <button className="primary-button" onClick={() => onCreate(scenario)}>Создать тестовый чат</button>
        <details><summary>Как пользоваться</summary><ol>
          <li>Начни с демонстрации: она не проверяет реальную модель.</li>
          <li>Для живого теста явно выбери модель и подключение. Каждый запрос расходует выбранный ключ; автоматического пакетного запуска нет.</li>
          <li>Для документов подготовь отдельную тестовую страницу или файл и выбери его в чате. Настоящая модель получает выбранные собственные данные через обычные инструменты.</li>
          <li>Вернись сюда, открой запрос, сравни шаги с ожидаемым результатом и поставь оценку.</li>
          <li>Для сравнения моделей повтори тот же сценарий с теми же данными в новом чате. Экспорт содержит личные данные: проверь его перед отправкой.</li>
        </ol><p>Общие метрики и токены находятся во вкладке «Использование». Оценка администратора — ручная, не автоматическая проверка истинности.</p></details>
      </div>
      <div className="ai-diagnostic-toolbar">
        <label>Статус<select className="ui-input" value={status} onChange={(event) => { setStatus(event.target.value); setOffset(0); }}><option value="">Все</option>{Object.entries(runLabels).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
        <label>Период<select className="ui-input" value={days} onChange={(event) => { setDays(Number(event.target.value)); setOffset(0); }}><option value={7}>7 дней</option><option value={30}>30 дней</option></select></label>
        <button className="secondary-button" onClick={() => void list.refetch()}>Обновить</button>
      </div>
      <QueryState pending={list.isPending} error={list.error} retry={() => void list.refetch()} />
      <p className="muted">Только твои запросы. Старые и обычные чаты имеют журнал попыток, но подробный захват задним числом не восстанавливается. Даты показаны в часовом поясе браузера.</p>
      <div className="ai-table-scroll" tabIndex={0} role="region" aria-label="Журнал AI-запросов"><table className="ai-table"><caption>Журнал AI-запросов</caption><thead><tr><th>Время / модель</th><th>Статус</th><th>Время ответа</th><th>Подключение</th><th>Оценка</th><th>Разбор</th></tr></thead><tbody>{list.data?.items.map((run) => <tr key={run.id}>
        <td>{new Date(run.created_at).toLocaleString("ru")}<br />{run.model}</td><td>{runLabels[run.status]}</td><td>{duration(run.created_at, run.finished_at)}</td><td>{{ demo: "Демонстрация", personal: "Личный API", operator: "Ключ приложения" }[run.credential_source]}</td><td>{verdicts[run.verdict]}</td><td><button className="secondary-button" onClick={() => setRunId(run.id)}>Открыть запрос</button>{run.captured && <small> Подробный захват</small>}</td>
      </tr>)}</tbody></table></div>
      {list.data?.items.length === 0 && <p>Запросов за выбранный период нет.</p>}
      <Pager offset={offset} size={20} count={list.data?.items.length ?? 0} hasMore={list.data?.has_more ?? false} onChange={setOffset} />
      {runId && <DiagnosticDetails key={runId} runId={runId} onClose={() => { setRunId(null); void list.refetch(); }} onOpenChat={onOpenChat} />}
    </>}
  </section>;
}

function DiagnosticDetails({ runId, onClose, onOpenChat }: { runId: string; onClose: () => void; onOpenChat: (id: string) => void }) {
  const query = useQuery({ queryKey: ["ai-diagnostic-detail", runId], staleTime: 0, gcTime: 0,
    queryFn: ({ signal }) => requestJson<Detail>(`${aiBase}/diagnostics/runs/${runId}`, { signal }),
    refetchInterval: (query) => ["queued", "running"].includes(query.state.data?.run.status ?? "") ? 1500 : false,
  });
  const action = useAction();
  const [verdict, setVerdict] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const data = query.data;
  const exportReport = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify({ exported_at: new Date().toISOString(), ...data }, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `ai-diagnostic-${runId}.json`; link.click(); URL.revokeObjectURL(url);
  };
  return <Modal title="Разбор AI-запроса" onClose={onClose} wide>
    <h2>Разбор AI-запроса</h2><QueryState pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
    {data && <div className="ai-diagnostic-detail">
      <p><code>{data.run.id}</code><br />{data.run.provider} · {data.run.model} · {runLabels[data.run.status]}</p>
      <p>Время: {duration(data.run.created_at, data.run.finished_at)}. Стоимость: {data.run.estimated_cost != null ? `${data.run.estimated_cost} ${data.run.price?.currency ?? ""}` : "неизвестна"}. Неоценённых попыток: {data.run.unpriced_attempts}.</p>
      <div className="ai-diagnostic-toolbar">{data.run.conversation_id && <button className="secondary-button" onClick={() => onOpenChat(data.run.conversation_id!)}>Открыть чат и источники</button>}<button className="secondary-button" onClick={exportReport}>Скачать JSON-отчёт</button><button className="secondary-button" onClick={() => void query.refetch()}>Обновить</button></div>
      <h3>Временная шкала</h3>
      <ol>{[
        ...data.run.attempts.map((item) => ({ at: item.started_at, text: `Модель #${item.number}: ${item.status}; ${item.error_code ?? "без ошибки"}; ${duration(item.started_at, item.finished_at)}; токены ${item.input_tokens ?? "?"} / ${item.output_tokens ?? "?"}` })),
        ...data.run.tools.map((item) => ({ at: item.started_at, text: `${item.tool_name} #${item.number}: ${item.status}; ${item.error_code ?? "без ошибки"}; ${duration(item.started_at, item.finished_at)}` })),
      ].sort((a, b) => a.at.localeCompare(b.at)).map((item, i) => <li key={i}>{new Date(item.at).toLocaleTimeString("ru")} — {item.text}</li>)}</ol>
      {!data.run.attempts.length && <p>Вызовов модели не зарегистрировано.</p>}
      <AiRunAnalysis run={data.run} events={data.trace.events} />
      <h3>Содержимое тестового выполнения</h3>
      {!data.trace.captured && <p>Подробного захвата нет: чат обычный, захват удалён или истёк срок хранения. Ответ и цитаты смотри в чате.</p>}
      {data.trace.truncated && <p role="alert">Достигнут лимит захвата. Часть данных отсутствует.</p>}
      {data.trace.events.map((item, index) => <details key={index}><summary>{new Date(item.at).toLocaleTimeString("ru")} · {eventLabels[item.kind] ?? item.kind}</summary><pre className="ai-diagnostic-json">{JSON.stringify(item.payload, null, 2)}</pre></details>)}
      <form onSubmit={(event) => { event.preventDefault(); void action.run(async () => { await writeJson(`${aiBase}/diagnostics/runs/${runId}/review`, "PUT", { verdict: verdict ?? data.trace.verdict, note: note ?? data.trace.note }); await query.refetch(); }, "Оценка сохранена"); }}>
        <label className="field-label">Результат проверки<select className="ui-input" value={verdict ?? data.trace.verdict} onChange={(event) => setVerdict(event.target.value)}>{Object.entries(verdicts).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
        <label className="field-label">Ожидание, фактический результат и причина оценки<textarea maxLength={2000} value={note ?? data.trace.note} onChange={(event) => setNote(event.target.value)} /></label>
        <button className="secondary-button" disabled={action.busy}>Сохранить оценку</button>
      </form>
      <button className="secondary-button" disabled={action.busy || ["queued", "running"].includes(data.run.status)} onClick={() => void action.run(async () => { await writeJson(`${aiBase}/diagnostics/runs/${runId}/capture`, "DELETE"); setVerdict(null); setNote(null); await query.refetch(); }, "Захват и оценка удалены")}>Удалить подробный захват и оценку</button>
      <ActionFeedback {...action} />
    </div>}
  </Modal>;
}
