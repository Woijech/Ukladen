"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { writeJson } from "@/shared/api";
import { ActionFeedback, Modal, useAction } from "@/shared/ui";
import { dateTimeLocal, localInstants, resolveLocalTime } from "../calendar-time";
import { aiBase, type Source } from "./ai-api";

export type TaskDraft = { title: string; description?: string | null; priority?: string; deadline_at?: string | null; estimated_minutes?: number | null; remaining_minutes?: number | null; parent_id?: string | null };
export type ProposalAction = { operation: string; task?: TaskDraft; estimate_kind?: string; sources?: Source[]; uncertainties?: string[]; [key: string]: unknown };
function DraftFields({ task, kind, index, timezone }: { task: TaskDraft; kind?: string; index: number; timezone: string }) {
  const [deadline, setDeadline] = useState(task.deadline_at ? dateTimeLocal(new Date(task.deadline_at), timezone) : "");
  const [choice, setChoice] = useState("");
  const [estimateKind, setEstimateKind] = useState(kind ?? "unknown");
  const options = localInstants(deadline, timezone, task.deadline_at ?? undefined);
  return <fieldset className="work-form"><legend>Задача {index + 1}</legend>
    <label>Название<input name={`${index}-title`} defaultValue={task.title} required maxLength={200} /></label>
    <label>Описание<textarea name={`${index}-description`} defaultValue={task.description ?? ""} maxLength={10000} /></label>
    <label>Приоритет<select name={`${index}-priority`} defaultValue={task.priority ?? "normal"}><option value="low">Низкий</option><option value="normal">Обычный</option><option value="high">Высокий</option><option value="urgent">Срочный</option></select></label>
    <label>Срок (необязательно)<input name={`${index}-deadline`} type="datetime-local" value={deadline} onChange={event => { setDeadline(event.target.value); setChoice(""); }} /></label>
    {deadline && !options.length && <p role="alert">Время не существует в выбранном часовом поясе.</p>}
    {options.length > 1 && <label>Смещение часов<select required name={`${index}-choice`} value={choice} onChange={event => setChoice(event.target.value)}><option value="">Выберите время</option>{options.map(value => <option key={value} value={value}>{value}</option>)}</select></label>}
    <div className="work-fields"><label>Оценка, мин<input name={`${index}-estimated`} type="number" min={1} max={525600} defaultValue={task.estimated_minutes ?? ""} onChange={() => setEstimateKind("estimate")} /></label><label>Осталось работы, мин<input name={`${index}-remaining`} type="number" min={0} max={525600} defaultValue={task.remaining_minutes ?? ""} /></label></div>
    <label>Откуда продолжительность<select name={`${index}-kind`} value={estimateKind} onChange={event => setEstimateKind(event.target.value)}><option value="unknown">Не определена</option><option value="estimate">Оценка</option><option value="source">Указана в источнике</option></select></label>
  </fieldset>;
}
export function TaskProposalEditor({ proposal, chatId, onClose }: { proposal: { id: string; timezone: string; batch: { actions: ProposalAction[] } }; chatId: string; onClose: () => void }) {
  const action = useAction(); const client = useQueryClient();
  return <Modal title="Уточнить предложенные задачи" wide onClose={() => { if (!action.busy) onClose(); }}><form className="work-planning" onSubmit={event => {
    event.preventDefault(); const values = new FormData(event.currentTarget);
    void action.run(async () => {
      const actions = proposal.batch.actions.map((item, index) => {
        if (item.operation !== "task_create" || !item.task) return item;
        const numeric = (key: string) => values.get(`${index}-${key}`) === "" ? null : Number(values.get(`${index}-${key}`));
        const deadline = String(values.get(`${index}-deadline`) ?? "");
        return { ...item, estimate_kind: String(values.get(`${index}-kind`)), task: { ...item.task, title: String(values.get(`${index}-title`)), description: String(values.get(`${index}-description`)) || null, priority: String(values.get(`${index}-priority`)), deadline_at: deadline ? resolveLocalTime(deadline, proposal.timezone, String(values.get(`${index}-choice`) ?? ""), item.task.deadline_at ?? undefined) : null, estimated_minutes: numeric("estimated"), remaining_minutes: numeric("remaining") } };
      });
      await writeJson(`${aiBase}/proposals/${proposal.id}/revise`, "POST", { actions });
      await client.invalidateQueries({ queryKey: ["ai-proposals", chatId] }); onClose();
    }, "Новый просмотр подготовлен. Подтвердите его отдельно.");
  }}><h2>Уточнить предложенные задачи</h2><p>Правки создадут новый просмотр. Источники и связи сохраняются; создание потребует отдельного подтверждения.</p>{proposal.batch.actions.map((item, index) => item.operation === "task_create" && item.task ? <DraftFields key={index} task={item.task} kind={item.estimate_kind} index={index} timezone={proposal.timezone} /> : null)}<button className="primary-button" disabled={action.busy}>Подготовить новый просмотр</button><ActionFeedback {...action} /></form></Modal>;
}
