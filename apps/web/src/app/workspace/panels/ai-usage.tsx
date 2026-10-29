"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { requestJson } from "@/shared/api";
import { Modal, QueryState } from "@/shared/ui";
import { aiBase, runLabels, type AiAccessStatus, type Run } from "./ai-api";

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
  const [range, setRange] = useState<{ from: string; to: string } | null>(null);
  const [offset, setOffset] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const access = useQuery({
    queryKey: ["ai-access"],
    queryFn: ({ signal }) =>
      requestJson<AiAccessStatus>(`${aiBase}/access`, { signal }),
  });
  const query = useQuery({
    queryKey: ["ai-usage", days, range, offset],
    staleTime: 0,
    queryFn: ({ signal }) =>
      requestJson<Report>(
        `${aiBase}/usage?days=${days}&limit=20&offset=${offset}${range ? `&date_from=${range.from}&date_to=${range.to}` : ""}`,
        { signal },
      ),
  });
  const report = query.data;
  return (
    <div className="ai-usage">
      <p className="muted">Оценка стоимости учитывает токены модели. Плата за веб-поиск сюда не входит.</p>
      <QueryState
        pending={access.isPending}
        error={access.error}
        retry={() => void access.refetch()}
      />
      {access.data && (
        <section className="panel" aria-label="Доступ к AI">
          <h2>
            {access.data.plan === "free"
              ? "Бесплатный доступ"
              : `Тариф: ${access.data.plan}`}
          </h2>
          <p>
            Запросов в месяц:{" "}
            {access.data.monthly_request_limit ?? "без ограничений"}. Токенов в месяц:{" "}
            {access.data.monthly_token_limit ?? "без ограничений"}.
          </p>
          <p className="muted">
            Технические ограничения запросов и провайдера сохраняются.
          </p>
        </section>
      )}
      <div className="panel-toolbar">
        <div className="segmented" aria-label="Период статистики">
          {[7, 30].map((value) => (
            <button
              key={value}
              aria-pressed={!range && days === value}
              onClick={() => {
                setDays(value);
                setRange(null);
                setOffset(0);
              }}
            >
              {value} дней
            </button>
          ))}
        </div>
        <button className="text-action" onClick={() => void query.refetch()}>
          Обновить
        </button>
      </div>
      <form
        className="ai-range"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          setRange({
            from: String(data.get("from")),
            to: String(data.get("to")),
          });
          setOffset(0);
        }}
      >
        <label className="field-label">
          С даты
          <input name="from" type="date" required />
        </label>
        <label className="field-label">
          По дату
          <input name="to" type="date" required />
        </label>
        <button className="secondary-button">Показать период</button>
      </form>
      <p className="muted">
        До 31 календарного дня. Статистика доступна в пределах 30-дневного
        хранения.
      </p>
      <QueryState
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {report && (
        <>
          {report.retention_partial && (
            <p role="status" className="muted">
              Часть выбранного периода уже за пределами хранения. Отсутствие
              записей за это время не означает отсутствие запросов.
            </p>
          )}
          <p className="muted">
            {report.date_from} — {report.date_to} · {report.timezone}
          </p>
          <div className="ai-metrics">
            <div className="panel">
              <span>Запросы</span>
              <strong>{report.summary.runs}</strong>
            </div>
            <div className="panel">
              <span>Попытки провайдера</span>
              <strong>{report.summary.attempts}</strong>
            </div>
            <div className="panel">
              <span>Входные / выходные токены</span>
              <strong>
                {tokens(report.summary.input_tokens)} /{" "}
                {tokens(report.summary.output_tokens)}
              </strong>
            </div>
            <div className="panel">
              <span>Оценка стоимости</span>
              <strong>{costs(report.summary)}</strong>
            </div>
          </div>
          <p className="muted">
            Оценка по сохранённым тарифам, не счёт провайдера. Повторные,
            неудачные и отменённые попытки учитываются. Неоценённых попыток:{" "}
            {report.summary.unpriced_attempts}. Поисковых вызовов без оценки платы:{" "}
            {report.summary.unpriced_web_searches ?? 0}. Баланс и внешние запросы
            аккаунта провайдера здесь не отражены.
          </p>
          {(report.summary.unknown_input_attempts > 0 ||
            report.summary.unknown_output_attempts > 0) && (
            <p className="muted">
              Известная часть: {report.summary.known_input_tokens} входных и{" "}
              {report.summary.known_output_tokens} выходных токенов. Полные
              значения неизвестны.
            </p>
          )}
          <MetricsTable title="По дням" rows={report.daily} />
          <MetricsTable
            title="По моделям и подключениям"
            rows={report.models}
          />
          <section className="panel">
            <h2>Последние запросы</h2>
            {report.recent_runs.length === 0 && (
              <p>Запросов за этот период нет.</p>
            )}
            {report.recent_runs.map((run) => (
              <button
                className="ai-run-row"
                key={run.id}
                onClick={() => setRunId(run.id)}
              >
                <span>
                  {new Intl.DateTimeFormat("ru", {
                    timeZone: report.timezone,
                    dateStyle: "short",
                    timeStyle: "short",
                  }).format(new Date(run.created_at))}
                </span>
                <span>
                  {run.provider === "fake" ? "Демонстрация" : run.model}
                </span>
                <span>{runLabels[run.status]}</span>
              </button>
            ))}
            <div className="panel-toolbar">
              <button
                className="secondary-button"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                Назад
              </button>
              <button
                className="secondary-button"
                disabled={!report.has_more}
                onClick={() => setOffset(offset + 20)}
              >
                Далее
              </button>
            </div>
          </section>
          <section className="panel">
            <h2>Тестовая модель</h2>
            <p>
              {report.fake.runs} запросов, {report.fake.attempts} попыток.
              Учитываются отдельно от реальных моделей.
            </p>
            <p className="muted">
              Поиск по смыслу доступен при включённом семантическом индексе.
              Готовность конкретного материала показана в просмотре источника.
            </p>
          </section>
        </>
      )}
      {runId && <RunDetails runId={runId} onClose={() => setRunId(null)} />}
    </div>
  );
}

function MetricsTable({ title, rows }: { title: string; rows: UsageGroup[] }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <div
        className="ai-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={title}
      >
        <table className="ai-table">
          <caption className="visually-hidden">{title}</caption>
          <thead>
            <tr>
              <th scope="col">Период / модель</th>
              <th scope="col">Запросы</th>
              <th scope="col">Попытки</th>
              <th scope="col">Входные токены</th>
              <th scope="col">Выходные токены</th>
              <th scope="col">Оценка</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.label}:${row.fake}`}>
                <th scope="row">
                  {row.label
                    .replace(" · operator", " · приложение")
                    .replace(" · personal", " · личный API")}
                  {row.fake && " (тест)"}
                </th>
                <td>{row.runs}</td>
                <td>{row.attempts}</td>
                <td>{tokens(row.input_tokens)}</td>
                <td>{tokens(row.output_tokens)}</td>
                <td>
                  {costs(row)}
                  {row.unpriced_attempts > 0 && (
                    <small> + неизвестная часть</small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
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
          <h3>Попытки провайдера</h3>
          {run.attempts.map((attempt) => (
            <p key={attempt.number}>
              Попытка {attempt.number}:{" "}
              {attempt.status === "succeeded"
                ? "завершена"
                : attempt.status === "started"
                  ? "выполняется"
                  : "не завершена"}{" "}
              · вход {tokens(attempt.input_tokens)}, выход{" "}
              {tokens(attempt.output_tokens)}
            </p>
          ))}
          <h3>Работа с источниками</h3>
          {run.tools.length ? (
            run.tools.map((tool) => (
              <p key={tool.number}>
                {tool.tool_name} ·{" "}
                {tool.status === "succeeded"
                  ? "готово"
                  : tool.status === "started"
                    ? "выполняется"
                    : "не завершено"}
              </p>
            ))
          ) : (
            <p>Инструменты не вызывались.</p>
          )}
        </>
      )}
    </Modal>
  );
}
