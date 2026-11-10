"use client";

import { useEffect, useRef, useState } from "react";
import { sections, sectionHref, type SectionKey } from "./navigation";

function readSection(fallback: SectionKey): SectionKey {
  if (window.location.pathname.startsWith("/workspace/ai")) return "ai";
  const params = new URLSearchParams(window.location.search);
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(params.get("page") ?? "")) return "notes";
  return sections.find(item => item.id === params.get("section"))?.id ?? fallback;
}

export function pushWorkspaceLocation(url: string) {
  const next = (window.history.state?.ukladenPosition ?? 0) + 1;
  window.history.pushState({ ukladenPosition: next }, "", url);
  window.dispatchEvent(new Event("ukladen:location-pushed"));
}

export function useSectionLocation(fallback: SectionKey, dirty: boolean) {
  const [location, setLocation] = useState(() => ({ section: readSection(fallback) }));
  const position = useRef(0);
  const restoring = useRef(false);
  useEffect(() => {
    position.current = window.history.state?.ukladenPosition ?? 0;
    window.history.replaceState({ ukladenPosition: position.current }, "");
  }, []);
  useEffect(() => {
    function back() {
      if (restoring.current) { restoring.current = false; return; }
      const next = window.history.state?.ukladenPosition;
      if (dirty && !window.confirm("Есть несохранённые изменения. Перейти без сохранения?")) {
        if (typeof next === "number" && next !== position.current) {
          restoring.current = true;
          window.history.go(position.current - next);
        }
        return;
      }
      position.current = next ?? 0;
      setLocation({ section: readSection(fallback) });
    }
    const pushed = () => {
      position.current = window.history.state?.ukladenPosition ?? 0;
      setLocation({ section: readSection(fallback) });
    };
    window.addEventListener("popstate", back);
    window.addEventListener("ukladen:location-pushed", pushed);
    return () => {
      window.removeEventListener("popstate", back);
      window.removeEventListener("ukladen:location-pushed", pushed);
    };
  }, [dirty, fallback]);

  function commitSection(next: SectionKey, query?: string) {
    const url = sectionHref(next) + (query ? `&q=${encodeURIComponent(query)}` : "");
    if (window.location.pathname + window.location.search !== url) {
      pushWorkspaceLocation(url);
    }
    setLocation({ section: next });
  }
  return { section: location.section, commitSection };
}
