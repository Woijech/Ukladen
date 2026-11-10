"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/shared/ui";
import { NavIcon, sections, type SectionKey } from "./navigation";

export function CommandPalette({ onClose, onNavigate, onSearch }: {
  onClose: () => void; onNavigate: (section: SectionKey) => void; onSearch: (query: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(0);
  const matches = sections.filter(item => item.title.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  const count = matches.length + (query.trim() ? 1 : 0);
  useEffect(() => {
    document.getElementById(`command-${selected}`)?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  function activate(index: number) {
    onClose();
    if (index < matches.length) onNavigate(matches[index].id);
    else onSearch(query.trim());
  }
  return <Modal initialFocus="#command-query" title="Поиск и переходы" onClose={onClose}>
    <div className="command-palette">
      <h2>Поиск и переходы</h2>
      <label htmlFor="command-query">Раздел или текст для поиска</label>
      <input id="command-query" type="search" autoComplete="off" maxLength={200}
        placeholder="Заметки, базы данных или текст…" value={query}
        role="combobox" aria-expanded="true" aria-controls="command-results"
        aria-activedescendant={count ? `command-${selected}` : undefined}
        onChange={event => { setQuery(event.target.value); setSelected(0); }}
        onKeyDown={event => {
          if (event.nativeEvent.isComposing) return;
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setSelected(index => (index + (event.key === "ArrowDown" ? 1 : count - 1)) % count);
          }
          if (event.key === "Enter" && count) { event.preventDefault(); activate(selected); }
        }} />
      <div id="command-results" role="listbox" aria-label="Переходы и поиск">
        {matches.map((item, index) => <button type="button" tabIndex={-1} key={item.id} id={`command-${index}`} role="option"
          aria-selected={selected === index} onPointerMove={() => setSelected(index)} onClick={() => activate(index)}>
            <NavIcon path={item.icon} /><span>{item.title}</span><small>Открыть раздел</small>
        </button>)}
        {query.trim() && <button type="button" tabIndex={-1} id={`command-${matches.length}`} role="option" aria-selected={selected === matches.length} onClick={() => activate(matches.length)}>
            Найти «{query.trim()}» в страницах и материалах
        </button>}
      </div>
      <p className="muted">↑ ↓ выбрать · Enter открыть · Esc закрыть</p>
    </div>
  </Modal>;
}
