"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PageAttachments } from "./attachments";
import { requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  Pager,
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
type Note = PageSummary & { document: { schema_version: 1; blocks: Block[] } };
type PageList = { items: PageSummary[]; limit: number; offset: number };

export function NotesPanel({
  initialPage,
  onDirtyChange,
}: {
  initialPage: string | null;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [selected, setSelected] = useState<string | null>(initialPage);
  const [offset, setOffset] = useState(0);
  const [trashed, setTrashed] = useState(false);
  const [creating, setCreating] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pendingPage, setPendingPage] = useState<string | null>(null);
  const client = useQueryClient();
  const action = useAction();
  const list = useQuery({
    queryKey: ["pages", trashed, offset],
    queryFn: ({ signal }) =>
      requestJson<PageList>(
        `/api/v1/notes/pages?trashed=${trashed}&limit=50&offset=${offset}`,
        { signal },
      ),
  });
  const note = useQuery({
    queryKey: ["page", selected],
    queryFn: ({ signal }) =>
      requestJson<Note>(`/api/v1/notes/pages/${selected}`, { signal }),
    enabled: !!selected,
  });
  const summaries = list.data?.items ?? [];
  function choose(id: string) {
    if (dirty && selected !== id) {
      setPendingPage(id);
      return;
    }
    setSelected(id);
  }
  function changeDirty(value: boolean) {
    setDirty(value);
    onDirtyChange(value);
  }
  useEffect(() => {
    function prevent(event: BeforeUnloadEvent) {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  async function refresh() {
    await client.invalidateQueries({ queryKey: ["pages"] });
  }
  function depth(page: PageSummary) {
    let count = 0,
      parent = page.parent_id;
    const seen = new Set<string>([page.id]);
    while (parent && count < 8 && !seen.has(parent)) {
      seen.add(parent);
      count++;
      parent = summaries.find((item) => item.id === parent)?.parent_id ?? null;
    }
    return count;
  }
  const ordered: PageSummary[] = [];
  const seen = new Set<string>();
  function append(page: PageSummary) {
    if (seen.has(page.id)) return;
    seen.add(page.id);
    ordered.push(page);
    summaries.filter((item) => item.parent_id === page.id).forEach(append);
  }
  summaries
    .filter(
      (page) =>
        !page.parent_id ||
        !summaries.some((item) => item.id === page.parent_id),
    )
    .forEach(append);
  summaries.forEach(append);

  return (
    <div className="feature-page notes-page">
      <div className="page-heading">
        <div>
          <span className="greeting">МЫСЛИ, КОТОРЫЕ ОСТАЮТСЯ</span>
          <h1>Заметки</h1>
          <p className="heading-subtitle">
            Знания и идеи, организованные по-твоему.
          </p>
        </div>
        <button className="primary-button" onClick={() => setCreating(true)}>
          + Новая страница
        </button>
      </div>
      <div className="notes-layout">
        <aside className="page-tree panel">
          <div className="panel-toolbar">
            <strong>Страницы</strong>
            <button
              className="text-action"
              onClick={() => {
                setTrashed((value) => !value);
                setOffset(0);
              }}
            >
              {trashed ? "Активные" : "Корзина"}
            </button>
          </div>
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
          <div
            role="list"
            aria-label={trashed ? "Удалённые страницы" : "Дерево страниц"}
          >
            {ordered.map((page) => (
              <div role="listitem" key={page.id}>
                <button
                  className={`tree-row ${selected === page.id ? "selected" : ""}`}
                  style={{ paddingLeft: `${12 + depth(page) * 14}px` }}
                  onClick={() => choose(page.id)}
                >
                  <span aria-hidden="true">{page.parent_id ? "↳" : "▤"}</span>
                  <span>{page.title}</span>
                  {page.trashed_at && <small>в корзине</small>}
                </button>
              </div>
            ))}
          </div>
          {(offset > 0 || summaries.length === 50) && (
            <Pager
              offset={offset}
              count={summaries.length}
              onChange={setOffset}
            />
          )}
        </aside>
        <div className="note-canvas panel">
          {selected ? (
            <>
              <QueryState
                pending={note.isPending}
                error={note.error}
                retry={() => void note.refetch()}
              />
              {note.data && (
                <NoteEditor
                  key={note.data.id}
                  note={note.data}
                  pages={summaries}
                  onSelect={choose}
                  onDirtyChange={changeDirty}
                  onSaved={async (updated) => {
                    client.setQueryData(["page", updated.id], updated);
                    await refresh();
                  }}
                />
              )}
            </>
          ) : (
            <EmptyState title="Пространство для твоих мыслей" icon="▤">
              <p>
                Выбери страницу слева или создай новую. Предметы и учебная
                группа не нужны.
              </p>
              <button
                className="primary-button"
                onClick={() => setCreating(true)}
              >
                Создать страницу
              </button>
            </EmptyState>
          )}
        </div>
      </div>
      <ActionFeedback {...action} />
      {creating && (
        <Modal title="Новая страница" onClose={() => setCreating(false)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              void action.run(async () => {
                const created = await writeJson<Note>(
                  "/api/v1/notes/pages",
                  "POST",
                  {
                    title: values.get("title"),
                    parent_id: values.get("parent") || null,
                  },
                );
                await refresh();
                if (!dirty) setSelected(created.id);
                setCreating(false);
              }, "Страница создана");
            }}
          >
            <span className="greeting">НОВАЯ МЫСЛЬ</span>
            <h2>Создать страницу</h2>
            <label htmlFor="new-page-title">Название страницы</label>
            <input
              id="new-page-title"
              name="title"
              maxLength={200}
              required
              autoFocus
              placeholder="Например, идеи для проекта"
            />
            <label htmlFor="new-page-parent">Родительская страница</label>
            <select id="new-page-parent" name="parent">
              <option value="">Без родительской страницы</option>
              {summaries
                .filter((page) => !page.trashed_at)
                .map((page) => (
                  <option key={page.id} value={page.id}>
                    {page.title}
                  </option>
                ))}
            </select>
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setCreating(false)}
              >
                Отмена
              </button>
              <button className="primary-button" disabled={action.busy}>
                Создать
              </button>
            </div>
          </form>
        </Modal>
      )}
      {pendingPage && (
        <Modal
          title="Несохранённые изменения"
          onClose={() => setPendingPage(null)}
        >
          <h2>Перейти к другой странице?</h2>
          <p>Несохранённый текст останется только в текущем редакторе.</p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setPendingPage(null)}
            >
              Остаться
            </button>
            <button
              className="danger-button"
              onClick={() => {
                changeDirty(false);
                setSelected(pendingPage);
                setPendingPage(null);
              }}
            >
              Перейти без сохранения
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function NoteEditor({
  note,
  pages,
  onSelect,
  onDirtyChange,
  onSaved,
}: {
  note: Note;
  pages: PageSummary[];
  onSelect: (id: string) => void;
  onDirtyChange: (dirty: boolean) => void;
  onSaved: (note: Note) => Promise<void>;
}) {
  const [title, setTitle] = useState(note.title);
  const [parent, setParent] = useState(note.parent_id ?? "");
  const [blocks, setBlocks] = useState<Block[]>(note.document.blocks);
  const [version, setVersion] = useState(note.version);
  const [dirty, setDirty] = useState(false);
  const [trashConfirm, setTrashConfirm] = useState(false);
  const [reloadConfirm, setReloadConfirm] = useState(false);
  const [addType, setAddType] = useState<Block["type"]>("text");
  const action = useAction();
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
  async function adopt(fresh: Note) {
    setTitle(fresh.title);
    setParent(fresh.parent_id ?? "");
    setBlocks(fresh.document.blocks);
    setVersion(fresh.version);
    setDirty(false);
    onDirtyChange(false);
    await onSaved(fresh);
  }
  function changed() {
    setDirty(true);
    onDirtyChange(true);
  }
  function update(index: number, value: Block) {
    changed();
    setBlocks((items) => items.map((item, i) => (i === index ? value : item)));
  }
  function addBlock() {
    if (blocks.length >= 1000) return;
    const id = crypto.randomUUID();
    const block: Block =
      addType === "list"
        ? { id, type: "list", items: [""], style: "bulleted" }
        : addType === "heading"
          ? { id, type: "heading", text: "", level: 2 }
          : addType === "checkbox"
            ? { id, type: "checkbox", text: "", checked: false }
            : addType === "link"
              ? { id, type: "link", text: "", url: "" }
              : { id, type: "text", text: "", text_format: "plain" };
    changed();
    setBlocks((items) => [...items, block]);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    await action.run(async () => {
      let current = note;
      if (title !== note.title || parent !== (note.parent_id ?? "")) {
        current = await writeJson<Note>(
          `/api/v1/notes/pages/${note.id}`,
          "PATCH",
          { title, parent_id: parent || null, expected_version: version },
        );
        setVersion(current.version);
      } else current = { ...note, version };
      const result = await writeJson<{
        version: number;
        document: Note["document"];
      }>(`/api/v1/notes/pages/${note.id}/document`, "PUT", {
        expected_version: current.version,
        document: { schema_version: 1, blocks },
      });
      setVersion(result.version);
      setDirty(false);
      onDirtyChange(false);
      await onSaved({
        ...current,
        title,
        parent_id: parent || null,
        ...result,
      });
    });
  }
  return (
    <>
      <form className="note-editor" onSubmit={(event) => void save(event)}>
        <div className="note-meta">
          <span>
            СТРАНИЦА ·{" "}
            {note.trashed_at
              ? "В КОРЗИНЕ"
              : dirty
                ? "ЕСТЬ ИЗМЕНЕНИЯ"
                : "СОХРАНЕНО"}
          </span>
          <span>v{version}</span>
        </div>
        <input
          className="note-title"
          aria-label="Название страницы"
          value={title}
          maxLength={200}
          required
          disabled={!!note.trashed_at || action.busy}
          onChange={(event) => {
            setTitle(event.target.value);
            changed();
          }}
        />
        <div className="note-location">
          <label htmlFor="page-parent">Вложенность</label>
          <select
            id="page-parent"
            value={parent}
            disabled={!!note.trashed_at || action.busy}
            onChange={(event) => {
              setParent(event.target.value);
              changed();
            }}
          >
            <option value="">Корневая страница</option>
            {pages
              .filter((page) => page.id !== note.id && !page.trashed_at)
              .map((page) => (
                <option key={page.id} value={page.id}>
                  {page.title}
                </option>
              ))}
          </select>
        </div>
        <div className="blocks-editor">
          {blocks.map((block, index) => (
            <div className={`block-row block-${block.type}`} key={block.id}>
              <div className="block-tools">
                <span>{index + 1}</span>
                <button
                  type="button"
                  aria-label={`Поднять блок ${index + 1}`}
                  disabled={!index || !!note.trashed_at || action.busy}
                  onClick={() => {
                    changed();
                    setBlocks((items) => {
                      const next = [...items];
                      [next[index - 1], next[index]] = [
                        next[index],
                        next[index - 1],
                      ];
                      return next;
                    });
                  }}
                >
                  ↑
                </button>
                <button
                  type="button"
                  aria-label={`Опустить блок ${index + 1}`}
                  disabled={
                    index === blocks.length - 1 ||
                    !!note.trashed_at ||
                    action.busy
                  }
                  onClick={() => {
                    changed();
                    setBlocks((items) => {
                      const next = [...items];
                      [next[index], next[index + 1]] = [
                        next[index + 1],
                        next[index],
                      ];
                      return next;
                    });
                  }}
                >
                  ↓
                </button>
              </div>
              <div className="block-content">
                {block.type === "heading" && (
                  <>
                    <select
                      aria-label={`Уровень заголовка ${index + 1}`}
                      value={block.level}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, {
                          ...block,
                          level: Number(event.target.value),
                        })
                      }
                    >
                      {[1, 2, 3, 4, 5, 6].map((level) => (
                        <option key={level} value={level}>
                          H{level}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label={`Заголовок ${index + 1}`}
                      value={block.text}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, { ...block, text: event.target.value })
                      }
                    />
                  </>
                )}
                {block.type === "text" && (
                  <>
                    <label className="block-kind">
                      {block.text_format === "markdown"
                        ? "Markdown · исходный формат"
                        : "Текст"}
                    </label>
                    <textarea
                      aria-label={`Текст блока ${index + 1}`}
                      value={block.text}
                      disabled={!!note.trashed_at || action.busy}
                      placeholder="Начни писать…"
                      onChange={(event) =>
                        update(index, { ...block, text: event.target.value })
                      }
                    />
                  </>
                )}
                {block.type === "checkbox" && (
                  <div className="checkbox-block">
                    <input
                      type="checkbox"
                      aria-label={`Отметить пункт ${index + 1}`}
                      checked={block.checked}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, {
                          ...block,
                          checked: event.target.checked,
                        })
                      }
                    />
                    <input
                      aria-label={`Пункт ${index + 1}`}
                      value={block.text}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, { ...block, text: event.target.value })
                      }
                    />
                  </div>
                )}
                {block.type === "list" && (
                  <>
                    <select
                      aria-label={`Вид списка ${index + 1}`}
                      value={block.style}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, {
                          ...block,
                          style: event.target.value as "bulleted" | "numbered",
                        })
                      }
                    >
                      <option value="bulleted">Маркированный</option>
                      <option value="numbered">Нумерованный</option>
                    </select>
                    <textarea
                      aria-label={`Список ${index + 1}`}
                      value={block.items.join("\n")}
                      disabled={!!note.trashed_at || action.busy}
                      placeholder="Каждый пункт с новой строки"
                      onChange={(event) =>
                        update(index, {
                          ...block,
                          items: event.target.value.split("\n"),
                        })
                      }
                    />
                  </>
                )}
                {block.type === "link" && (
                  <>
                    <input
                      aria-label={`Текст ссылки ${index + 1}`}
                      value={block.text}
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, { ...block, text: event.target.value })
                      }
                    />
                    <input
                      type="url"
                      aria-label={`Адрес ссылки ${index + 1}`}
                      value={block.url}
                      required
                      disabled={!!note.trashed_at || action.busy}
                      onChange={(event) =>
                        update(index, { ...block, url: event.target.value })
                      }
                    />
                  </>
                )}
              </div>
              {!note.trashed_at && (
                <button
                  className="block-remove"
                  type="button"
                  aria-label={`Удалить блок ${index + 1}`}
                  disabled={action.busy}
                  onClick={() => {
                    changed();
                    setBlocks((items) =>
                      items.filter((item) => item.id !== block.id),
                    );
                  }}
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
        {!note.trashed_at && (
          <div className="block-add">
            <select
              aria-label="Тип нового блока"
              value={addType}
              onChange={(event) =>
                setAddType(event.target.value as Block["type"])
              }
            >
              <option value="text">Текст</option>
              <option value="heading">Заголовок</option>
              <option value="list">Список</option>
              <option value="checkbox">Чекбокс</option>
              <option value="link">Ссылка</option>
            </select>
            <button
              className="secondary-button"
              type="button"
              disabled={blocks.length >= 1000 || action.busy}
              onClick={addBlock}
            >
              + Добавить блок
            </button>
          </div>
        )}
        <ActionFeedback {...action} />
        {action.error && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => setReloadConfirm(true)}
          >
            Загрузить последнюю версию
          </button>
        )}
        <div className="note-footer">
          <button
            type="button"
            className={
              note.trashed_at ? "secondary-button" : "text-action danger-text"
            }
            disabled={action.busy}
            onClick={() =>
              note.trashed_at
                ? void action.run(async () => {
                    const restored = await writeJson<Note>(
                      `/api/v1/notes/pages/${note.id}/restore`,
                      "POST",
                      { expected_version: version },
                    );
                    await adopt(restored);
                  }, "Страница восстановлена")
                : setTrashConfirm(true)
            }
          >
            {note.trashed_at ? "Восстановить страницу" : "В корзину"}
          </button>
          {!note.trashed_at && (
            <button className="primary-button" disabled={!dirty || action.busy}>
              {action.busy ? "Сохраняем…" : "Сохранить страницу"}
            </button>
          )}
        </div>
      </form>
      <section className="note-relations">
        <h3>Связанные события</h3>
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
        {pages
          .filter((page) => page.parent_id === note.id)
          .map((page) => (
            <button
              className="tree-row"
              key={page.id}
              onClick={() => onSelect(page.id)}
            >
              ↳ {page.title}
            </button>
          ))}
      </section>
      <PageAttachments pageId={note.id} readonly={!!note.trashed_at} />
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
              disabled={action.busy}
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
      {trashConfirm && (
        <Modal
          title="Убрать страницу в корзину"
          onClose={() => setTrashConfirm(false)}
        >
          <h2>Убрать страницу в корзину?</h2>
          <p>
            Вложенные страницы тоже будут перемещены. Содержимое можно
            восстановить. Несохранённые изменения не попадут в корзину.
          </p>
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setTrashConfirm(false)}
            >
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  const removed = await writeJson<Note>(
                    `/api/v1/notes/pages/${note.id}/trash`,
                    "POST",
                    { expected_version: version },
                  );
                  await adopt(removed);
                  setTrashConfirm(false);
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
