"use client";

import { useState, type ReactNode } from "react";

export const sections = [
  {
    id: "home",
    title: "Главная",
    icon: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z",
  },
  {
    id: "calendar",
    title: "Календарь",
    icon: "M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14H3V6a2 2 0 0 1 2-2Z",
  },
  {
    id: "tasks",
    title: "Задачи",
    icon: "M9 5h12M9 12h12M9 19h12M3 5h.01M3 12h.01M3 19h.01",
  },
  {
    id: "notes",
    title: "Заметки",
    icon: "M14 2H5v20h14V7Zm0 0v5h5M7 12h8m-8 4h6",
  },
  {
    id: "materials",
    title: "Материалы",
    icon: "M3 6h7l2 2h9v12H3Zm0 0V4h7l2 2",
  },
  {
    id: "databases",
    title: "Базы данных",
    icon: "M3 4h18v16H3Zm0 5h18M9 9v11m6-11v11M3 14h18",
  },
  {
    id: "organization",
    title: "Коллекции и теги",
    icon: "M3 3h7l11 11-7 7L3 10Zm4 4h.01",
  },
  {
    id: "search",
    title: "Поиск",
    icon: "M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  },
  {
    id: "notifications",
    title: "Уведомления",
    icon: "M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4",
  },
  {
    id: "ai",
    title: "AI",
    icon: "M4 4h16v12H9l-5 4Zm4 5h8m-8 3h5",
  },
  {
    id: "settings",
    title: "Настройки",
    icon: "m9 3-1 3-3 1-2 3 2 3v4l4 1 3 3 3-3 4-1v-4l2-3-2-3-3-1-1-3Zm6 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  },
] as const;
export type SectionKey = (typeof sections)[number]["id"];
export const primarySections = ["calendar", "notes", "tasks", "ai"] as const;

export function NavIcon({ path }: { path: string }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={path} />
    </svg>
  );
}

export function Navigation({
  active,
  onNavigate,
  footer,
}: {
  active: SectionKey;
  onNavigate: (section: SectionKey) => void;
  footer?: ReactNode;
}) {
  const [moreOpen, setMoreOpen] = useState(false);
  const primary = new Set<SectionKey>(primarySections);
  const secondaryActive = !primary.has(active) && active !== "settings";
  function item(section: (typeof sections)[number]) {
    return (
      <button
        type="button"
        className={`nav-item ${active === section.id ? "active" : ""}`}
        aria-current={active === section.id ? "page" : undefined}
        key={section.id}
        aria-label={section.title}
        onClick={() => onNavigate(section.id)}
        title={section.title}
      >
        <NavIcon path={section.icon} />
        <span>{section.title}</span>
      </button>
    );
  }
  return (
    <nav className="workspace-navigation" aria-label="Разделы пространства" onKeyDown={(event) => {
      if (event.key === "Escape" && moreOpen) {
        setMoreOpen(false);
        event.currentTarget.querySelector<HTMLButtonElement>('button[aria-expanded]')?.focus();
      }
    }}>
      <span className="sidebar-section-label">Рабочее пространство</span>
      {primarySections.map((id) =>
        item(sections.find((section) => section.id === id)!),
      )}
      <button
        type="button"
        className={`nav-item ${secondaryActive ? "active" : ""}`}
        aria-label="Ещё"
        aria-expanded={moreOpen}
        onClick={() => setMoreOpen(!moreOpen)}
        title="Ещё"
      >
        <NavIcon path="M4 4h6v6H4Zm10 0h6v6h-6ZM4 14h6v6H4Zm10 0h6v6h-6Z" />
        <span>Ещё</span>
        <span className="nav-disclosure" aria-hidden="true">{moreOpen ? "−" : "+"}</span>
      </button>
      {moreOpen && (
        <div
          className="secondary-navigation"
          aria-label="Дополнительные разделы"
        >
          {sections
            .filter(
              (section) =>
                !primary.has(section.id) && section.id !== "settings",
            )
            .map(item)}
        </div>
      )}
      {footer}
    </nav>
  );
}
