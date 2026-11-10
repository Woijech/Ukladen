import type { Run } from "./ai-api";

export type DiagnosticEvent = {
  kind: string;
  at: string;
  payload: Record<string, unknown>;
};
type Size = { characters: number; bytes: number };
type Input = {
  tool_mode: string;
  message_count: number;
  parts: Record<string, Size>;
  tools: (Size & { name: string })[];
};
type ProviderUsage = {
  cached_tokens?: number | null;
  cache_write_tokens?: number | null;
  reasoning_tokens?: number | null;
  finish_reasons?: (string | null)[];
};
const number = (value: number | null | undefined) => value == null ? "неизвестно" : value.toLocaleString("ru");
const partLabels: Record<string, string> = {
  system: "Системные инструкции и настройки",
  tool_schemas: "Описания и схемы инструментов",
  history: "История до текущего сообщения",
  current_request: "Текущее сообщение пользователя",
  tool_results: "Результаты инструментов текущего шага",
  assistant_calls: "Вызовы инструментов и сообщения модели",
};
function value(event?: DiagnosticEvent): Record<string, unknown> | undefined {
  const data = event?.payload.value;
  return data && typeof data === "object" && !Array.isArray(data)
    ? data as Record<string, unknown> : undefined;
}
function latest(events: DiagnosticEvent[], kind: string, attempt: number) {
  return value(events.findLast((event) => event.kind === kind && value(event)?.attempt === attempt));
}
function elapsed(start: string, end: string | null) {
  return end ? `${Math.max(0, Date.parse(end) - Date.parse(start)).toLocaleString("ru")} мс` : "выполняется";
}
function knownSum(values: (number | null)[]) {
  const unknown = values.filter((v) => v == null).length;
  const sum = values.reduce<number>((total, v) => total + (v ?? 0), 0);
  return values.length === 0 ? "нет вызовов" : unknown === values.length ? `неизвестно (${unknown} шаг.)` : `${number(sum)}${unknown ? ` + неизвестно (${unknown} шаг.)` : ""}`;
}
function tariffCost(run: Run, input: number | null, output: number | null) {
  if (!run.price || input == null || output == null) return "неизвестно";
  const cost = (input * Number(run.price.input_per_million) + output * Number(run.price.output_per_million)) / 1_000_000;
  return Number.isFinite(cost) ? `${cost.toLocaleString("ru", { maximumFractionDigits: 8 })} ${run.price.currency}` : "неизвестно";
}

export function AiRunAnalysis({ run, events = [] }: { run: Run; events?: DiagnosticEvent[] }) {
  return <section className="stack ai-run-analysis" aria-label="Расход по шагам">
    <h3>Расход по шагам</h3>
    <div className="ai-diagnostic-totals">
      <div className="panel"><strong>Входные токены</strong><p>{knownSum(run.attempts.map(a => a.input_tokens))}</p></div>
      <div className="panel"><strong>Выходные токены</strong><p>{knownSum(run.attempts.map(a => a.output_tokens))}</p></div>
      <div className="panel"><strong>Вызовы</strong><p>Модель: {run.attempts.length} · инструменты: {run.tools.length}</p></div>
    </div>
    <p className="muted">Токены рассуждения входят в учёт провайдера и не прибавляются к выходным повторно. Оценка по базовому тарифу не учитывает скидку кеша и дополнительные сборы, не является счётом. Неизвестные значения не означают ноль.</p>
    <p className="muted">Токены сообщает провайдер для каждого обращения к модели, включая повторные попытки. Системные инструкции, схемы и история передаются снова. Входные токены разных шагов суммируются; кешированные токены уже входят во входные и повторно не прибавляются.</p>
    {run.attempts.map((attempt) => {
      const input = latest(events, "model_input", attempt.number) as Input | undefined;
      const usage = latest(events, "provider_usage", attempt.number) as ProviderUsage | undefined;
      const wire = latest(events, "provider_request", attempt.number);
      const response = latest(events, "model_response", attempt.number);
      const messages = response?.messages as { tool_calls?: { name: string; args: unknown }[] }[] | undefined;
      const calls = messages?.flatMap(m => m.tool_calls ?? []) ?? [];
      const denied = events.filter(e => e.kind === "tool_policy" && value(e)?.attempt === attempt.number).map(e => value(e)?.tool);
      const totalBytes = Object.values(input?.parts ?? {}).reduce((sum, p) => sum + p.bytes, 0);
      return <details className="panel" key={attempt.number} open>
        <summary><strong>Модель — шаг {attempt.number}</strong> · {elapsed(attempt.started_at, attempt.finished_at)}</summary>
        <div className="stack">
          <p>Статус: {({ succeeded: "завершён", started: "выполняется", failed: "ошибка", interrupted: "прерван" } as Record<string, string>)[attempt.status] ?? attempt.status}{attempt.error_code ? ` · ${attempt.error_code}` : ""}.</p>
          <dl className="ai-diagnostic-facts">
            <div><dt>Входные токены</dt><dd>{number(attempt.input_tokens)}</dd></div>
            <div><dt>Выходные токены</dt><dd>{number(attempt.output_tokens)}</dd></div>
            <div><dt>Из входных прочитано из кеша</dt><dd>{number(usage?.cached_tokens)}</dd></div>
            <div><dt>Записано в кеш</dt><dd>{number(usage?.cache_write_tokens)}</dd></div>
            <div><dt>Токены рассуждения, сообщает провайдер</dt><dd>{number(usage?.reasoning_tokens)}</dd></div>
            <div><dt>Оценка по базовому тарифу</dt><dd>{tariffCost(run, attempt.input_tokens, attempt.output_tokens)}</dd></div>
          </dl>
          {usage?.finish_reasons?.some(Boolean) && <p>Завершение провайдера: {usage.finish_reasons.filter(Boolean).join(", ")}.</p>}
          {wire && <p>HTTP-запрос: {number(wire.request_bytes as number)} байт · лимит ответа: {number(wire.max_output_tokens as number)} токенов · {wire.streaming ? "потоковый ответ" : "обычный ответ"}.</p>}
          {input ? <>
            <h4>Что передано модели</h4>
            <p>Режим: {input.tool_mode === "calendar_lookup" ? "просмотр расписания — только календарь" : "общий запрос"}. Сообщений: {input.message_count}. Доступных инструментов: {input.tools.length}.</p>
            <p className="muted">Ниже измеренные символы и байты сериализованных частей, а не токены. Провайдер не сообщает точное распределение токенов между этими частями. Размеры не включают весь HTTP-конверт и могут отличаться от его размера.</p>
            <div className="ai-table-scroll" tabIndex={0} role="region" aria-label={`Контекст шага ${attempt.number}`}>
              <table className="ai-table"><caption>Состав входа — шаг {attempt.number}</caption><thead><tr><th>Часть</th><th>Символы</th><th>Байты</th><th>Доля байтов</th></tr></thead><tbody>
                {Object.entries(input.parts).map(([name, size]) => <tr key={name}><th>{partLabels[name] ?? name}</th><td>{number(size.characters)}</td><td>{number(size.bytes)}</td><td>{totalBytes ? Math.round(size.bytes / totalBytes * 100) : 0}%</td></tr>)}
              </tbody></table>
            </div>
            <details><summary>Доступные инструменты и размер их схем</summary>
              {input.tools.length ? <ul>{input.tools.map(tool => <li key={tool.name}><code>{tool.name}</code> — {number(tool.characters)} символов / {number(tool.bytes)} байт</li>)}</ul> : <p>Инструменты не переданы: ожидается итоговый ответ.</p>}
            </details>
          </> : <p className="muted">Разбивка контекста для этого шага не записана: старый запуск, обычный чат или захват ограничен. Её нельзя восстановить по общему числу токенов.</p>}
          <h4>Что выбрала модель</h4>
          {denied.length > 0 && <p role="alert">Заблокировано правилами просмотра расписания: {denied.map(String).join(", ")}. Эти инструменты не выполнялись.</p>}
          {calls.length ? <ul>{calls.map((call, i) => <li key={i}><code>{call.name}</code><pre className="ai-diagnostic-json">{JSON.stringify(call.args, null, 2)}</pre></li>)}</ul> : <p>{response ? "Ответ без вызовов инструментов." : "Ответ модели отсутствует в захвате."}</p>}
        </div>
      </details>;
    })}
    <h4>Выполнение инструментов</h4>
    <p className="muted">Локальный инструмент сам не расходует токены чат-модели. Его результат может увеличить вход следующего шага. Web-поиск и другие внешние сервисы могут иметь отдельную стоимость.</p>
    {run.tools.length ? run.tools.map(tool => {
      const request = value(events.find(e => e.kind === "tool_request" && value(e)?.number === tool.number));
      const response = value(events.find(e => e.kind === "tool_response" && value(e)?.number === tool.number));
      const size = response?.size as Size | undefined;
      return <details className="panel" key={tool.number}>
        <summary>Инструмент {tool.number}: <code>{tool.tool_name}</code> · {elapsed(tool.started_at, tool.finished_at)}</summary>
        <p>Статус: {({ succeeded: "завершён", started: "выполняется", failed: "ошибка", interrupted: "прерван" } as Record<string, string>)[tool.status] ?? tool.status}{tool.error_code ? ` · ${tool.error_code}` : ""}.</p>
        {size && <p>Размер результата: {number(size.characters)} символов / {number(size.bytes)} байт. Это размер результата инструмента, не точное число токенов в следующем запросе.</p>}
        {request ? <><h5>Аргументы</h5><pre className="ai-diagnostic-json">{JSON.stringify(request.arguments, null, 2)}</pre></> : <p>Аргументы не записаны.</p>}
        {response ? <><h5>Результат</h5><pre className="ai-diagnostic-json">{JSON.stringify(response.content, null, 2)}</pre></> : <p>Результат не записан.</p>}
      </details>;
    }) : <p>Инструменты не вызывались.</p>}
  </section>;
}
