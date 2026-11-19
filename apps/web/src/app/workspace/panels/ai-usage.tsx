"use client";

import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { requestJson } from "@/shared/api";
import { Modal, QueryState } from "@/shared/ui";
import { aiBase, runLabels, type AiAccessStatus, type Run } from "./ai-api";
import { HelpTooltip } from "@/shared/help-tooltip";
import { UsageChart } from "./ai-usage-chart";
import { AiRunAnalysis } from "./ai-run-analysis";

type Metrics = {
  runs: number;
  attempts: number;
  input_tokens: number | null;
  output_tokens: number | null;
  known_input_tokens: number;
  known_output_tokens: number;
  unknown_input_attempts: number;
  unknown_output_attempts: number;
  unpriced_attempts: number;
  unpriced_web_searches?: number;
  estimated_costs: Record<string, string>;
};
type UsageGroup = Metrics & { label: string; fake: boolean };
type Report = {
  retention_partial: boolean;
  timezone: string;
  date_from: string;
  date_to: string;
  summary: Metrics;
  fake: Metrics;
  daily: UsageGroup[];
  models: UsageGroup[];
  recent_runs: {
    id: string;
    provider: string;
    model: string;
    status: Run["status"];
    created_at: string;
    credential_source: string;
  }[];
  has_more: boolean;
  retained_from: string;
};
const tokens = (value: number | null) =>
  value === null ? "Неизвестно" : value.toLocaleString("ru");
const costs = (value: Metrics) =>
  Object.entries(value.estimated_costs)
    .map(([currency, amount]) => `${amount} ${currency}`)
    .join(" + ") || (value.attempts ? "Неизвестно" : "—");

export function AiUsage() {
  const [days, setDays] = useState(7);
  const access = useQuery({ queryKey: ["ai-access"], queryFn: ({ signal }) => requestJson<AiAccessStatus>(`${aiBase}/access`, { signal }) });
  const query = useQuery({ queryKey: ["ai-usage", days], staleTime: 0, placeholderData: keepPreviousData,
    queryFn: ({ signal }) => requestJson<Report>(`${aiBase}/usage?days=${days}&limit=20&offset=0`, { signal }) });
  const report = query.data;
  const totalTokens = report?.summary.input_tokens != null && report.summary.output_tokens != null ? report.summary.input_tokens + report.summary.output_tokens : null;
  const priced = report && report.summary.attempts > 0 && report.summary.unpriced_attempts === 0 && !report.summary.unpriced_web_searches && Object.keys(report.summary.estimated_costs).length > 0;
  return <div className="ai-usage" aria-busy={query.isFetching}>
    <div className="panel-toolbar"><div className="segmented" aria-label="Период статистики">{[7, 30].map(value => <button type="button" key={value} aria-pressed={days === value} onClick={() => setDays(value)}>{value} дней</button>)}</div>
      <button type="button" className="text-action" disabled={query.isFetching} onClick={() => void query.refetch()}>Обновить</button></div>
    <QueryState pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
    <QueryState pending={false} error={access.error} retry={() => void access.refetch()} />
    {report && <>
      <div className="usage-summary" aria-label="Показатели использования">
        <div><span>Запросы</span><strong>{tokens(report.summary.runs)}</strong></div>
        <div><span>Токены<HelpTooltip label="Что такое токены">Части текста, которыми модель измеряет объём запроса и ответа. Повторные вызовы тоже учитываются.</HelpTooltip></span><strong>{tokens(totalTokens)}</strong></div>
        <div><span>Входные<HelpTooltip label="Что такое входные токены">Сообщения, инструкции, история и данные инструментов, отправленные модели.</HelpTooltip></span><strong>{tokens(report.summary.input_tokens)}</strong></div>
        <div><span>Выходные<HelpTooltip label="Что такое выходные токены">Токены ответа модели. Токены рассуждения, если они входят в usage провайдера, повторно не прибавляются.</HelpTooltip></span><strong>{tokens(report.summary.output_tokens)}</strong></div>
        {priced && <div><span>Примерная стоимость<HelpTooltip label="Как рассчитана стоимость">Оценка по сохранённым тарифам, без возможных скидок провайдера. Это не счёт и не баланс аккаунта.</HelpTooltip></span><strong>{costs(report.summary)}</strong></div>}
      </div>
      {(report.retention_partial || report.summary.unknown_input_attempts > 0 || report.summary.unknown_output_attempts > 0 || report.summary.unpriced_attempts > 0 || (report.summary.unpriced_web_searches ?? 0) > 0) && <p className="usage-notice" role="status">{report.retention_partial ? "Часть периода вне срока хранения. " : ""}{report.summary.unknown_input_attempts || report.summary.unknown_output_attempts ? `Учёт токенов неполный: известно ${tokens(report.summary.known_input_tokens)} входных и ${tokens(report.summary.known_output_tokens)} выходных. ` : ""}{report.summary.unpriced_attempts || report.summary.unpriced_web_searches ? "Часть расходов неизвестна; полная стоимость недоступна." : ""}</p>}
      <UsageChart key={days} daily={report.daily} from={report.date_from} to={report.date_to} />
      {access.data && <p className="muted">{access.data.plan === "free" ? "Бесплатный доступ" : `Тариф: ${access.data.plan}`} · Запросов в месяц: {access.data.monthly_request_limit ?? "без ограничений"} · Токенов в месяц: {access.data.monthly_token_limit ?? "без ограничений"}</p>}
      {report.fake.runs > 0 && <p className="muted">Тестовые запросы: {report.fake.runs}. Учитываются отдельно.</p>}
    </>}
  </div>;
}

export function RunDetails({
  runId,
  onClose,
}: {
  runId: string;
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["ai-run-detail", runId],
    staleTime: 0,
    gcTime: 0,
    queryFn: ({ signal }) =>
      requestJson<Run>(`${aiBase}/runs/${runId}`, { signal }),
  });
  const run = query.data;
  return (
    <Modal title="Подробности запроса" onClose={onClose} wide>
      <h2>Подробности запроса</h2>
      <QueryState
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {run && (
        <>
          <p>
            {run.model} · {runLabels[run.status]}
          </p>
          <p>
            Оценка сохранённых попыток:{" "}
            {run.estimated_cost != null
              ? `${run.estimated_cost} ${run.price?.currency ?? ""}`
              : "неизвестно"}
            . Неоценённых попыток:{" "}
            {run.unpriced_attempts ?? run.attempts.length}.
          </p>
          {run.price ? (
            <p className="muted">
              Тариф на {run.price.date}: вход {run.price.input_per_million},
              выход {run.price.output_per_million} {run.price.currency} за
              миллион токенов. Историческая оценка.
            </p>
          ) : (
            <p className="muted">Тариф неизвестен; стоимость не рассчитана.</p>
          )}
          <AiRunAnalysis run={run} />
        </>
      )}
    </Modal>
  );
}
