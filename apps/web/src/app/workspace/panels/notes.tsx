"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageAttachments } from "./attachments";
import { positionNoteMenu } from "./note-menu";
import { workspaceHref } from "../workspace-location";
import { isUnavailableObject, UnavailableObject } from "../unavailable-object";
import { NoteBlocks } from "./note-blocks";
import { useNoteDraft } from "./use-note-draft";
import "./notes.css";
import { requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  QueryState,
  useAction,
} from "@/shared/ui";

export type PageSummary = {
  id: string;
  title: string;
  parent_id: string | null;
  version: number;
  updated_at: string;
  trashed_at: string | null;
  trash_batch_id?: string | null;
};
export type Block =
  | {
      id: string;
      type: "text";
      text: string;
      text_format: "plain" | "markdown";
    }
  | { id: string; type: "heading"; text: string; level: number }
  | { id: string; type: "checkbox"; text: string; checked: boolean }
  | {
      id: string;
      type: "list";
      items: string[];
      style: "bulleted" | "numbered";
    }
  | { id: string; type: "link"; text: string; url: string };
export type Note = PageSummary & { document: { schema_version: 1; blocks: Block[] } };
type PageList = { items: PageSummary[]; limit: number; offset: number };

type Destination = { id: string | null; action?: "move" | "trash" | "restore" };

// shortcut: load all summaries for complete nesting; use lazy branches for large libraries.
async function pageSummaries(trashed: boolean, signal: AbortSignal) {
  const pages: PageSummary[] = [];
  for (let offset = 0; ; offset += 200) {
    const batch = await requestJson<PageList>(
      `/api/v1/notes/pages?trashed=${trashed}&limit=200&offset=${offset}`,
      { signal },
    );
    pages.push(...batch.items);
    if (batch.items.length < 200) return pages;
  }
}

export function NotesPanel({
  selectedId,
  onSelectPage,
  onBusyChange,
  onDirtyChange,
}: {
  selectedId: string | null;
  onSelectPage: (id: string | null) => void;
  onBusyChange: (busy: boolean) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const selected = selectedId;
  const [trashed, setTrashed] = useState(false);
  const [creating, setCreating] = useState<{ parent: string | null } | null>(
    null,
  );
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Destination | null>(null);
  const [intent, setIntent] = useState<Destination | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [treeOpen, setTreeOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [createTitle, setCreateTitle] = useState("");
  function startCreating(parent: string | null) { setCreateTitle(""); setCreating({ parent }); }
  const [focusTitle, setFocusTitle] = useState<string | null>(null);
  const client = useQueryClient();
  const action = useAction();
  const active = useQuery({
    queryKey: ["pages", false],
    queryFn: ({ signal }) => pageSummaries(false, signal),
  });
  const trash = useQuery({
    queryKey: ["pages", true],
    queryFn: ({ signal }) => pageSummaries(true, signal),
    enabled: trashed,
  });
  const list = trashed ? trash : active;
  const summaries = list.data ?? [];
  const summaryIds = new Set(summaries.map((page) => page.id));
  const childrenByParent = new Map<string | null, PageSummary[]>();
  for (const page of summaries) {
    const parent =
      page.parent_id && summaryIds.has(page.parent_id) ? page.parent_id : null;
    const siblings = childrenByParent.get(parent) ?? [];
    siblings.push(page);
    childrenByParent.set(parent, siblings);
  }
  const note = useQuery({
    queryKey: ["page", selected],
    queryFn: ({ signal }) =>
      requestJson<Note>(`/api/v1/notes/pages/${selected}`, { signal }),
    enabled: !!selected,
    retry: false,
  });
  useLayoutEffect(() => { onBusyChange(busy || action.busy); return () => onBusyChange(false); }, [busy, action.busy, onBusyChange]);
  const dirtyCallback = useRef(onDirtyChange);
  const mounted = useRef(true);
  useEffect(() => { dirtyCallback.current = onDirtyChange; }, [onDirtyChange]);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; dirtyCallback.current(false); };
  }, []);
  const hasDraft = dirty || Boolean(creating && createTitle.trim());
  useEffect(() => { dirtyCallback.current(hasDraft); }, [hasDraft]);
  function changeDirty(value: boolean) {
    setDirty(value);
    if (mounted.current) dirtyCallback.current(value || Boolean(creating && createTitle.trim()));
  }
  function go(destination: Destination) {
    onSelectPage(destination.id);
    setIntent(destination);
    setPending(null);
    setTreeOpen(false);
  }
  function choose(destination: Destination) {
    if (busy) return;
    if (dirty && (selected !== destination.id || destination.action))
      setPending(destination);
    else go(destination);
  }
  useEffect(() => {
    function prevent(event: BeforeUnloadEvent) {
      if (hasDraft) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [hasDraft]);
  async function refresh() {
    await client.invalidateQueries({ queryKey: ["pages"] });
  }
  const visible = new Set<string>();
  for (const page of summaries) {
    if (!page.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) continue;
    let current: PageSummary | undefined = page;
    while (current && !visible.has(current.id)) {
      visible.add(current.id);
      current = summaries.find(item => item.id === current!.parent_id);
    }
  }
  function tree(parent: string | null, ancestors: Set<string> = new Set()) {
    const children = childrenByParent.get(parent) ?? [];
    return (
      <ul
        className="note-tree-list"
        aria-label={
          parent ? undefined : trashed ? "Удалённые страницы" : "Дерево страниц"
        }
      >
        {children
          .filter((page) => !ancestors.has(page.id) && visible.has(page.id))
          .map((page) => {
            const hasChildren = childrenByParent.has(page.id);
            const expanded = !!search.trim() || !collapsed.has(page.id);
            return (
              <li key={page.id}>
                <div
                  className={`note-tree-row ${selected === page.id ? "selected" : ""}`}
                >
                  <button
                    type="button"
                    className="tree-disclosure"
                    disabled={!hasChildren}
                    aria-label={`${expanded ? "Свернуть" : "Развернуть"} ${page.title}`}
                    aria-expanded={hasChildren ? expanded : undefined}
                    onClick={() =>
                      setCollapsed((value) => {
                        const next = new Set(value);
                        if (expanded) next.add(page.id);
                        else next.delete(page.id);
                        return next;
                      })
                    }
                  >
                    <span aria-hidden="true">
                      {hasChildren ? (expanded ? "⌄" : "›") : "·"}
                    </span>
                  </button>
                  <button
                    className="tree-page-link"
                    aria-current={selected === page.id ? "page" : undefined}
                    disabled={busy}
                    onClick={() => choose({ id: page.id })}
                  >
                    <span aria-hidden="true">▤</span>
                    <span>{page.title}</span>
                    {page.trashed_at && <small>в корзине</small>}
                  </button>
                  {!trashed && (
                    <button
                      className="tree-child-add"
                      aria-label={`Добавить страницу в ${page.title}`}
                      disabled={busy || action.busy}
                      onClick={() => startCreating(page.id)}
                    >
                      +
                    </button>
                  )}
                  <details
                    className="note-menu tree-menu"
                    onToggle={event => positionNoteMenu(event.currentTarget)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape" && event.currentTarget.open) {
                        event.preventDefault();
                        event.stopPropagation();
                        event.currentTarget.open = false;
                        event.currentTarget.querySelector("summary")?.focus();
                      }
                    }}
                  >
                    <summary aria-label={`Действия страницы ${page.title}`}>
                      ···
                    </summary>
                    <div
                      className="note-menu-items"
                      onClick={(event) => {
                        if ((event.target as HTMLElement).closest("button"))
                          event.currentTarget
                            .closest("details")
                            ?.removeAttribute("open");
                      }}
                    >
                      {!page.trashed_at && (
                        <button
                          onClick={() =>
                            choose({ id: page.id, action: "move" })
                          }
                        >
                          Переместить
                        </button>
                      )}
                      <button
                        disabled={busy}
                        onClick={() =>
                          choose({
                            id: page.id,
                            action: page.trashed_at ? "restore" : "trash",
                          })
                        }
                      >
                        {page.trashed_at
                          ? "Восстановить страницу"
                          : "В корзину"}
                      </button>
                    </div>
                  </details>
                </div>
                {hasChildren &&
                  expanded &&
                  tree(page.id, new Set([...ancestors, page.id]))}
              </li>
            );
          })}
      </ul>
    );
  }
  const treePanel = <>
          <div className="panel-toolbar">
            <strong>Страницы</strong>
            <button
              className="text-action"
              aria-label="Новая страница"
              disabled={busy || action.busy}
              onClick={() => { startCreating(null); if (window.matchMedia("(max-width: 1100px)").matches) setTreeOpen(true); }}
            >
              +
            </button>
          </div>
          <input type="search" className="note-page-search" aria-label="Найти страницу" placeholder="Найти страницу…" value={search} onChange={event => setSearch(event.target.value)} />
          <button
            className="notes-trash-toggle text-action"
            aria-pressed={trashed}
            onClick={() => setTrashed(!trashed)}
          >
            {trashed ? "← Активные страницы" : "Корзина"}
          </button>
          {trashed && (
            <p className="tree-empty muted">
              Корзина · страницы можно восстановить
            </p>
          )}
          <QueryState
            pending={list.isPending}
            error={list.error}
            retry={() => void list.refetch()}
          />
          {!list.isPending && !list.isError && !summaries.length && (
            <p className="muted tree-empty">
              {trashed ? "Корзина пуста" : "Начни с первой страницы"}
            </p>
          )}
          {creating && (          <form className="note-create-form" aria-label="Новая страница"
            onKeyDown={event => { if (event.key === "Escape" && !action.busy) { event.preventDefault(); event.stopPropagation(); setCreating(null); } }}
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              void action.run(async () => {
                const created = await writeJson<Note>(
                  "/api/v1/notes/pages",
                  "POST",
                  {
                    title: String(values.get("title")).trim(),
                    parent_id: creating.parent,
                    document: { schema_version: 1, blocks: [] },
                  },
                );
                client.setQueryData(["page", created.id], created);
                setFocusTitle(created.id);
                setCreating(null);
                setTrashed(false);
                setCollapsed((value) => {
                  const next = new Set(value);
                  if (creating.parent) next.delete(creating.parent);
                  return next;
                });
                choose({ id: created.id });
                await refresh();
              }, "Страница создана");
            }}
          >
            <strong>Новая страница</strong>
            {creating.parent && (
              <p className="muted">
                Внутри:{" "}
                {
                  active.data?.find((page) => page.id === creating.parent)
                    ?.title
                }
              </p>
            )}
            <label htmlFor="new-page-title">Название новой страницы</label>
            <input
              id="new-page-title"
              name="title"
              value={createTitle}
              onChange={event => setCreateTitle(event.target.value)}
              maxLength={200}
              required
              pattern={".*\\S.*"}
              autoFocus
              disabled={action.busy}
              placeholder="Например, идеи для проекта"
            />
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={action.busy}
                onClick={() => setCreating(null)}
              >
                Отмена
              </button>
              <button className="primary-button" disabled={action.busy}>
                Создать
              </button>
            </div>
          </form>)}
          {search && !visible.size && <p className="muted tree-empty">Страницы не найдены</p>}
          {tree(null)}
  </>;
  return (
    <div className="feature-page notes-page">
      <h1 className="notes-desktop-title sr-only">Заметки</h1>
      <div className="notes-mobile-toolbar">
        <h1>Заметки</h1>
        <button
          className="secondary-button"
          aria-expanded={treeOpen}
          aria-controls={treeOpen ? "notes-page-tree-sheet" : "notes-page-tree"}
          onClick={() => setTreeOpen(!treeOpen)}
        >
          Страницы {treeOpen ? "↑" : "↓"}
        </button>
      </div>
      {treeOpen && <Modal title="Страницы" onClose={() => setTreeOpen(false)}><div id="notes-page-tree-sheet" className="note-tree-sheet">{treePanel}</div></Modal>}
      <div className="notes-layout">
        <aside
          id="notes-page-tree"
          className={`page-tree ${treeOpen ? "tree-in-sheet" : ""}`}
        >
          {!treeOpen && treePanel}

        </aside>
        <div className="note-canvas">
          {selected ? (
            <>
              {isUnavailableObject(note.error) ? <UnavailableObject onBack={() => go({ id: null })} /> : <QueryState
                pending={note.isPending}
                error={note.error}
                retry={() => void note.refetch()}
              />}
              {note.data && !isUnavailableObject(note.error) && (
                <NoteEditor
                  key={note.data.id}
                  note={note.data}
                  pages={active.data ?? []}
                  onSelect={(id) => choose({ id })}
                  onDirtyChange={changeDirty}
                  onBusyChange={setBusy}
                  focusTitle={focusTitle === note.data.id}
                  intent={intent}
                  onCloseIntent={() => setIntent(null)}
                  pending={pending}
                  onCancelPending={() => setPending(null)}
                  onDiscard={() => {
                    changeDirty(false);
                    if (pending) go(pending);
                  }}
                  onSaved={async (updated, complete = true) => {
                    client.setQueryData(["page", updated.id], updated);
                    await refresh();
                    if (pending && complete) go(pending);
                  }}
                />
              )}
            </>
          ) : (
            <EmptyState title="Пространство для твоих мыслей" icon="▤">
              <p>
                Выбери страницу слева или создай новую.
                <br />
                Предметы и учебная группа не нужны.
              </p>
              <button
                className="primary-button"
                onClick={() => { startCreating(null); if (window.matchMedia("(max-width: 1100px)").matches) setTreeOpen(true); }}
              >
                Создать страницу
              </button>
            </EmptyState>
          )}
        </div>
      </div>

    </div>
  );
}

function NoteEditor({
  note,
  pages,
  onSelect,
  onDirtyChange,
  onBusyChange,
  onSaved,
  focusTitle,
  intent,
  onCloseIntent,
  pending,
  onCancelPending,
  onDiscard,
}: {
  note: Note;
  pages: PageSummary[];
  onSelect: (id: string) => void;
  onDirtyChange: (dirty: boolean) => void;
  onBusyChange: (busy: boolean) => void;
  onSaved: (note: Note, complete?: boolean) => Promise<void>;
  focusTitle: boolean;
  intent: Destination | null;
  onCloseIntent: () => void;
  pending: Destination | null;
  onCancelPending: () => void;
  onDiscard: () => void;
}) {
  const draft = useNoteDraft(note, onDirtyChange, onSaved);
  const { title, parent, blocks, version, dirty, saving } = draft;
  const setTitle = (value: string) => draft.update({ title: value });
  const setParent = (value: string) => draft.update({ parent: value });
  const setBlocks = (value: Block[]) => draft.update({ blocks: value });
  const [trashConfirm, setTrashConfirm] = useState(false);
  const [reloadConfirm, setReloadConfirm] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
  const [navigationError, setNavigationError] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const action = useAction();
  const readonly = !!note.trashed_at;
  const restoreRoot =
    readonly && note.trash_batch_id && note.trash_batch_id !== note.id
      ? note.trash_batch_id
      : null;
  const locked = readonly || action.busy;
  const operationsLocked = action.busy || saving;
  const error = draft.error || (readonly ? action.error : "");
  useLayoutEffect(() => {
    onBusyChange(operationsLocked);
    return () => onBusyChange(false);
  }, [operationsLocked, onBusyChange]);
  useEffect(() => {
    const editor = form.current;
    function shortcut(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (dirty && !locked) {
          if (saving && editor?.checkValidity()) void draft.save();
          else if (!saving) editor?.requestSubmit();
        }
      }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [dirty, locked, saving, draft]);
  const links = useQuery({
    queryKey: ["page-events", note.id],
    queryFn: ({ signal }) =>
      requestJson<{
        items: {
          event: { title: string; starts_at: string; source_status: string };
        }[];
      }>(`/api/v1/relations/pages/${note.id}/calendar-events?limit=50`, {
        signal,
      }),
  });
  const ancestors: PageSummary[] = [];
  const seen = new Set([note.id]);
  let ancestorId = parent;
  while (ancestorId && !seen.has(ancestorId)) {
    seen.add(ancestorId);
    const ancestor = pages.find((page) => page.id === ancestorId);
    if (!ancestor) break;
    ancestors.unshift(ancestor);
    ancestorId = ancestor.parent_id ?? "";
  }
  function validParent(page: PageSummary) {
    const visited = new Set<string>();
    let current: PageSummary | undefined = page;
    while (current) {
      if (current.id === note.id || visited.has(current.id)) return false;
      visited.add(current.id);
      current = pages.find((item) => item.id === current!.parent_id);
    }
    return !page.trashed_at;
  }
  async function adopt(fresh: Note) {
    draft.adopt(fresh);
    await onSaved(fresh);
  }
  function save() { if (locked) return Promise.resolve(false); return draft.save(); }
  const requested = intent?.id === note.id ? intent.action : undefined;
  function closeDialogs() {
    setMoveOpen(false);
    setTrashConfirm(false);
    onCloseIntent();
  }
  async function restore() {
    await action.run(async () => {
      await adopt(
        await writeJson<Note>(
          `/api/v1/notes/pages/${note.id}/restore`,
          "POST",
          { expected_version: version },
        ),
      );
      closeDialogs();
    }, "Страница восстановлена");
  }
  return (
    <>
      <form
        ref={form}
        id="note-editor-form"
        className="note-editor"
        tabIndex={-1}
        aria-label={`Документ: ${title}`}
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <header className="note-topbar">
          <nav className="note-breadcrumbs" aria-label="Положение страницы">
            <span>Страницы</span>
            {ancestors.map((page) => (
              <span key={page.id}>
                <span aria-hidden="true"> / </span>
                <button
                  type="button"
                  disabled={operationsLocked}
                  onClick={() => onSelect(page.id)}
                >
                  {page.title}
                </button>
              </span>
            ))}
            {parent && !ancestors.length && <span> / Родитель недоступен</span>}
            <span aria-current="page"> / {title}</span>
          </nav>
          <div className="note-top-actions">
            <span className="note-meta" role="status">
              {readonly
                ? "В корзине"
                : operationsLocked
                  ? "Сохраняем…"
                  : error
                    ? "Ошибка сохранения"
                    : dirty
                      ? "Есть изменения"
                      : "Сохранено"}{" "}
              <small>v{version}</small>
            </span>
            {!readonly && (
              <button
                className="secondary-button note-save-button"
                aria-label="Сохранить страницу"
                disabled={!dirty || operationsLocked}
              >
                Сохранить
              </button>
            )}
            {readonly && (
              <button
                type="button"
                className="secondary-button"
                disabled={operationsLocked}
                onClick={() =>
                  restoreRoot ? onSelect(restoreRoot) : void restore()
                }
              >
                {restoreRoot
                  ? "Открыть корень удалённой ветки"
                  : "Восстановить страницу"}
              </button>
            )}
            <details
              className="note-menu"
              onToggle={event => positionNoteMenu(event.currentTarget)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  event.currentTarget.open = false;
                  event.currentTarget.querySelector("summary")?.focus();
                }
              }}
            >
              <summary aria-label="Действия страницы">···</summary>
              <div
                className="note-menu-items"
                onClick={(event) => {
                  if ((event.target as HTMLElement).closest("button"))
                    event.currentTarget
                      .closest("details")
                      ?.removeAttribute("open");
                }}
              >
                <button
                  type="button"
                  onClick={async () => {
                    const url = new URL(workspaceHref({ section: "notes", pageId: note.id }), window.location.origin);
                    try {
                      await navigator.clipboard.writeText(url.href);
                      setCopyNotice("Ссылка скопирована");
                    } catch {
                      setCopyNotice("Не удалось скопировать ссылку");
                    }
                  }}
                >
                  Копировать ссылку
                </button>
                {!readonly && (
                  <>
                    <button
                      type="button"
                      disabled={operationsLocked}
                      onClick={() => setMoveOpen(true)}
                    >
                      Переместить
                    </button>
                    <button
                      type="button"
                      className="danger-text"
                      disabled={operationsLocked}
                      onClick={() => setTrashConfirm(true)}
                    >
                      В корзину
                    </button>
                  </>
                )}
              </div>
            </details>
          </div>
        </header>
        <div className="note-sheet" onClick={event => {
          if (!locked && event.target === event.currentTarget && !window.getSelection()?.toString())
            event.currentTarget.querySelector<HTMLTextAreaElement>(".block-empty-line")?.focus();
        }}>
          {copyNotice && (
            <p role="status" className="muted">
              {copyNotice}
            </p>
          )}
          <label className="sr-only" htmlFor="note-title">
            Название страницы
          </label>
          <textarea
            id="note-title"
            name="title"
            className="note-title"
            aria-label="Название страницы"
            value={title}
            maxLength={200}
            required
            rows={1}
            autoFocus={focusTitle}
            disabled={locked}
            ref={element => {
              if (element) { element.style.height = "auto"; element.style.height = `${element.scrollHeight}px`; }
            }}
            onKeyDown={event => {
              if (event.key === "Enter" && !event.nativeEvent.isComposing) {
                event.preventDefault();
                form.current?.querySelector<HTMLElement>(".blocks-editor .block-text, .block-empty-line")?.focus();
              }
            }}
            onChange={event => {
              const value = event.target.value.replace(/[\r\n]+/g, " ");
              event.currentTarget.setCustomValidity(value.trim() ? "" : "Укажи название страницы.");
              setTitle(value);
            }}
          />
          <NoteBlocks
            key={draft.epoch}
            blocks={blocks}
            disabled={locked}
            readonly={readonly}
            onChange={(next) => {
              setBlocks(next);
            }}
          />
          <ActionFeedback error={error} notice="" />
          {error && (
            <div className="note-conflict-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setReloadConfirm(true)}
              >
                Загрузить последнюю версию
              </button>
              <button
                type="button"
                className="text-action"
                onClick={() =>
                  form.current
                    ?.querySelector<HTMLTextAreaElement>(".note-title")
                    ?.focus()
                }
              >
                Остаться в редакторе
              </button>
            </div>
          )}
        </div>
      </form>
      <div className="note-sheet note-related-content">
        <details className="note-relations">
          <summary>
            Связанные события
            {links.data?.items.length ? ` · ${links.data.items.length}` : ""}
          </summary>
          <p className="muted">
            Связь не меняет содержимое страницы или события.
          </p>
          <QueryState
            pending={links.isPending}
            error={links.error}
            retry={() => void links.refetch()}
          />
          {links.data?.items.length === 0 && (
            <p className="muted">Страница пока не связана с событиями.</p>
          )}
          {links.data?.items.map((item, index) => (
            <div className="relation-row" key={index}>
              <span>{item.event.title}</span>
              <small>
                {item.event.starts_at.slice(0, 10)} ·{" "}
                {item.event.source_status === "active"
                  ? "активно"
                  : "историческая связь"}
              </small>
            </div>
          ))}
        </details>
        {pages.some((page) => page.parent_id === note.id) && (
          <section className="note-relations">
            <h3>Вложенные страницы</h3>
            {pages
              .filter((page) => page.parent_id === note.id)
              .map((page) => (
                <button
                  className="tree-row"
                  key={page.id}
                  disabled={operationsLocked}
                  onClick={() => onSelect(page.id)}
                >
                  ↳ {page.title}
                </button>
              ))}
          </section>
        )}
        <PageAttachments pageId={note.id} readonly={readonly} />
      </div>
      {(moveOpen || requested === "move") && (
        <Modal title="Переместить страницу" onClose={closeDialogs}>
          <h2>Переместить страницу</h2>
          <label htmlFor="page-parent">Родительская страница</label>
          <select
            id="page-parent"
            value={parent}
            disabled={locked}
            onChange={(event) => {
              setParent(event.target.value);
            }}
          >
            <option value="">Корневая страница</option>
            {pages.filter(validParent).map((page) => (
              <option key={page.id} value={page.id}>
                {page.title}
              </option>
            ))}
          </select>
          <p className="muted">
            Перемещение применится при сохранении страницы.
          </p>
          <div className="modal-actions">
            <button className="primary-button" onClick={closeDialogs}>
              Готово
            </button>
          </div>
        </Modal>
      )}
      {requested === "restore" && (
        <Modal title="Восстановить страницу" onClose={closeDialogs}>
          <h2>Восстановить страницу?</h2>
          <p>Восстановление выполняется для корня удалённой ветки.</p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button className="secondary-button" onClick={closeDialogs}>
              Отмена
            </button>
            <button
              className="primary-button"
              disabled={operationsLocked}
              onClick={() => {
                if (restoreRoot) {
                  closeDialogs();
                  onSelect(restoreRoot);
                } else void restore();
              }}
            >
              {restoreRoot ? "Открыть корень удалённой ветки" : "Восстановить"}
            </button>
          </div>
        </Modal>
      )}
      {pending && (
        <Modal
          title="Несохранённые изменения"
          onClose={() => {
            if (!action.busy) onCancelPending();
          }}
        >
          <h2>Сохранить изменения перед переходом?</h2>
          <p>
            Сохрани страницу или продолжи редактирование. Переход без сохранения
            удалит текущий черновик.
          </p>
          <ActionFeedback error={navigationError || error} notice="" />
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={operationsLocked}
              onClick={onCancelPending}
            >
              Продолжить редактирование
            </button>
            <button
              className="danger-button"
              disabled={operationsLocked}
              onClick={() => {
                draft.discard();
                onDiscard();
              }}
            >
              Перейти без сохранения
            </button>
            <button
              className="primary-button"
              disabled={operationsLocked}
              onClick={() => {
                if (form.current?.checkValidity()) {
                  setNavigationError("");
                  void save();
                } else
                  setNavigationError(
                    "Проверь название и адреса ссылок. Продолжи редактирование, чтобы исправить поля.",
                  );
              }}
            >
              Сохранить и перейти
            </button>
          </div>
        </Modal>
      )}
      {reloadConfirm && (
        <Modal
          title="Загрузить последнюю версию"
          onClose={() => setReloadConfirm(false)}
        >
          <h2>Загрузить версию с сервера?</h2>
          <p>Несохранённые изменения редактора будут заменены.</p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setReloadConfirm(false)}
            >
              Остаться
            </button>
            <button
              className="danger-button"
              disabled={operationsLocked}
              onClick={() =>
                void action.run(async () => {
                  await adopt(
                    await requestJson<Note>(`/api/v1/notes/pages/${note.id}`),
                  );
                  setReloadConfirm(false);
                }, "Последняя версия загружена")
              }
            >
              Загрузить версию
            </button>
          </div>
        </Modal>
      )}
      {(trashConfirm || requested === "trash") && (
        <Modal title="Убрать страницу в корзину" onClose={closeDialogs}>
          <h2>Убрать страницу в корзину?</h2>
          <p>
            Вложенные страницы тоже будут перемещены. Содержимое можно
            восстановить. Несохранённые изменения не попадут в корзину.
          </p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button
              className="secondary-button"
              disabled={operationsLocked}
              onClick={closeDialogs}
            >
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={operationsLocked}
              onClick={() =>
                void action.run(async () => {
                  await adopt(
                    await writeJson<Note>(
                      `/api/v1/notes/pages/${note.id}/trash`,
                      "POST",
                      { expected_version: version },
                    ),
                  );
                  closeDialogs();
                }, "Страница в корзине")
              }
            >
              В корзину
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
