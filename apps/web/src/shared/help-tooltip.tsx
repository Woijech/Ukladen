"use client";

import { useCallback, useEffect, useId, useRef, type ReactNode } from "react";

export function HelpTooltip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const content = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const position = useCallback(() => {
    if (!trigger.current || !content.current?.matches(":popover-open")) return;
    const box = trigger.current.getBoundingClientRect();
    const width = Math.min(280, window.innerWidth - 24);
    const height = content.current.getBoundingClientRect().height;
    const below = box.bottom + 8;
    const top = below + height <= window.innerHeight - 12 ? below : box.top - height - 8;
    content.current.style.width = `${width}px`;
    content.current.style.left = `${Math.max(12, Math.min(box.left, window.innerWidth - width - 12))}px`;
    content.current.style.top = `${Math.max(12, Math.min(top, window.innerHeight - height - 12))}px`;
  }, []);
  useEffect(() => {
    window.addEventListener("resize", position);
    return () => window.removeEventListener("resize", position);
  }, [position]);
  return <span className="help-tooltip" onKeyDown={event => {
    if (event.key === "Escape" && !event.nativeEvent.isComposing && content.current?.matches(":popover-open")) {
      event.preventDefault(); event.stopPropagation();
      content.current.hidePopover(); trigger.current?.focus();
    }
  }}>
    <button ref={trigger} type="button" className="help-tooltip-trigger" aria-label={label} popoverTarget={id}>?</button>
    <div ref={content} id={id} popover="auto" role="note" tabIndex={0} className="help-tooltip-content" onToggle={position}>{children}</div>
  </span>;
}
