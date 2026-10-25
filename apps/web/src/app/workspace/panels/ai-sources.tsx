"use client";

import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { csrfToken, requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, Pager, QueryState, useAction } from "@/shared/ui";
import { aiBase, emptyScope, type Scope, type Source } from "./ai-api";

const kinds = {
  page_ids: "Страницы",
  material_ids: "Материалы",
  database_ids: "Базы данных",
};
type Kind = keyof typeof kinds;

export function SourcePicker({
  value,
  onSave,
  onClose,
}: {
  value: Scope | null;
  onSave: (value: Scope | null) => void;
  onClose: () => void;
}) {
  const [automatic, setAutomatic] = useState(value === null);
  const [scope, setScope] = useState(value ?? emptyScope());
  const [kind, setKind] = useState<Kind>("page_ids");
  const [offset, setOffset] = useState(0);
  const count =
    scope.page_ids.length +
    scope.material_ids.length +
    scope.database_ids.length;
  const paths = {
    page_ids: "/api/v1/notes/pages",
    material_ids: "/api/v1/materials",
    database_ids: "/api/v1/workspace/databases",
  };
  const list = useQuery({
    queryKey: ["ai-source-options", kind, offset],
    enabled: !automatic,
    queryFn: ({ signal }) =>
      requestJson<{ items: { id: string; title?: string; name?: string }[] }>(
        `${paths[kind]}?limit=50&offset=${offset}&trashed=false`,
        { signal },
      ),
  });
  return (
    <Modal title="Источники для запроса" onClose={onClose}>
      <h2>Где искать ответ</h2>
      <label className="checkbox-label">
        <input
          type="checkbox"
          checked={automatic}
          onChange={(event) => setAutomatic(event.target.checked)}
        />
        Все мои источники автоматически
      </label>
      <p className="muted">
        AI выбирает нужные данные. Ограничение действует только на отправляемый
        запрос.
      </p>
      {!automatic && (
        <>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={scope.calendar}
              onChange={(event) =>
                setScope({ ...scope, calendar: event.target.checked })
              }
            />
            Мой календарь
          </label>
          <label className="field-label">
            Тип источника
            <select
              aria-label="Тип источника"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as Kind);
                setOffset(0);
              }}
            >
              {Object.entries(kinds).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <p>Выбрано: {count}</p>
          <QueryState
            pending={list.isPending}
            error={list.error}
            retry={() => void list.refetch()}
          />
          <div className="ai-source-options">
            {list.data?.items.map((item) => (
              <label key={item.id} className="checkbox-label">
                <input
                  type="checkbox"
                  checked={scope[kind].includes(item.id)}
                  onChange={(event) =>
                    setScope({
                      ...scope,
                      [kind]: event.target.checked
                        ? [...scope[kind], item.id]
                        : scope[kind].filter((id) => id !== item.id),
                    })
                  }
                />
                {item.title ?? item.name}
              </label>
            ))}
          </div>
          <Pager
            offset={offset}
            count={list.data?.items.length ?? 0}
            size={50}
            onChange={setOffset}
          />
          {!count && !scope.calendar && (
            <p className="muted">
              Без выбранных источников AI не сможет читать данные пространства.
            </p>
          )}
        </>
      )}
      <button
        className="primary-button"
        onClick={() => {
          onSave(automatic ? null : scope);
          onClose();
        }}
      >
        Применить
      </button>
    </Modal>
  );
}

type Evidence = {
  status: string;
  data: unknown;
  sources: Source[];
  coverage: string;
  warnings: string[];
  next_offset: number | null;
};
const warnings: Record<string, string> = {
  snippets_are_not_full_sources: "Показаны фрагменты, а не весь документ.",
  extracted_text_only_no_ocr:
    "Извлечённый текст, без распознавания изображений.",
  semantic_unavailable_lexical_fallback: "Поиск по смыслу временно недоступен. Использован поиск по словам.",
  index_pending_or_unavailable: "Индекс ещё не готов. Доступные результаты могут быть неполными.",
  lexical_search_only: "Поиск по словам. Семантический поиск пока недоступен.",
  record_preview_values_bounded:
    "Показана часть полей; длинные значения сокращены.",
  text_unavailable_or_not_extracted: "Текст ещё не извлечён или недоступен.",
  selected_block_only: "Только выбранный блок.",
};
const labels: Record<string, string> = {
  title: "Название",
  text: "Текст",
  name: "Название",
  value: "Значение",
  properties: "Поля",
  views: "Представления",
  entries: "События",
  records: "Записи",
  values: "Значения",
  starts_at: "Начало",
  ends_at: "Конец",
  location: "Место",
  busy: "Занятое время",
  blocks_time: "Занятое время",
  date: "Дата",
  kind: "Тип",
  status: "Статус",
  description: "Описание",
};

function SourceContent({ value }: { value: unknown }): ReactNode {
  if (value === null || value === undefined) return null;
  if (typeof value === "string" || typeof value === "number")
    return <span>{String(value)}</span>;
  if (typeof value === "boolean") return <span>{value ? "Да" : "Нет"}</span>;
  if (Array.isArray(value))
    return (
      <div className="ai-source-items">
        {value.length ? (
          value.map((item, index) => (
            <div key={index}>
              <SourceContent value={item} />
            </div>
          ))
        ) : (
          <p>Нет данных в этом фрагменте.</p>
        )}
      </div>
    );
  if (typeof value === "object")
    return (
      <dl className="ai-source-fields">
        {Object.entries(value)
          .filter(([key]) => key in labels)
          .map(([key, item]) => (
            <div key={key}>
              <dt>{labels[key]}</dt>
              <dd>
                <SourceContent value={item} />
              </dd>
            </div>
          ))}
      </dl>
    );
  return null;
}

export function SourceViewer({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  const action = useAction();
  const indexed = source.source === "page" || source.source === "material";
  const indexState = useQuery({
    queryKey: ["ai-index-state", source.source, source.id],
    enabled: indexed,
    queryFn: ({ signal }) => requestJson<{ status: string }>(`${aiBase}/sources/${source.source}/${source.id}/index`, { signal }),
    refetchInterval: (query) => ["pending", "processing"].includes(query.state.data?.status ?? "") ? 5000 : false,
  });
  const indexLabels: Record<string, string> = { pending: "Ожидает обработки", processing: "Индексируется", ready: "Готов к поиску по смыслу", failed: "Не удалось построить индекс", unavailable: "Доступен поиск по словам" };
  const location = source.locator.match(/(?:^|;)(page|slide):(\d+)/);
  const initialOffset = source.locator.match(/(?:chars|characters):(\d+)/)?.[1];
  const [offset, setOffset] = useState(Number(initialOffset ?? 0));
  const [previous, setPrevious] = useState<number[]>([]);
  const query = useQuery({
    queryKey: [
      "ai-source-preview",
      source.source,
      source.id,
      source.parent_id,
      offset,
    ],
    staleTime: 0,
    gcTime: 0,
    queryFn: async ({ signal }) => {
      let payload: Record<string, unknown>;
      if (source.source === "page") payload = { page_id: source.id, offset };
      else if (source.source === "material")
        payload = { material_id: source.id, offset };
      else if (source.source === "database")
        payload = { database_id: source.id, offset };
      else if (
        source.source === "database_record" ||
        source.source === "record_date"
      )
        payload = {
          database_id: source.parent_id,
          record_id: source.id.split(":")[0],
          offset,
        };
      else {
        const dates = source.locator.match(
          /^dates:(\d{4}-\d{2}-\d{2}):(\d{4}-\d{2}-\d{2})$/,
        );
        if (!dates)
          throw new Error(
            "Расположение источника недоступно. Найдите его в календаре.",
          );
        payload = { date_from: dates[1], date_to: dates[2], offset, limit: 20 };
      }
      const token = await csrfToken(signal);
      return requestJson<Evidence>(`${aiBase}/sources/read`, {
        method: "POST",
        signal,
        headers: { "Content-Type": "application/json", "X-CSRF-Token": token },
        body: JSON.stringify(payload),
      });
    },
  });
  const data = query.data;
  const current = data?.sources.find(
    (item) => item.id === source.id || item.id === source.id.split(":")[0],
  );
  return (
    <Modal title="Просмотр источника" onClose={onClose} wide>
      <h2>{current?.title ?? "Источник ответа"}</h2>
      {location && <p>{location[1] === "page" ? "Страница PDF" : "Слайд"} {location[2]}</p>}
      {indexState.data && <p className="muted" role="status">{indexLabels[indexState.data.status] ?? "Обрабатывается"}</p>}
      {indexState.data?.status === "failed" && <button className="secondary-button" disabled={action.busy} onClick={() => void action.run(async () => {
        await writeJson(`${aiBase}/sources/${source.source}/${source.id}/index/retry`, "POST");
        await indexState.refetch();
      })}>Повторить обработку</button>}
      <ActionFeedback {...action} />
      <p className="muted">
        Текущее содержимое. В ответе использовалась версия {source.version}.
        {current && current.version !== source.version
          ? " Источник изменился после ответа."
          : ""}
      </p>
      <QueryState
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {data &&
        (data.status !== "ok" ? (
          <p role="status">
            Источник недоступен или ещё не готов.{" "}
            {data.warnings
              .map((item) => warnings[item] ?? "Попробуйте открыть его позже.")
              .join(" ")}
          </p>
        ) : (
          <>
            {data.coverage === "partial" && (
              <p className="muted">Показан ограниченный фрагмент.</p>
            )}
            {data.warnings.length > 0 && (
              <p className="muted">
                {data.warnings
                  .map(
                    (item) =>
                      warnings[item] ??
                      "Есть ограничения полноты или актуальности источника.",
                  )
                  .join(" ")}
              </p>
            )}
            <div className="ai-source-content">
              <SourceContent value={data.data} />
            </div>
            <div className="panel-toolbar">
              <button
                className="secondary-button"
                disabled={!previous.length}
                onClick={() => {
                  setOffset(previous.at(-1)!);
                  setPrevious(previous.slice(0, -1));
                }}
              >
                Назад
              </button>
              <button
                className="secondary-button"
                disabled={data.next_offset === null}
                onClick={() => {
                  setPrevious([...previous, offset]);
                  setOffset(data.next_offset!);
                }}
              >
                Следующий фрагмент
              </button>
            </div>
          </>
        ))}
    </Modal>
  );
}
