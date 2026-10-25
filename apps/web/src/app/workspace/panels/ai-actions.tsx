"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RequestError, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Pager, QueryState, useAction } from "@/shared/ui";
import { aiBase } from "./ai-api";
import type { Block } from "./notes";

type Values = {
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
  effects: Effect[];
  outcomes: { operation: string; target_id: string }[];
};
const operations: Record<string, string> = {
  page_create: "Создать страницу", page_update: "Изменить страницу",
  event_create: "Создать личное событие", event_update: "Изменить личное событие",
  reminder_create: "Добавить напоминание",
};
const statuses: Record<Proposal["status"], string> = {
  pending: "Ожидает подтверждения", applied: "Все изменения применены", rejected: "Отклонено",
  expired: "Срок подтверждения истёк", conflict: "Данные изменились — нужен новый предпросмотр",
  superseded: "Заменено новым предложением",
};
function timestamp(value: string, timezone: string) {
  return new Intl.DateTimeFormat("ru", { timeZone: timezone, dateStyle: "long", timeStyle: "short" }).format(new Date(value));
}
function Preview({ values, timezone }: { values: Values; timezone: string }) {
  return <div className="ai-action-values">
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
        ...["pages", "page", "workspace-calendar", "reminders", "event-reminders", "home-pages", "ai-usage"].map((key) => client.invalidateQueries({ queryKey: [key] })),
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
          {effect.before && <div><h5>{effect.operation === "page_create" ? "Родительская страница" : "До"}</h5><Preview values={effect.before} timezone={proposal.timezone} /></div>}
          <div><h5>{effect.before && effect.operation !== "page_create" ? "После" : "Будет создано"}</h5><Preview values={effect.after} timezone={proposal.timezone} /></div>
        </div>
        {effect.warnings.includes("existing_reminders_will_be_cancelled") && <p className="form-error">При переносе прежние напоминания для события будут отменены. Новое напоминание создаётся отдельным действием в этом предложении.</p>}
      </section>)}
      {proposal.status === "pending" && <>
        <p>Все показанные действия применяются вместе. Если данные изменятся, потребуется новый предпросмотр.</p>
        <div className="ai-action-buttons">
          <button className="primary-button" disabled={action.busy || running} onClick={() => void decide(proposal, "approve")}>Применить всё</button>
          <button className="secondary-button" disabled={action.busy || running} onClick={() => void decide(proposal, "reject")}>Отклонить</button>
        </div>
      </>}
      {proposal.outcomes.map((outcome, index) => {
        const effect = proposal.effects[index];
        const isPage = outcome.operation.startsWith("page_");
        const eventId = outcome.operation === "reminder_create" ? (effect.after.event_action != null ? proposal.outcomes[effect.after.event_action].target_id : effect.after.event_id) : outcome.target_id;
        return <button key={index} className="text-action" disabled={action.busy} onClick={() => isPage ? onOpenPage(outcome.target_id) : eventId && void action.run(() => onOpenEvent(eventId, effect.after.starts_at!, effect.after.source ?? "personal"))}>
          {isPage ? "Открыть страницу" : outcome.operation === "reminder_create" ? "Открыть событие с напоминанием" : "Открыть событие"}
        </button>;
      })}
    </article>)}
    {!!proposals?.length && <Pager offset={offset} count={proposals.length} size={10} onChange={setOffset} />}
    <ActionFeedback {...action} />
  </section>;
}
