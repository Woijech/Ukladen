"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RequestError, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Pager, QueryState, useAction } from "@/shared/ui";
import { aiBase, type Source } from "./ai-api";
import { SourceViewer } from "./ai-sources";
import { TaskProposalEditor, type TaskDraft, type ProposalAction } from "./ai-task-editor";
import { PlanDetails, type WorkPlan } from "../task-planning";
import type { Block } from "./notes";

type Values = Partial<WorkPlan> & {
  task?: TaskDraft;
  priority?: string; status?: string; remaining_minutes?: number | null; estimated_minutes?: number | null; deadline_at?: string | null;
  estimate_kind?: string; uncertainties?: string[]; sources?: Source[];
  possible_duplicates?: { id: string; title: string; status: string }[];
  parent_action?: number | null; predecessor_actions?: number[]; predecessor_ids?: string[];
  title?: string;
  description?: string | null;
  location?: string | null;
  starts_at?: string;
  ends_at?: string;
  due_at?: string;
  blocks_time?: boolean;
  minutes_before?: number;
  parent_id?: string | null;
  event_id?: string | null;
  event_action?: number | null;
  source?: "personal" | "official";
  document?: { schema_version: number; blocks: Block[] };
};
type Effect = { operation: string; target_id: string | null; before: Values | null; after: Values; warnings: string[] };
export type Proposal = {
  id: string;
  digest: string;
  run_id: string;
  expires_at: string;
  timezone: string;
  status: "pending" | "applied" | "rejected" | "expired" | "conflict" | "superseded";
  batch?: { actions: ProposalAction[] };
  effects: Effect[];
  outcomes: { operation: string; target_id: string }[];
};
const operations: Record<string, string> = {
  page_create: "Создать страницу", page_update: "Изменить страницу",
  event_create: "Создать личное событие", event_update: "Изменить личное событие",
  reminder_create: "Добавить напоминание",
  task_create: "Создать задачу", task_update: "Изменить задачу", task_plan_apply: "Применить план задач",
};
const statuses: Record<Proposal["status"], string> = {
  pending: "Ожидает подтверждения", applied: "Все изменения применены", rejected: "Отклонено",
  expired: "Срок подтверждения истёк", conflict: "Данные изменились — нужен новый предпросмотр",
  superseded: "Заменено новым предложением",
};
function timestamp(value: string, timezone: string) {
  return new Intl.DateTimeFormat("ru", { timeZone: timezone, dateStyle: "long", timeStyle: "short" }).format(new Date(value));
}
function Preview({ values, timezone, operation }: { values: Values; timezone: string; operation: string }) {
  if (operation === "task_plan_apply" && values.sessions) return <PlanDetails plan={values as WorkPlan} />;
  return <div className="ai-action-values">
    {values.task && <Preview values={values.task} timezone={timezone} operation="task_values" />}
    {values.priority && <p>Приоритет: {({ low: "Низкий", normal: "Обычный", high: "Высокий", urgent: "Срочный" } as Record<string, string>)[values.priority]}</p>}
    {values.status && <p>Статус: {({ todo: "К выполнению", in_progress: "В работе", done: "Готово", cancelled: "Отменена" } as Record<string, string>)[values.status]}</p>}
    {values.estimated_minutes !== undefined && <p>Оценка: {values.estimated_minutes == null ? "не указана" : `${values.estimated_minutes} мин`}</p>}
    {values.remaining_minutes !== undefined && <p>Осталось работы: {values.remaining_minutes == null ? "не указано" : `${values.remaining_minutes} мин`}</p>}
    {values.deadline_at !== undefined && <p>Срок: {values.deadline_at ? timestamp(values.deadline_at, timezone) : "не задан"}</p>}
    {values.estimate_kind && <p>{values.estimate_kind === "estimate" ? "Продолжительность предложена как оценка." : values.estimate_kind === "source" ? "Продолжительность указана в источнике." : "Продолжительность неизвестна."}</p>}
    {values.uncertainties?.map((text, index) => <p key={index}>Требует уточнения: {text}</p>)}
    {!!values.possible_duplicates?.length && <div><strong>Возможные дубликаты</strong><ul>{values.possible_duplicates.map(item => <li key={item.id}>{item.title}</li>)}</ul><p>Это подсказки. Задачи не объединяются автоматически.</p></div>}
    {values.parent_action != null && <p>Подзадача действия №{values.parent_action + 1}</p>}
    {!!values.predecessor_actions?.length && <p>После действий: {values.predecessor_actions.map(index => index + 1).join(", ")}</p>}
    {!!values.predecessor_ids?.length && <p>Предшественники: {values.predecessor_ids.join(", ")}</p>}
    {values.title !== undefined && <p><strong>{values.title || "Без названия"}</strong></p>}
    {values.description !== undefined && <p>Описание: {values.description || "—"}</p>}
    {values.location !== undefined && <p>Место: {values.location || "—"}</p>}
    {values.starts_at && <p>Начало: {timestamp(values.starts_at, timezone)}</p>}
    {values.ends_at && <p>Конец: {timestamp(values.ends_at, timezone)}</p>}
    {values.blocks_time !== undefined && <p>{values.blocks_time ? "Занимает время в календаре" : "Не занимает время в календаре"}</p>}
    {values.minutes_before !== undefined && <p>Напомнить за {values.minutes_before} мин.</p>}
    {values.due_at && <p><strong>Уведомление: {timestamp(values.due_at, timezone)}</strong></p>}
    {values.parent_id === null && <p>Расположение: корень страниц</p>}
    {values.event_action != null && <p>Для события из действия №{values.event_action + 1}</p>}
    {values.document && <div aria-label="Содержимое страницы">{values.document.blocks.length === 0 ? <p>Пустая страница</p> : values.document.blocks.map((block) => <div key={block.id} className="ai-action-block">
      {block.type === "list" ? (block.style === "numbered" ? <ol>{block.items.map((item, index) => <li key={index}>{item}</li>)}</ol> : <ul>{block.items.map((item, index) => <li key={index}>{item}</li>)}</ul>) : block.type === "heading" ? <strong>{block.text}</strong> : block.type === "checkbox" ? <span>{block.checked ? "☑" : "☐"} {block.text}</span> : block.type === "link" ? <span>{block.text} · {block.url}</span> : block.text}
    </div>)}</div>}
  </div>;
}

export function ActionProposals({ chatId, runId, running, onOpenPage, onOpenEvent }: {
  chatId: string; runId?: string; running: boolean;
  onOpenPage: (id: string) => void; onOpenEvent: (id: string, startsAt: string, source: "personal" | "official") => Promise<void>;
}) {
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Proposal | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [partialAccepted, setPartialAccepted] = useState<Record<string, boolean>>({});
  const query = useQuery({
    queryKey: ["ai-proposals", chatId, runId, offset], staleTime: 0, enabled: !running,
    queryFn: async ({ signal }) => {
      try { return await requestJson<Proposal[]>(`${aiBase}/conversations/${chatId}/proposals?limit=10&offset=${offset}`, { signal }); }
      catch (error) { if (error instanceof RequestError && error.status === 503) return []; throw error; }
    },
  });
  const client = useQueryClient();
  const action = useAction();
  const proposals = query.data;
  useEffect(() => {
    const pending = proposals?.filter((item) => item.status === "pending");
    if (!pending?.length) return;
    const wait = Math.min(...pending.map((item) => Date.parse(item.expires_at))) - Date.now();
    if (wait <= 0) return;
    const timer = window.setTimeout(() => { void query.refetch(); }, Math.min(wait + 100, 2147483647));
    return () => window.clearTimeout(timer);
  }, [proposals, query]);
  async function decide(proposal: Proposal, decision: "approve" | "reject") {
    await action.run(async () => {
      try {
        await writeJson(`${aiBase}/proposals/${proposal.id}/decision`, "POST", { digest: proposal.digest, decision });
      } catch (error) {
        if (error instanceof RequestError && error.status === 409)
          throw new Error("Предложение устарело. Ничего не применено: попроси AI подготовить новый предпросмотр.");
        throw error;
      }
      await Promise.all([
        client.invalidateQueries({ queryKey: ["ai-proposals", chatId] }),
        ...["pages", "page", "workspace-calendar", "reminders", "event-reminders", "home-pages", "ai-usage", "tasks-list", "task-detail", "task-children", "work-sessions", "calendar-task-sessions"].map((key) => client.invalidateQueries({ queryKey: [key] })),
      ]);
    });
  }
  return <section className="ai-proposals" aria-label="Предложения действий">
    <QueryState pending={false} error={query.error} retry={() => void query.refetch()} />
    {proposals?.map((proposal) => <article className="ai-action-card" key={proposal.id}>
      <h3>Предложение изменений</h3>
      <p role="status">{statuses[proposal.status]}</p>
      <p className="muted">Часовой пояс: {proposal.timezone}. Подтвердить до {timestamp(proposal.expires_at, proposal.timezone)}.</p>
      {proposal.effects.map((effect, index) => <section key={index} aria-label={`${index + 1}. ${operations[effect.operation]}`}>
        <h4>{index + 1}. {operations[effect.operation]}</h4>
        <div className="ai-action-comparison">
          {effect.before && <div><h5>{effect.operation === "page_create" ? "Родительская страница" : "До"}</h5><Preview values={effect.before} timezone={proposal.timezone} operation={effect.operation} /></div>}
          <div><h5>{effect.before && effect.operation !== "page_create" ? "После" : "Будет создано"}</h5><Preview values={effect.after} timezone={proposal.timezone} operation={effect.operation} /></div>
        </div>
        {effect.after.sources?.map((item, at) => <p key={at}><button className="text-action" onClick={() => setSource(item)}>{item.title}</button> · версия {item.version} · {item.locator}</p>)}
        {effect.operation === "task_create" && <p className="muted">Самостоятельная задача. Чекбоксы и записи не синхронизируются.</p>}
        {effect.warnings.includes("existing_reminders_will_be_cancelled") && <p className="form-error">При переносе прежние напоминания для события будут отменены. Новое напоминание создаётся отдельным действием в этом предложении.</p>}
      </section>)}
      {proposal.status === "pending" && <>
        <p>Все показанные действия применяются вместе. Если данные изменятся, потребуется новый предпросмотр.</p>
        {proposal.batch?.actions.some(item => item.operation === "task_create") && <button className="secondary-button" disabled={action.busy || running} onClick={() => setEditing(proposal)}>Уточнить задачи</button>}
        {proposal.effects.some(effect => effect.operation === "task_plan_apply" && !!effect.after.unplaced?.length) && <>
          {!proposal.batch?.actions.some(item => item.operation === "task_plan_apply" && item.accept_partial === true) ? <button className="secondary-button" disabled={action.busy || running} onClick={() => void action.run(async () => {
            await writeJson(`${aiBase}/proposals/${proposal.id}/revise`, "POST", { actions: proposal.batch!.actions.map(item => item.operation === "task_plan_apply" ? { ...item, accept_partial: true } : item) });
            await client.invalidateQueries({ queryKey: ["ai-proposals", chatId] });
          }, "Частичный план подготовлен. Проверьте и подтвердите новый просмотр.")}>Подготовить частичный план к подтверждению</button> : <label className="checkbox-label"><input type="checkbox" checked={partialAccepted[proposal.id] ?? false} onChange={event => setPartialAccepted({ ...partialAccepted, [proposal.id]: event.target.checked })} />Подтверждаю частичный план и показанный остаток</label>}
        </>}
        <div className="ai-action-buttons">
          <button className="primary-button" disabled={action.busy || running || proposal.effects.some(effect => effect.operation === "task_plan_apply" && (!effect.after.verified || (!!effect.after.unplaced?.length && (!partialAccepted[proposal.id] || !proposal.batch?.actions.some(item => item.operation === "task_plan_apply" && item.accept_partial === true)))))} onClick={() => void decide(proposal, "approve")}>Применить всё</button>
          <button className="secondary-button" disabled={action.busy || running} onClick={() => void decide(proposal, "reject")}>Отклонить</button>
        </div>
      </>}
      {proposal.outcomes.map((outcome, index) => {
        const effect = proposal.effects[index];
        if (outcome.operation.startsWith("task_")) return <p key={index}>{outcome.operation === "task_plan_apply" ? "План сохранён в календаре задач." : "Задача сохранена в разделе «Задачи»."}</p>;
        const isPage = outcome.operation.startsWith("page_");
        const eventId = outcome.operation === "reminder_create" ? (effect.after.event_action != null ? proposal.outcomes[effect.after.event_action].target_id : effect.after.event_id) : outcome.target_id;
        return <button key={index} className="text-action" disabled={action.busy} onClick={() => isPage ? onOpenPage(outcome.target_id) : eventId && void action.run(() => onOpenEvent(eventId, effect.after.starts_at!, effect.after.source ?? "personal"))}>
          {isPage ? "Открыть страницу" : outcome.operation === "reminder_create" ? "Открыть событие с напоминанием" : "Открыть событие"}
        </button>;
      })}
    </article>)}
    {!!proposals?.length && <Pager offset={offset} count={proposals.length} size={10} onChange={setOffset} />}
    {editing?.batch && <TaskProposalEditor proposal={{ ...editing, batch: editing.batch }} chatId={chatId} onClose={() => setEditing(null)} />}
    {source && <SourceViewer source={source} onClose={() => setSource(null)} />}
    <ActionFeedback {...action} />
  </section>;
}
