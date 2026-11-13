"use client";

import { useEffect, useRef, useState } from "react";
import { writeJson } from "@/shared/api";
import type { Block, Note } from "./notes";

type Draft = { title: string; parent: string; blocks: Block[] };
const fromNote = (note: Note): Draft => ({
  title: note.title,
  parent: note.parent_id ?? "",
  blocks: note.document.blocks,
});
const same = (left: Draft, right: Draft) =>
  left.title.trim() === right.title.trim() && left.parent === right.parent &&
  JSON.stringify(left.blocks) === JSON.stringify(right.blocks);

export function useNoteDraft(
  note: Note,
  onDirtyChange: (dirty: boolean) => void,
  onSaved: (note: Note, complete?: boolean) => Promise<void>,
) {
  const [draft, setDraft] = useState(() => fromNote(note));
  const [version, setVersion] = useState(note.version);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [epoch, setEpoch] = useState(0);
  const current = useRef(draft);
  const confirmed = useRef(note);
  const dirtyFlag = useRef(false);
  const callbacks = useRef({ onDirtyChange, onSaved });
  const mounted = useRef(true);
  const flight = useRef<Promise<boolean> | null>(null);
  const savingDraft = useRef<Draft | null>(null);
  const flushAgain = useRef(false);
  useEffect(() => { callbacks.current = { onDirtyChange, onSaved }; }, [onDirtyChange, onSaved]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; callbacks.current.onDirtyChange(false); };
  }, []);

  function mark(value: boolean) {
    dirtyFlag.current = value;
    setDirty(value);
    callbacks.current.onDirtyChange(value);
  }
  function update(changes: Partial<Draft>) {
    const next = { ...current.current, ...changes };
    current.current = next;
    setDraft(next);
    mark(!same(next, fromNote(confirmed.current)) || Boolean(flight.current));
  }
  function adopt(fresh: Note) {
    confirmed.current = fresh;
    current.current = fromNote(fresh);
    setDraft(current.current);
    setVersion(fresh.version);
    setError("");
    mark(false);
    setEpoch(value => value + 1);
  }
  async function run() {
    setSaving(true);
    setError("");
    try {
      do {
        flushAgain.current = false;
        const snapshot = current.current;
        savingDraft.current = snapshot;
        let base = confirmed.current;
        if (!snapshot.title.trim()) throw new Error("Укажи название страницы.");
        if (snapshot.title.trim() !== base.title || snapshot.parent !== (base.parent_id ?? "")) {
          base = await writeJson<Note>(`/api/v1/notes/pages/${note.id}`, "PATCH", {
            title: snapshot.title.trim(), parent_id: snapshot.parent || null,
            expected_version: base.version,
          });
          confirmed.current = base;
          if (!mounted.current) return false;
          setVersion(base.version);
        }
        const result = await writeJson<{ version: number; document: Note["document"] }>(
          `/api/v1/notes/pages/${note.id}/document`, "PUT", {
            expected_version: base.version,
            document: { schema_version: 1, blocks: snapshot.blocks },
          },
        );
        if (!mounted.current) return false;
        const saved = { ...base, ...result };
        confirmed.current = saved;
        setVersion(saved.version);
        const complete = same(current.current, fromNote(saved));
        if (complete) { current.current = fromNote(saved); setDraft(current.current); }
        mark(!complete);
        await callbacks.current.onSaved(saved, complete);
      } while (mounted.current && flushAgain.current && dirtyFlag.current);
      return !dirtyFlag.current;
    } catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : "Не удалось сохранить страницу.");
        mark(true);
      }
      flushAgain.current = false;
      return false;
    } finally {
      savingDraft.current = null;
      flight.current = null;
      if (mounted.current) setSaving(false);
    }
  }
  function save() {
    if (note.trashed_at) return Promise.resolve(false);
    if (flight.current) {
      if (savingDraft.current && !same(current.current, savingDraft.current)) flushAgain.current = true;
      return flight.current;
    }
    if (!dirtyFlag.current) return Promise.resolve(true);
    // Start in a microtask so a synchronous validation failure still releases the flight lock.
    flight.current = Promise.resolve().then(run);
    return flight.current;
  }
  return { ...draft, version, dirty, saving, error, epoch, update, adopt, discard: () => adopt(confirmed.current), save };
}
