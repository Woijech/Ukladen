"use client";

import { useEffect, useRef } from "react";
import { GoogleAuth } from "./google-auth";
import styles from "./google-auth.module.css";

export function GoogleLinkDialog({ onClose, onSessionEnd }: { onClose: () => void; onSessionEnd: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} onClose={onClose} className={`event-modal ${styles.dialog}`} aria-labelledby="google-link-title">
    <button type="button" className="modal-close" aria-label="Закрыть" onClick={() => dialog.current?.close()}>×</button>
    <h2 id="google-link-title">Связать аккаунт с Google</h2>
    <p>Подтвердите пароль Ukladen и выберите аккаунт Google. После привязки можно будет входить обоими способами.</p>
    <GoogleAuth link onSessionEnd={onSessionEnd} />
  </dialog>;
}
