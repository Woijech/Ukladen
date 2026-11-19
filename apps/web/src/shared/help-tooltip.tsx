"use client";

import { useId, useRef, type ReactNode } from "react";

export function HelpTooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const content = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  function position() {
    if (!trigger.current || !content.current) return;
    const box = trigger.current.getBoundingClientRect();
    const width = Math.min(280, window.innerWidth - 24);
    content.current.style.width = `${width}px`;
    content.current.style.left = `${Math.max(12, Math.min(box.left, window.innerWidth - width - 12))}px`;
    content.current.style.top = `${Math.max(12, Math.min(box.bottom + 8, window.innerHeight - 170))}px`;
  }
  return <span className="help-tooltip">
    <button ref={trigger} type="button" className="help-tooltip-trigger" aria-label={label} popoverTarget={id} onClick={position}
      onKeyDown={event => { if (event.key === "Escape" && content.current?.matches(":popover-open")) { event.preventDefault(); event.stopPropagation(); content.current.hidePopover(); trigger.current?.focus(); } }}>?</button>
    <div ref={content} id={id} popover="auto" role="note" className="help-tooltip-content">{children}</div>
  </span>;
}
