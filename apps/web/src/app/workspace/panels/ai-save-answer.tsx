"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { writeJson } from "@/shared/api";
import { ActionFeedback, Modal, useAction } from "@/shared/ui";
import type { Message } from "./ai-api";

export function SaveAnswer({ message, onOpenPage }: { message: Message; onOpenPage: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [savedId, setSavedId] = useState<string | null>(null);
  const action = useAction();
  const client = useQueryClient();
  return <>
    {savedId ? <button type="button" className="text-action" onClick={() => onOpenPage(savedId)}>Открыть сохранённую страницу</button> : <button type="button" className="text-action" onClick={() => { setTitle(message.content.split("\n").find(line => line.trim())?.replace(/^#+\s*/, "").slice(0, 200) ?? "Ответ AI"); setOpen(true); }}>Сохранить как страницу</button>}
    {open && <Modal title="Сохранить ответ как страницу" onClose={() => { if (!action.busy) setOpen(false); }}>
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
        const page = await writeJson<{ id: string }>("/api/v1/notes/pages", "POST", { title: title.trim(), content: message.content });
        await client.invalidateQueries({ queryKey: ["pages"] });
        setSavedId(page.id); setOpen(false);
      }); }}><h2>Ответ станет твоей страницей</h2><p>Сохраним текст{message.incomplete ? ", включая доступную часть незавершённого ответа" : ""}. Его можно будет редактировать в заметках.</p>
      <label htmlFor="ai-save-title">Название страницы</label><input id="ai-save-title" required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} />
      <div className="modal-actions"><button type="button" className="secondary-button" disabled={action.busy} onClick={() => setOpen(false)}>Отмена</button><button className="primary-button" disabled={action.busy || !title.trim()}>{action.busy ? "Сохраняю…" : "Сохранить страницу"}</button></div><ActionFeedback {...action} /></form>
    </Modal>}
  </>;
}
