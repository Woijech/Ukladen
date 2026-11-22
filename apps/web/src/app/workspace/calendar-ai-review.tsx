"use client";

import { useEffect, useRef } from "react";
import { ActionProposals, type Proposal } from "./panels/ai-actions";
import { calendarProposalItems, type CalendarReviewRequest } from "./ai-calendar-preview";
import { dateKey, prettyDate } from "./calendar-time";

export function CalendarAiReview({ review, phase, busy, onBusy, timezone, onBack, onDate, onProposal, onDecision, onOpenPage, onOpenEvent }: {
  review: CalendarReviewRequest; phase?: "applied" | "rejected";
  busy: boolean; onBusy: (busy: boolean) => void; timezone: string;
  onBack: () => void; onDate: (date: string) => void;
  onProposal: (proposal: Proposal) => void; onDecision: (proposal: Proposal) => void;
  onOpenPage: (id: string) => void;
  onOpenEvent: (id: string, startsAt: string, source: "personal" | "official") => Promise<void>;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [review.proposal.id]);
  const dates = [...new Set(calendarProposalItems(review.proposal).map(item => dateKey(new Date(item.starts_at), timezone)))].sort();
  return <section className="calendar-ai-review" aria-label="Подтверждение изменений AI" onKeyDown={event => {
    if (event.key === "Escape" && !event.defaultPrevented && !(event.target as HTMLElement).closest("dialog")) { event.preventDefault(); event.stopPropagation(); if (!phase && !busy) onBack(); }
  }}>
    <div className="calendar-ai-review-heading"><div>
      <h2 ref={heading} tabIndex={-1}>Проверь изменения на календаре</h2>
      <p role="status">{phase === "applied" ? "Изменения применены. Возвращаю в чат…" : phase === "rejected" ? "Предложение отклонено. Возвращаю в чат…" : "Пунктиром показан предпросмотр. До подтверждения ничего не меняется."}</p>
    </div><button type="button" className="secondary-button" disabled={!!phase || busy} onClick={onBack}>Вернуться в чат</button></div>
    <p className="calendar-ai-timezone">Часовой пояс календаря: {timezone}{timezone !== review.proposal.timezone && `; подробности предложения: ${review.proposal.timezone}`}</p>
    {dates.length > 1 && <div className="calendar-ai-dates" aria-label="Дни предложения">{dates.map(date => <button type="button" className="text-action" key={date} disabled={busy || !!phase} onClick={() => onDate(date)}>{prettyDate(date, timezone, { day: "numeric", month: "short" })}</button>)}</div>}
    <div className="calendar-ai-review-details"><ActionProposals chatId={review.chatId} runId={review.proposal.run_id} running={!!phase}
      calendarMode onlyProposalId={review.proposal.id} initialOffset={review.offset}
      onBusy={onBusy} onProposalChange={onProposal} onDecision={onDecision} onOpenPage={onOpenPage} onOpenEvent={onOpenEvent} /></div>
  </section>;
}
