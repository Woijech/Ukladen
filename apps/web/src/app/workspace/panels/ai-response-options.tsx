"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { HelpTooltip } from "@/shared/help-tooltip";
import { NavIcon } from "../navigation";

export function ResponseOptions({
  sourceOnly, fullSources, disabled, onSourceOnlyChange, onFullSourcesChange,
}: {
  sourceOnly: boolean;
  fullSources: boolean;
  disabled: boolean;
  onSourceOnlyChange: (value: boolean) => void;
  onFullSourcesChange: (value: boolean) => void;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const activeCount = Number(sourceOnly) + Number(fullSources);
  const position = useCallback(() => {
    if (!trigger.current || !panel.current?.matches(":popover-open")) return;
    const box = trigger.current.getBoundingClientRect();
    const bounds = panel.current.getBoundingClientRect();
    const above = box.top - bounds.height - 8;
    const top = above >= 12 ? above : box.bottom + 8;
    panel.current.style.left = `${Math.max(12, Math.min(box.left, window.innerWidth - bounds.width - 12))}px`;
    panel.current.style.top = `${Math.max(12, Math.min(top, window.innerHeight - bounds.height - 12))}px`;
  }, []);
  useEffect(() => {
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    const observer = new ResizeObserver(position);
    if (trigger.current) observer.observe(trigger.current);
    if (panel.current) observer.observe(panel.current);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
      observer.disconnect();
    };
  }, [position]);
  return (
    <div className="ai-response-options">
      <button
        ref={trigger}
        type="button"
        className="ai-composer-control ai-options-button"
        aria-label="Параметры ответа"
        aria-expanded={open}
        aria-controls={id}
        popoverTarget={id}
      >
        <NavIcon path="M3 6h18M3 12h18M3 18h18M8 3v6m8 0v6m-7 0v6" />
        <span>Параметры ответа</span>
        {!!activeCount && <small className="ai-options-count" aria-hidden="true">{activeCount}</small>}
        <span className="ai-disclosure-chevron" aria-hidden="true">⌄</span>
      </button>
      <div
        ref={panel}
        id={id}
        popover="auto"
        role="region"
        aria-label="Настройки ответа"
        className="ai-options-popover"
        onToggle={event => {
          setOpen(event.newState === "open");
          position();
        }}
      >
        <div className="ai-composer-options">
          <div className="ai-option-with-help">
            <label className="checkbox-label">
              <input type="checkbox" aria-label="Только мои источники" checked={sourceOnly} disabled={disabled} onChange={event => onSourceOnlyChange(event.target.checked)} />
              <span><strong>Только мои источники</strong></span>
            </label>
            <HelpTooltip label="О режиме только моих источников">Искать в твоём пространстве, без веб-поиска.</HelpTooltip>
          </div>
          <div className="ai-option-with-help">
            <label className="checkbox-label">
              <input type="checkbox" aria-label="Разобрать документы целиком" checked={fullSources} disabled={disabled} onChange={event => onFullSourcesChange(event.target.checked)} />
              <span><strong>Разобрать документы целиком</strong></span>
            </label>
            <HelpTooltip label="О полном разборе документов">Для выбранных страниц и файлов. Сначала выбери их в источниках.</HelpTooltip>
          </div>
        </div>
      </div>
    </div>
  );
}
