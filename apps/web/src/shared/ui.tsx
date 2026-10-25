"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`ui-dialog ${wide ? "wide-dialog" : ""}`}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          const box = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < box.left ||
            event.clientX > box.right ||
            event.clientY < box.top ||
            event.clientY > box.bottom
          )
            onClose();
        }
      }}
    >
      <button
        className="modal-close"
        type="button"
        aria-label="Закрыть"
        onClick={onClose}
      >
        ×
      </button>
      {children}
    </dialog>
  );
}

export function EmptyState({
  title,
  children,
  icon = "◇",
}: {
  title: string;
  children: ReactNode;
  icon?: string;
}) {
  return (
    <div className="ui-empty">
      <span className="empty-symbol" aria-hidden="true">
        {icon}
      </span>
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}

export function QueryState({
  pending,
  error,
  retry,
}: {
  pending: boolean;
  error: unknown;
  retry: () => void;
}) {
  if (pending)
    return (
      <div className="skeleton-stack" role="status" aria-label="Загрузка">
        <span />
        <span />
        <span />
      </div>
    );
  if (error)
    return (
      <div className="ui-error" role="alert">
        <strong>Не удалось загрузить данные</strong>
        <p>
          {error instanceof Error ? error.message : "Проверьте соединение."}
        </p>
        <button className="secondary-button" onClick={retry}>
          Повторить
        </button>
      </div>
    );
  return null;
}

export function Pager({
  offset,
  count,
  size = 50,
  onChange,
}: {
  offset: number;
  count: number;
  size?: number;
  onChange: (offset: number) => void;
}) {
  return (
    <div className="ui-pager">
      <button
        className="secondary-button"
        disabled={!offset}
        onClick={() => onChange(Math.max(0, offset - size))}
      >
        Назад
      </button>
      <span>{count ? `${offset + 1}–${offset + count}` : "Нет элементов"}</span>
      <button
        className="secondary-button"
        disabled={count < size}
        onClick={() => onChange(offset + size)}
      >
        Далее
      </button>
    </div>
  );
}

export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const active = useRef(false);
  async function run(action: () => Promise<void>, message = "Сохранено") {
    if (active.current) return;
    active.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      setNotice(message);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Не удалось выполнить действие.",
      );
    } finally {
      active.current = false;
      setBusy(false);
    }
  }
  return { busy, error, notice, run };
}

export function ActionFeedback({
  error,
  notice,
}: {
  error: string;
  notice: string;
}) {
  return (
    <>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="action-notice" role="status">
          {notice}
        </p>
      )}
    </>
  );
}
