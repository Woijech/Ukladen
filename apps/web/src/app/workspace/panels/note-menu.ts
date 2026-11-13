export function positionNoteMenu(details: HTMLDetailsElement) {
  if (!details.open) return;
  const menu = details.querySelector<HTMLElement>(":scope > .note-menu-items");
  const trigger = details.querySelector("summary");
  if (!menu || !trigger) return;
  const dialog = details.closest("dialog")?.getBoundingClientRect();
  const left = Math.max(8, (dialog?.left ?? 0) + 8);
  const top = Math.max(8, (dialog?.top ?? 0) + 8);
  const right = Math.min(window.innerWidth - 8, (dialog?.right ?? window.innerWidth) - 8);
  const bottom = Math.min(window.innerHeight - 8, (dialog?.bottom ?? window.innerHeight) - 8);
  menu.style.position = "fixed";
  menu.style.right = "auto";
  menu.style.left = "0px";
  menu.style.top = "0px";
  menu.style.maxWidth = `${Math.max(0, right - left)}px`;
  menu.style.maxHeight = `${Math.max(0, bottom - top)}px`;
  menu.style.overflowY = "auto";
  const anchor = trigger.getBoundingClientRect();
  // An animated dialog can establish a containing block for fixed descendants.
  const origin = menu.getBoundingClientRect();
  const x = Math.max(left, Math.min(anchor.left, right - origin.width));
  const y = Math.max(top, Math.min(anchor.bottom + 4, bottom - origin.height));
  menu.style.left = `${x - origin.left}px`;
  menu.style.top = `${y - origin.top}px`;
}
