"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, useAction } from "@/shared/ui";

type Preview = { digest: string; pages: number; databases: number; records: number; views: number; root_page_id: string | null };
const base = "/api/v1/workspace/transfer";
const limit = 32 * 1024 * 1024;

export function WorkspaceTransfer({ onBusyChange }: { onBusyChange: (busy: boolean) => void }) {
  const action = useAction();
  const client = useQueryClient();
  const [archive, setArchive] = useState<unknown>(null);
  const [filename, setFilename] = useState("");
  const [title, setTitle] = useState("Импортированные страницы");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [complete, setComplete] = useState(false);
  useEffect(() => { onBusyChange(action.busy); return () => onBusyChange(false); }, [action.busy, onBusyChange]);
  return <section className="panel setting-section" aria-label="Перенос страниц и баз">
    <div><h2>Страницы с собой</h2><p className="muted">Страницы, базы, связи и виды — одним JSON-файлом, включая корзину.</p>
      <p className="muted">Файлы, календарь, задачи, коллекции и история не входят. Для полного восстановления нужна резервная копия сервера.</p></div>
    <div className="ai-action-buttons">
      <button className="secondary-button" disabled={action.busy} onClick={() => void action.run(async () => {
        const value = await requestJson<{ archive: unknown }>(`${base}/export`);
        const url = URL.createObjectURL(new Blob([JSON.stringify(value)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = `ukladen-pages-${new Date().toISOString().slice(0, 10)}.json`; link.click();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      }, "Файл переноса подготовлен")}>Скачать JSON</button>
      <label className="secondary-button avatar-file-label">Импортировать JSON<input className="sr-only" type="file" accept="application/json,.json" disabled={action.busy} onChange={event => {
        const file = event.target.files?.[0]; event.target.value = ""; if (!file) return;
        void action.run(async () => {
          if (!file.size || file.size > limit + 4096) throw new Error("Выбери JSON-файл размером до 32 МБ.");
          let value: unknown;
          try { value = JSON.parse(await file.text()); } catch { throw new Error("Не удалось прочитать JSON-файл."); }
          if (!value || typeof value !== "object" || !("archive" in value)) throw new Error("Нужен файл переноса страниц и баз Ukladen.");
          setArchive(value.archive); setFilename(file.name); setTitle("Импортированные страницы"); setPreview(null); setComplete(false);
        });
      }} /></label>
    </div>
    <ActionFeedback {...action} />
    {archive !== null && <Modal title="Импорт страниц и баз" onClose={() => { if (!action.busy) setArchive(null); }}>
      <h2>{complete ? "Копия готова" : "Проверим файл"}</h2><p className="muted">{filename}</p>
      <p>Создадим новые базы и поместим страницы в отдельный раздел. Существующие записи сохранятся. Текстовые веб-ссылки останутся прежними.</p>
      <p className="muted">Вложения, задачи, календарь и история не переносятся. Недоступные ссылки на виды нужно исправить перед импортом.</p>
      <label className="field-label">Название раздела<input maxLength={200} value={title} disabled={action.busy || complete} onChange={event => { setTitle(event.target.value); setPreview(null); }} /></label>
      {preview && <p role="status">Страниц: {preview.pages} · баз: {preview.databases} · записей: {preview.records} · видов: {preview.views}</p>}
      <ActionFeedback {...action} />
      {!complete && <div className="ai-action-buttons"><button className="secondary-button" disabled={action.busy || !title.trim()} onClick={() => void action.run(async () => {
        setPreview(null); setPreview(await writeJson<Preview>(`${base}/preview`, "POST", { archive, title }));
      }, "Проверка пройдена. Пробный импорт отменён; можно создать копию.")}>Проверить файл</button>
      <button className="primary-button" disabled={action.busy || !preview} onClick={() => void action.run(async () => {
        const value = await writeJson<Preview>(`${base}/import`, "POST", { archive, title, digest: preview!.digest });
        setPreview(value); setComplete(true); await client.invalidateQueries();
      }, "Страницы и базы импортированы")}>Создать копию</button></div>}
      <button className="text-action" disabled={action.busy} onClick={() => setArchive(null)}>{complete ? "Готово" : "Отмена"}</button>
    </Modal>}
  </section>;
}
