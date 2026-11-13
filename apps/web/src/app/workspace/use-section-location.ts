"use client";

import { useEffect, useRef, useState } from "react";
import { type SectionKey } from "./navigation";
import { readWorkspaceLocation, workspaceHref, type WorkspaceLocation } from "./workspace-location";

export function pushWorkspaceLocation(url: string) {
  const next = (window.history.state?.ukladenPosition ?? 0) + 1;
  window.history.pushState({ ...window.history.state, ukladenPosition: next }, "", url);
  window.dispatchEvent(new Event("ukladen:location-pushed"));
}

export function useSectionLocation(
  fallback: SectionKey,
  protection: () => { dirty: boolean; busy: boolean },
  onDiscard?: () => void,
) {
  const read = () => readWorkspaceLocation(window.location.pathname, window.location.search, fallback);
  const [location, setLocation] = useState(() => read().location);
  const [notice, setNotice] = useState("");
  const [discardVersion, setDiscardVersion] = useState(0);
  const protect = useRef(protection);
  useEffect(() => { protect.current = protection; }, [protection]);
  const discard = useRef(onDiscard);
  useEffect(() => { discard.current = onDiscard; }, [onDiscard]);
  function discardDrafts() {
    discard.current?.();
    setDiscardVersion(value => value + 1);
  }
  const position = useRef(0);
  const restoring = useRef(false);
  const currentUrl = useRef("");
  useEffect(() => {
    position.current = window.history.state?.ukladenPosition ?? 0;
    window.history.replaceState({ ...window.history.state, ukladenPosition: position.current }, "");
    currentUrl.current = window.location.pathname + window.location.search;
  }, []);
  useEffect(() => {
    function accept() {
      const parsed = readWorkspaceLocation(window.location.pathname, window.location.search, fallback);
      if (parsed.invalid) {
        window.history.replaceState(window.history.state, "", workspaceHref(parsed.location));
        setNotice("Некорректные параметры ссылки удалены. Проверь выбранный объект или дату.");
      }
      position.current = window.history.state?.ukladenPosition ?? 0;
      currentUrl.current = window.location.pathname + window.location.search;
      setLocation(parsed.location);
    }
    accept();
    function back() {
      if (restoring.current) { restoring.current = false; return; }
      const next = window.history.state?.ukladenPosition;
      const guard = protect.current();
      if (guard.busy || (guard.dirty && !window.confirm("Есть несохранённые изменения. Перейти без сохранения?"))) {
        if (guard.busy) setNotice("Дождись завершения сохранения перед переходом.");
        if (typeof next === "number" && next !== position.current) {
          restoring.current = true;
          window.history.go(position.current - next);
        } else {
          // Entries not created by Ukladen have no relative history position.
          window.history.pushState({ ...window.history.state, ukladenPosition: position.current }, "", currentUrl.current);
        }
        return;
      }
      if (guard.dirty) discardDrafts();
      accept();
    }
    function unload(event: BeforeUnloadEvent) {
      const guard = protect.current();
      if (guard.dirty || guard.busy) { event.preventDefault(); event.returnValue = ""; }
    }
    window.addEventListener("popstate", back);
    window.addEventListener("beforeunload", unload);
    window.addEventListener("ukladen:location-pushed", accept);
    return () => {
      window.removeEventListener("popstate", back);
      window.removeEventListener("beforeunload", unload);
      window.removeEventListener("ukladen:location-pushed", accept);
    };
  }, [fallback]);

  function commitLocation(next: WorkspaceLocation, replace = false) {
    const url = workspaceHref(next);
    if (window.location.pathname + window.location.search !== url) {
      if (replace) {
        window.history.replaceState(window.history.state, "", url);
        window.dispatchEvent(new Event("ukladen:location-pushed"));
      } else pushWorkspaceLocation(url);
    }
    setLocation(next);
  }
  function commitSection(section: SectionKey, query?: string) {
    commitLocation({ section, query });
  }
  return {
    section: location.section, location, commitLocation, commitSection, notice,
    discardVersion, discardDrafts,
  };
}
