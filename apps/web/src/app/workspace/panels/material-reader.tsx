"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { request, requestJson } from "@/shared/api";
import { Modal, QueryState } from "@/shared/ui";
import { SourceIndexStatus } from "./source-index-status";
import type { Material } from "./resources";
import "./material-reader.css";

type TextExcerpt = { text: string; offset: number; total_characters: number; version: number };
const pageSize = 2000;

function PdfReader({ id, title }: { id: string; title: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = "";
    request(`/api/v1/materials/${id}/content`, { signal: controller.signal })
      .then(response => response.blob())
      .then(blob => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
        setUrl(objectUrl);
      })
      .catch(caught => { if (!controller.signal.aborted) setError(caught); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [id, attempt]);
  return <>
    <QueryState pending={!url && !error} error={error} retry={() => { setError(null); setAttempt(value => value + 1); }} />
    {url && <iframe className="material-reader-pdf" src={url} title={title} />}
    <p className="material-reader-hint">Если браузер не показывает PDF, скачай оригинал и открой его на устройстве.</p>
  </>;
}

export function MaterialReader({ material, onClose }: { material: Material; onClose: () => void }) {
  const [offset, setOffset] = useState(0);
  const [fontSize, setFontSize] = useState(18);
  const body = useRef<HTMLDivElement>(null);
  const pdf = material.filename?.toLowerCase().endsWith(".pdf");
  const metadata = useQuery({
    queryKey: ["material-reader", material.id],
    queryFn: ({ signal }) => requestJson<Material>(`/api/v1/materials/${material.id}`, { signal }),
    initialData: material,
    refetchInterval: query => ["pending", "processing"].includes(query.state.data?.status ?? "") ? 3000 : false,
    gcTime: 0,
  });
  const current = metadata.data;
  const readable = current.status === "ready" && !current.trashed_at && !metadata.error;
  const text = useQuery({
    queryKey: ["material-text", material.id, current.version, offset],
    queryFn: ({ signal }) => requestJson<TextExcerpt | null>(`/api/v1/materials/${material.id}/text?offset=${offset}&limit=${pageSize}`, { signal }),
    enabled: !pdf && readable,
    gcTime: 0,
  });
  const total = text.data?.total_characters ?? 0;
  function move(value: number) { setOffset(value); body.current?.scrollTo(0, 0); }
  return <Modal title={`Чтение: ${material.title}`} onClose={onClose} wide className="material-reader">
    <header className="material-reader-header">
      <span className="material-reader-format">{material.filename?.split(".").at(-1)?.toUpperCase()}</span>
      <div><p className="material-reader-eyebrow">Библиотека · Только чтение</p><h2>{current.title}</h2><p className="muted">{material.filename}</p></div>
    </header>
    <div className="material-reader-toolbar">
      <span className="muted">{pdf ? "Исходный документ" : "Текст документа · без оформления оригинала"}</span>
      <div className="row-actions">
        {!pdf && <div className="material-reader-font" role="group" aria-label="Размер текста">
          <button type="button" className="secondary-button" aria-label="Уменьшить текст" disabled={fontSize <= 16} onClick={() => setFontSize(value => value - 2)}>А−</button>
          <button type="button" className="secondary-button" aria-label="Увеличить текст" disabled={fontSize >= 24} onClick={() => setFontSize(value => value + 2)}>А+</button>
        </div>}
        <a className="secondary-button" href={`/api/v1/materials/${material.id}/content`} download>Скачать оригинал</a>
      </div>
    </div>
    {readable && <SourceIndexStatus source="material" id={material.id} />}
    <div ref={body} className="material-reader-body" tabIndex={0} aria-label="Содержимое документа">
      <QueryState pending={false} error={metadata.error} retry={() => void metadata.refetch()} />
      {!metadata.error && (current.trashed_at ? <p role="status">Материал в корзине. Восстанови его, чтобы читать.</p> : pdf ? <PdfReader id={material.id} title={current.title} /> : <>
        {!readable && <div className="material-reader-message" role="status"><h3>{current.status === "failed" ? "Текст недоступен" : "Готовим документ к чтению"}</h3><p>{current.status === "failed" ? "Не удалось извлечь текст. Ты можешь скачать оригинал." : "Окно обновится автоматически после обработки файла."}</p></div>}
        {readable && <>
          <QueryState pending={text.isPending} error={text.error} retry={() => void text.refetch()} />
          {!text.isPending && !text.error && (!text.data?.text ? <p className="material-reader-message">В документе нет доступного текста. Скачай оригинал для просмотра.</p> : <article className="material-reader-sheet" style={{ fontSize }} aria-label="Текст документа">{text.data.text}</article>)}
        </>}
      </>)}
    </div>
    {!pdf && <footer className="material-reader-footer">
      <span className="muted" aria-live="polite">{total ? `Фрагмент ${Math.floor(offset / pageSize) + 1} из ${Math.ceil(total / pageSize)}` : "Чтение документа"}</span>
      <div className="row-actions">
        <button type="button" className="secondary-button" disabled={!offset || text.isFetching} onClick={() => move(Math.max(0, offset - pageSize))}>Назад</button>
        <button type="button" className="secondary-button" disabled={!total || offset + pageSize >= total || text.isFetching || !!text.error} onClick={() => move(offset + pageSize)}>Далее</button>
      </div>
    </footer>}
  </Modal>;
}
