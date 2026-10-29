"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, Pager, QueryState, useAction } from "@/shared/ui";
import type { PlanningTask } from "./task-planning";
import type { Source } from "./panels/ai-api";
import { SourceViewer } from "./panels/ai-sources";

type Page = { id: string; title: string; trashed_at?: string | null };
export function TaskRelations({ task, onSelectTask, onOpenPage }: { task: PlanningTask; onSelectTask: (id: string) => void; onOpenPage: (id: string) => void }) {
  const client = useQueryClient(); const action = useAction();
  const [picker, setPicker] = useState<"tasks" | "pages" | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [offset, setOffset] = useState(0);
  const [dependencyOffset, setDependencyOffset] = useState(0); const [pageOffset, setPageOffset] = useState(0);
  const dependencies = useQuery({ queryKey: ["task-dependencies", task.id, dependencyOffset], queryFn: ({ signal }) => requestJson<{ items: PlanningTask[]; has_unresolved_dependencies: boolean }>(`/api/v1/tasks/${task.id}/dependencies?limit=20&offset=${dependencyOffset}`, { signal }) });
  const pages = useQuery({ queryKey: ["task-pages", task.id, pageOffset], queryFn: ({ signal }) => requestJson<{ items: Page[] }>(`/api/v1/relations/tasks/${task.id}/pages?limit=20&offset=${pageOffset}`, { signal }) });
  const origin = useQuery({ queryKey: ["task-origin", task.id], queryFn: ({ signal }) => requestJson<{ sources: Source[]; estimate_kind: string; uncertainties: string[] } | null>(`/api/v1/tasks/${task.id}/origin`, { signal }) });
  const candidates = useQuery({ queryKey: ["task-relation-picker", picker, offset], enabled: !!picker, queryFn: ({ signal }) => requestJson<{ items: Page[] }>(`${picker === "tasks" ? "/api/v1/tasks" : "/api/v1/notes/pages"}?limit=20&offset=${offset}`, { signal }) });
  async function refresh() { await Promise.all(["task-detail", "tasks-list", "task-dependencies", "task-pages"].map(key => client.invalidateQueries({ queryKey: [key] }))); }
  function link(id: string, remove = false) { return action.run(async () => {
    if (picker === "tasks" || (remove && dependencies.data?.items.some(item => item.id === id))) {
      await writeJson(`/api/v1/tasks/${task.id}/dependencies/${id}`, remove ? "DELETE" : "PUT", { expected_version: task.version });
    } else {
      await writeJson(`/api/v1/relations/tasks/${task.id}/pages/${id}`, remove ? "DELETE" : "PUT");
    }
    setPicker(null); await refresh();
  }); }
  return <section className="task-relations" aria-label="Связи задачи">
    <h3>Предшественники</h3><p className="task-muted">Планировщик соблюдает порядок зависимостей. Ручное завершение остаётся доступным.</p>
    <QueryState pending={dependencies.isPending} error={dependencies.error} retry={() => void dependencies.refetch()} />
    {dependencies.data?.has_unresolved_dependencies && <p role="status">Есть незавершённые или недоступные предшественники.</p>}
    <ul>{dependencies.data?.items.map(item => <li key={item.id} className="task-relation-row"><button className="text-action" onClick={() => onSelectTask(item.id)}>{item.title}</button><button className="text-action" disabled={action.busy} onClick={() => void link(item.id, true)}>Убрать зависимость</button></li>)}</ul>
    <Pager offset={dependencyOffset} count={dependencies.data?.items.length ?? 0} size={20} onChange={setDependencyOffset} />
    <button className="task-secondary" onClick={() => { setPicker("tasks"); setOffset(0); }}>Добавить предшественника</button>
    <h3>Связанные страницы</h3><QueryState pending={pages.isPending} error={pages.error} retry={() => void pages.refetch()} />
    <ul>{pages.data?.items.map(page => <li key={page.id} className="task-relation-row"><button className="text-action" onClick={() => onOpenPage(page.id)}>{page.title}</button><button className="text-action" disabled={action.busy} onClick={() => void action.run(async () => { await writeJson(`/api/v1/relations/tasks/${task.id}/pages/${page.id}`, "DELETE"); await refresh(); })}>Убрать связь</button></li>)}</ul>
    <Pager offset={pageOffset} count={pages.data?.items.length ?? 0} size={20} onChange={setPageOffset} />
    <button className="task-secondary" onClick={() => { setPicker("pages"); setOffset(0); }}>Связать страницу</button><p className="task-muted">Удаление связи не меняет страницу или задачу.</p>
    <QueryState pending={origin.isPending} error={origin.error} retry={() => void origin.refetch()} />
    {origin.data && <><h3>Происхождение задачи</h3><p>{origin.data.estimate_kind === "estimate" ? "Продолжительность предложена AI; это оценка." : origin.data.estimate_kind === "source" ? "Продолжительность указана в источнике." : "Продолжительность не определена."}</p>{origin.data.uncertainties.map((text, index) => <p key={index}>{text}</p>)}<ul>{origin.data.sources.map((item, index) => <li key={index}><button className="text-action" onClick={() => item.source === "page" ? onOpenPage(item.id) : setSource(item)}>{item.title}</button> · версия {item.version}<br /><small>{item.locator}</small></li>)}</ul><p className="task-muted">Это ссылки на использованные версии. Чекбоксы и записи не синхронизируются с задачей.</p></>}
    {picker && <Modal title={picker === "tasks" ? "Выбрать предшественника" : "Выбрать страницу"} onClose={() => setPicker(null)}><h2>{picker === "tasks" ? "Выбрать предшественника" : "Выбрать страницу"}</h2><QueryState pending={candidates.isPending} error={candidates.error} retry={() => void candidates.refetch()} />{candidates.data?.items.filter(item => picker !== "tasks" || item.id !== task.id).map(item => <button key={item.id} className="task-picker-item" disabled={action.busy} onClick={() => void link(item.id)}>{item.title}</button>)}<Pager offset={offset} count={candidates.data?.items.length ?? 0} size={20} onChange={setOffset} /><ActionFeedback {...action} /></Modal>}
    {source && <SourceViewer source={source} onClose={() => setSource(null)} />}<ActionFeedback {...action} />
  </section>;
}
