"use client";

import dynamic from "next/dynamic";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import symbol from "@/shared/assets/ukladen-avatar.png";
import { Modal } from "@/shared/ui";
import "./floating-assistant.css";

const ChatArea = dynamic(() => import("./panels/ai").then(module => module.ChatArea), {
  loading: () => <p className="floating-ai-loading" role="status">Загружаю помощника…</p>,
});

export function FloatingAssistant({ visible, onOpenPage, onOpenEvent }: {
  visible: boolean;
  onOpenPage: (id: string) => void;
  onOpenEvent: (id: string, startsAt: string, source: "personal" | "official") => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [opened, setOpened] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [pending, setPending] = useState<{ id: string | null } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  function close() {
    setOpen(false);
    requestAnimationFrame(() => trigger.current?.focus({ preventScroll: true }));
  }
  useEffect(() => {
    if (open && visible) closeButton.current?.focus({ preventScroll: true });
  }, [open, visible]);
  useEffect(() => {
    function protectDraft(event: BeforeUnloadEvent) {
      if (dirty) event.preventDefault();
    }
    window.addEventListener("beforeunload", protectDraft);
    return () => window.removeEventListener("beforeunload", protectDraft);
  }, [dirty]);

  return <div className="floating-ai" hidden={!visible}>
    {opened && <section id="floating-ai-panel" className="floating-ai-panel" role="dialog" aria-modal="false" aria-labelledby="floating-ai-title" hidden={!open} onKeyDown={event => {
      if (event.key === "Escape" && !event.defaultPrevented && !document.querySelector("dialog[open]")) {
        event.stopPropagation();
        close();
      }
    }}>
      <header className="floating-ai-header">
        <Image src={symbol} alt="" width={36} height={36} />
        <div><h2 id="floating-ai-title">Помощник</h2><p>Твои планы и материалы рядом</p></div>
        <button ref={closeButton} type="button" className="icon-button" aria-label="Свернуть помощника" onClick={close}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M5 12h14" /></svg>
        </button>
      </header>
      <div className="floating-ai-content ai-page">
        <ChatArea composerId="floating-ai-message" selected={selected} onChoose={id => {
          if (dirty) setPending({ id });
          else setSelected(id);
        }} onDirtyChange={setDirty} onOpenPage={onOpenPage} onOpenEvent={onOpenEvent} />
      </div>
    </section>}
    <button ref={trigger} type="button" className="floating-ai-trigger" aria-label={open ? "Свернуть AI-помощника" : "Открыть AI-помощника"} aria-expanded={open} aria-controls={opened ? "floating-ai-panel" : undefined} onClick={() => {
      if (open) close();
      else { setOpened(true); setOpen(true); }
    }}>
      <Image src={symbol} alt="" width={38} height={38} />
      <span>AI</span>
    </button>
    {pending && <Modal title="Сменить беседу" onClose={() => setPending(null)}>
      <h2>Оставить черновик?</h2><p>Несохранённый текст текущей беседы будет потерян.</p>
      <div className="modal-actions"><button className="secondary-button" onClick={() => setPending(null)}>Остаться</button><button className="danger-button" onClick={() => { setDirty(false); setSelected(pending.id); setPending(null); }}>Сменить беседу</button></div>
    </Modal>}
  </div>;
}
