"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, QueryState, useAction } from "@/shared/ui";
import { NoteBlocks } from "./note-blocks";
import type { Note } from "./notes";

type Revision = Pick<Note, "version" | "title"> & { saved_at: string };

export function NoteHistory({ note, onClose, onRestored }: {
  note: Note; onClose: () => void; onRestored: (note: Note) => void;
}) {
  const [selected, setSelected] = useState<number | null>(null);
  const [confirm, setConfirm] = useState(false);
  const action = useAction();
  const query = useQuery({ queryKey: ["page-revisions", note.id], staleTime: 0,
    queryFn: ({ signal }) => requestJson<Revision[]>(`/api/v1/notes/pages/${note.id}/revisions?limit=50`, { signal }) });
  const revision = query.data?.find(item => item.version === selected) ?? query.data?.[0];
  const detail = useQuery({ queryKey: ["page-revision", note.id, revision?.version], enabled: !!revision,
    queryFn: ({ signal }) => requestJson<Revision & Pick<Note, "document">>(`/api/v1/notes/pages/${note.id}/revisions/${revision!.version}`, { signal }) });
  return <Modal title="История страницы" wide onClose={() => { if (!action.busy) onClose(); }}>
    <div className="note-history"><header><h2>История страницы</h2><p>Последние 50 сохранений. Восстановление создаст новую версию.</p></header>
      <QueryState pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
      {query.data?.length === 0 && <p>История появится после сохранения страницы.</p>}
      {revision && <div className="note-history-layout"><nav aria-label="Сохранения страницы">{query.data?.map(item => <button type="button" key={item.version} aria-pressed={item.version === revision.version} disabled={action.busy} onClick={() => { setSelected(item.version); setConfirm(false); }}>
        <strong>{new Date(item.saved_at).toLocaleString("ru")}</strong><span>Версия {item.version}{item.version === note.version ? " · текущая" : ""}</span></button>)}</nav>
        <article><h3>{revision.title}</h3><QueryState pending={detail.isPending} error={detail.error} retry={() => void detail.refetch()} />{detail.data && <NoteBlocks blocks={detail.data.document.blocks} readonly disabled onChange={() => {}} />}</article></div>}
      {revision && revision.version !== note.version && !note.trashed_at && <footer>{confirm ? <><p>Восстановить выбранный текст и название? Текущая версия останется в истории.</p><button type="button" className="primary-button" disabled={action.busy} onClick={() => void action.run(async () => {
        const saved = await writeJson<Note>(`/api/v1/notes/pages/${note.id}/revisions/${revision.version}/restore`, "POST", { expected_version: note.version });
        onRestored(saved); onClose();
      })}>Подтвердить восстановление</button><button type="button" className="secondary-button" disabled={action.busy} onClick={() => setConfirm(false)}>Отмена</button></> : <button type="button" className="primary-button" onClick={() => setConfirm(true)}>Восстановить эту версию</button>}</footer>}
      <ActionFeedback {...action} />
    </div>
  </Modal>;
}
