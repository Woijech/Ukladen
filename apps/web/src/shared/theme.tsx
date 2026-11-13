"use client";

import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
  window.addEventListener("ukladen:theme", callback);
  return () => window.removeEventListener("ukladen:theme", callback);
}

function applyTheme(theme: string) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem("ukladen-theme", theme); }
  catch { /* Theme remains available without storage. */ }
  window.dispatchEvent(new Event("ukladen:theme"));
}

export function ThemeOptions() {
  const theme = useSyncExternalStore(subscribe, () => document.documentElement.dataset.theme ?? "system", () => "system");
  return <div className="theme-options" role="group" aria-label="Оформление приложения">
    {([["light", "Светлая"], ["dark", "Тёмная"], ["system", "Системная"]] as const).map(([value, label]) => (
      <button type="button" key={value} data-theme-option={value} aria-pressed={theme === value} onClick={() => applyTheme(value)}>
        <span className="theme-preview" aria-hidden="true"><span /><span /></span>{label}
      </button>
    ))}
  </div>;
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(
    subscribe,
    () => document.documentElement.dataset.theme ?? "system",
    () => "system",
  );
  function change() {
    const next =
      theme === "system" ? "light" : theme === "light" ? "dark" : "system";
    applyTheme(next);
  }
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={change}
      aria-label={`Тема: ${theme === "dark" ? "тёмная" : theme === "light" ? "светлая" : "системная"}. Изменить тему`}
      title="Системная → светлая → тёмная"
    >
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
        aria-hidden="true"
      >
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5" />
      </svg>
      <span>
        {theme === "dark"
          ? "Тёмная"
          : theme === "light"
            ? "Светлая"
            : "Системная"}
      </span>
    </button>
  );
}
