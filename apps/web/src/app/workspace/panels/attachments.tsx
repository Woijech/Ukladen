"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Pager, QueryState, useAction } from "@/shared/ui";
import type { Material } from "./resources";

export function PageAttachments({
  pageId,
  readonly,
}: {
  pageId: string;
  readonly: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [optionOffset, setOptionOffset] = useState(0);
  const client = useQueryClient();
  const action = useAction();
  const base = `/api/v1/relations/pages/${pageId}/materials`;
  const links = useQuery({
    queryKey: ["page-materials", pageId, offset],
    queryFn: ({ signal }) =>
      requestJson<{ items: Material[] }>(`${base}?limit=50&offset=${offset}`, {
        signal,
      }),
    enabled: open,
  });
  const materials = useQuery({
    queryKey: ["attachment-options", optionOffset],
    queryFn: ({ signal }) =>
      requestJson<{ items: Material[] }>(
        `/api/v1/materials?limit=50&offset=${optionOffset}`,
        { signal },
      ),
    enabled: open && !readonly,
  });
  return (
    <section className="note-relations">
      <button
        className="text-action"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "Скрыть материалы ↑" : "Связанные материалы ↓"}
      </button>
      {open && (
        <>
          <QueryState
            pending={links.isPending}
            error={links.error}
            retry={() => void links.refetch()}
          />
          {links.data?.items.map((material) => (
            <div className="relation-row" key={material.id}>
              <div>
                <strong>{material.title}</strong>
                {material.trashed_at ? (
                  <small> · в корзине</small>
                ) : material.kind === "link" && material.url ? (
                  <a
                    className="text-action"
                    href={material.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {" "}
                    Открыть ↗
                  </a>
                ) : (
                  material.status !== "uploading" && (
                    <a
                      className="text-action"
                      href={`/api/v1/materials/${material.id}/content`}
                      download
                    >
                      {" "}
                      Скачать
                    </a>
                  )
                )}
              </div>
              <button
                type="button"
                className="text-action"
                disabled={action.busy}
                onClick={() =>
                  void action.run(async () => {
                    await writeJson(`${base}/${material.id}`, "DELETE");
                    await client.invalidateQueries({
                      queryKey: ["page-materials", pageId],
                    });
                  }, "Связь удалена. Материал сохранён.")
                }
              >
                Убрать связь
              </button>
            </div>
          ))}
          {links.data && !links.data.items.length && (
            <p className="muted">К странице пока не прикреплены материалы.</p>
          )}
          {links.data && (offset || links.data.items.length === 50) ? (
            <Pager
              offset={offset}
              count={links.data.items.length}
              onChange={setOffset}
            />
          ) : null}
          {!readonly && (
            <>
              <label className="field-label" htmlFor="attach-material">
                Добавить из библиотеки
              </label>
              <select
                className="ui-input"
                id="attach-material"
                disabled={action.busy || materials.isPending}
                defaultValue=""
                onChange={(event) => {
                  const id = event.target.value;
                  event.target.value = "";
                  if (id)
                    void action.run(async () => {
                      await writeJson(`${base}/${id}`, "PUT");
                      await client.invalidateQueries({
                        queryKey: ["page-materials", pageId],
                      });
                    });
                }}
              >
                <option value="">Выбрать материал…</option>
                {materials.data?.items.map((material) => (
                  <option key={material.id} value={material.id}>
                    {material.title}
                  </option>
                ))}
              </select>
              <QueryState
                pending={false}
                error={materials.error}
                retry={() => void materials.refetch()}
              />
              {materials.data &&
              (optionOffset || materials.data.items.length === 50) ? (
                <Pager
                  offset={optionOffset}
                  count={materials.data.items.length}
                  onChange={setOptionOffset}
                />
              ) : null}
            </>
          )}
          <ActionFeedback {...action} />
        </>
      )}
    </section>
  );
}
