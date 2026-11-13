export function positionNoteMenu(details: HTMLDetailsElement) {
  if (!details.open) return;
  const menu = details.querySelector<HTMLElement>(":scope > .note-menu-items");
  const trigger = details.querySelector("summary");
  if (!menu || !trigger) return;
  menu.style.position = "fixed";
  menu.style.right = "auto";
  menu.style.left = "8px";
  menu.style.top = "8px";
  const anchor = trigger.getBoundingClientRect();
  const bounds = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - bounds.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(anchor.bottom + 4, window.innerHeight - bounds.height - 8))}px`;
}
