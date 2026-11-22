"use client";

import { useQuery } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, useAction } from "@/shared/ui";
import { aiBase } from "./ai-api";
import "./source-index-status.css";

const labels: Record<string, string> = {
  pending: "Поиск по смыслу: ожидает индексации",
  processing: "Поиск по смыслу: готовим фрагменты",
  ready: "Поиск по смыслу готов",
  failed: "Не удалось подготовить поиск по смыслу",
  unavailable: "Поиск по смыслу не настроен · доступен поиск по словам",
};

export function SourceIndexStatus({ source, id }: { source: "page" | "material"; id: string }) {
  const action = useAction();
  const query = useQuery({
    queryKey: ["ai-index-state", source, id], retry: false,
    queryFn: ({ signal }) => requestJson<{ status: string }>(`${aiBase}/sources/${source}/${id}/index`, { signal }),
    refetchInterval: query => ["pending", "processing"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  return <div className="source-index-status">
    <p className="muted" role="status">{query.data ? labels[query.data.status] ?? "Проверяем готовность поиска" : query.error ? "Статус поиска по смыслу недоступен" : "Проверяем готовность поиска…"}</p>
    <details><summary>Как AI читает этот источник</summary><p>Сначала извлекается текст. Затем фрагменты индексируются для поиска по смыслу. При вопросе AI получает найденные фрагменты, а не весь документ. Для чтения целиком выбери источник и включи «Полный разбор» в чате.</p></details>
    {query.error && <button type="button" className="text-action" onClick={() => void query.refetch()}>Обновить статус поиска</button>}
    {query.data?.status === "failed" && <button type="button" className="text-action" disabled={action.busy} onClick={() => void action.run(async () => {
      await writeJson(`${aiBase}/sources/${source}/${id}/index/retry`, "POST");
      await query.refetch();
    })}>Повторить обработку</button>}
    <ActionFeedback {...action} />
  </div>;
}
