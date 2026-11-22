import { createContext } from "react";
import type { Proposal } from "./panels/ai-actions";

export type CalendarReviewRequest = { chatId: string; proposal: Proposal; offset: number };
export const CalendarReviewContext = createContext<{
  open: (request: CalendarReviewRequest, automatic?: boolean) => void;
} | null>(null);
export type CalendarGhost = {
  id: string; title: string; starts_at: string; ends_at: string;
  phase: "before" | "after"; label: string;
};

export function calendarProposalItems(proposal: Proposal): CalendarGhost[] {
  const items: CalendarGhost[] = [];
  function add(id: string, title: string, start: string | undefined, end: string | undefined, phase: CalendarGhost["phase"], label: string) {
    if (!start || !Number.isFinite(Date.parse(start))) return;
    const ends = end ?? new Date(Date.parse(start) + 60_000).toISOString();
    if (!Number.isFinite(Date.parse(ends)) || Date.parse(ends) <= Date.parse(start)) return;
    items.push({ id, title, starts_at: start, ends_at: ends, phase, label });
  }
  proposal.effects.forEach((effect, index) => {
    if (effect.operation === "event_create" || effect.operation === "event_update") {
      if (effect.before) add(`${index}-before`, effect.before.title ?? "Событие", effect.before.starts_at, effect.before.ends_at, "before", "Сейчас");
      add(`${index}-after`, effect.after.title ?? "Событие", effect.after.starts_at, effect.after.ends_at, "after", effect.before ? "Будет изменено" : "Будет создано");
    } else if (effect.operation === "reminder_create") {
      add(`${index}-reminder`, "Напоминание", effect.after.due_at, undefined, "after", "Уведомление");
    } else if (effect.operation === "task_plan_apply") {
      for (const old of effect.after.previous_sessions ?? []) {
        if (effect.after.cancelled_sessions?.includes(old.id)) add(`${index}-old-${old.id}`, effect.after.task_titles?.[old.task_id] ?? "Работа над задачей", old.starts_at, old.ends_at, "before", "Будет отменено");
      }
      effect.after.sessions?.forEach((session, n) => add(`${index}-session-${n}`, effect.after.task_titles?.[session.task_id] ?? "Работа над задачей", session.starts_at, session.ends_at, "after", "Рабочая сессия"));
    } else if (effect.operation === "task_create" || effect.operation === "task_update") {
      const before = effect.before?.task ?? effect.before;
      const after = effect.after.task ?? effect.after;
      if (before?.deadline_at) add(`${index}-deadline-before`, before.title ?? "Срок задачи", before.deadline_at, undefined, "before", "Прежний срок");
      if (after.deadline_at) add(`${index}-deadline`, after.title ?? "Срок задачи", after.deadline_at, undefined, "after", "Срок задачи");
    }
  });
  return items;
}
