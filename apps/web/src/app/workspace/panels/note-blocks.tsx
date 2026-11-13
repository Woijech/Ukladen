"use client";

import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { positionNoteMenu } from "./note-menu";
import type { Block } from "./notes";

const blockTypes = [
  { key: "text", label: "Текст", icon: "Т", hint: "Обычный абзац" },
  ...[1, 2, 3, 4, 5, 6].map((level) => ({
    key: `h${level}`,
    label: `Заголовок H${level}`,
    icon: `H${level}`,
    hint: "Раздел страницы",
  })),
  {
    key: "bulleted",
    label: "Маркированный список",
    icon: "•",
    hint: "Пункты с маркерами",
  },
  {
    key: "numbered",
    label: "Нумерованный список",
    icon: "1.",
    hint: "Пункты по порядку",
  },
  { key: "checkbox", label: "Чекбокс", icon: "☑", hint: "Отмечаемый пункт" },
  { key: "link", label: "Ссылка", icon: "↗", hint: "Подпись и веб-адрес" },
];

function newBlock(key: string, id = crypto.randomUUID(), text = ""): Block {
  if (/^h[1-6]$/.test(key))
    return { id, type: "heading", text, level: Number(key.slice(1)) };
  if (key === "bulleted" || key === "numbered")
    return { id, type: "list", items: [text], style: key };
  if (key === "checkbox") return { id, type: "checkbox", text, checked: false };
  if (key === "link") return { id, type: "link", text, url: "" };
  return { id, type: "text", text, text_format: "plain" };
}

function BlockMenu({
  onSelect,
  onClose,
  anchor,
}: {
  onSelect: (key: string) => void;
  onClose: (restoreFocus?: boolean) => void;
  anchor: DOMRect | null;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 8, left: 8 });
  useLayoutEffect(() => {
    const height = container.current?.getBoundingClientRect().height ?? 360;
    setPosition({ top: Math.max(8, Math.min(anchor?.bottom ?? 8, window.innerHeight - height - 8)), left: Math.max(8, Math.min(anchor?.left ?? 8, window.innerWidth - 328)) });
  }, [anchor]);
  useEffect(() => {
    function outside(event: PointerEvent) { if (!container.current?.contains(event.target as Node)) onClose(false); }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [onClose]);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const matches = blockTypes.filter((type) =>
    type.label.toLowerCase().includes(search.toLowerCase()),
  );
  function keys(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActive(
        (index) =>
          (index + (event.key === "ArrowDown" ? 1 : -1) + matches.length) %
          (matches.length || 1),
      );
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (matches[active]) onSelect(matches[active].key);
    }
  }
  return createPortal(
    <div
      ref={container}
      style={position}
      className="block-picker"
      role="dialog"
      aria-label="Добавить блок"
      onKeyDown={keys}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) onClose(false);
      }}
    >
      <input
        autoFocus
        aria-label="Найти тип блока"
        role="combobox"
        aria-expanded="true"
        aria-controls="block-type-options"
        aria-autocomplete="list"
        aria-activedescendant={
          matches[active] ? `block-option-${matches[active].key}` : undefined
        }
        value={search}
        placeholder="Найти блок…"
        onChange={(event) => {
          setSearch(event.target.value);
          setActive(0);
        }}
      />
      <div id="block-type-options" role="listbox" aria-label="Типы блоков">
        {matches.map((type, index) => (
          <button
            type="button"
            role="option"
            tabIndex={-1}
            id={`block-option-${type.key}`}
            aria-selected={index === active}
            className={index === active ? "active" : ""}
            key={type.key}
            ref={(element) => {
              if (index === active)
                element?.scrollIntoView({ block: "nearest" });
            }}
            onPointerDown={(event) => event.preventDefault()}
            onClick={() => onSelect(type.key)}
          >
            <span className="block-type-symbol" aria-hidden="true">
              {type.icon}
            </span>
            <span>
              {type.label}
              <small>{type.hint}</small>
            </span>
          </button>
        ))}
        {!matches.length && <p className="muted">Блок не найден</p>}
      </div>
      <small className="block-picker-hint">
        ↑ ↓ выбор · Enter добавить · Esc закрыть
      </small>
    </div>, document.body
  );
}

export function NoteBlocks({
  blocks,
  disabled,
  readonly,
  onChange,
}: {
  blocks: Block[];
  disabled: boolean;
  readonly: boolean;
  onChange: (blocks: Block[]) => void;
}) {
  const [menu, setMenu] = useState<{ index: number; replace: boolean; anchor: DOMRect | null } | null>(
    null,
  );
  const [undo, setUndo] = useState<{ block: Block; index: number; before?: string; after?: string; removed: boolean } | null>(null);
  const [drop, setDrop] = useState<{ id: string; after: boolean } | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const dragging = useRef<string | null>(null);
  const pendingFocus = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (!pendingFocus.current) return;
    const input = root.current?.querySelector<
      HTMLInputElement | HTMLTextAreaElement
    >(pendingFocus.current);
    if (input) {
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      pendingFocus.current = null;
    }
  });
  function focus(id: string, selector = ".block-text") {
    pendingFocus.current = `[data-block-id="${id}"] ${selector}`;
  }
  function remember(index: number, removed: boolean) {
    setUndo({ block: blocks[index], index, before: blocks[index - 1]?.id, after: blocks[index + 1]?.id, removed });
  }
  function undoStructure() {
    if (!undo || disabled) return;
    const block = undo.removed ? undo.block : blocks.find(item => item.id === undo.block.id);
    if (!block || (undo.removed && blocks.length >= 1000)) return;
    const next = blocks.filter(item => item.id !== block.id);
    const after = next.findIndex(item => item.id === undo.after);
    const before = next.findIndex(item => item.id === undo.before);
    next.splice(after >= 0 ? after : before >= 0 ? before + 1 : Math.min(undo.index, next.length), 0, block);
    onChange(next); setUndo(null); focus(block.id);
  }
  function removeBlock(index: number) {
    remember(index, true);
    onChange(blocks.filter((_, position) => position !== index));
    const next = blocks[index + 1] ?? blocks[index - 1];
    if (next) focus(next.id);
    else pendingFocus.current = ".block-empty-line";
  }
  function update(index: number, block: Block) {
    onChange(blocks.map((item, i) => (i === index ? block : item)));
  }
  function move(from: number, to: number) {
    if (disabled || from === to || to < 0 || to >= blocks.length) return;
    remember(from, false);
    const next = [...blocks];
    const [block] = next.splice(from, 1);
    next.splice(to, 0, block);
    onChange(next);
  }
  function add(key: string) {
    if (!menu || disabled || (!menu.replace && blocks.length >= 1000)) return;
    const block = newBlock(
      key,
      menu.replace ? blocks[menu.index].id : undefined,
    );
    const next = [...blocks];
    next.splice(menu.index, menu.replace ? 1 : 0, block);
    onChange(next);
    setMenu(null);
    focus(block.id);
  }
  function openMenu(index: number, replace = false) {
    if (!disabled) {
      const active = document.activeElement;
      setMenu({ index, replace, anchor: active instanceof HTMLElement ? active.getBoundingClientRect() : null });
    }
  }
  function blockKeys(
    event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>,
    block: Block,
    index: number,
  ) {
    if (
      event.key === "/" &&
      event.currentTarget.value === "" &&
      block.type === "text"
    ) {
      event.preventDefault();
      openMenu(index, true);
    }
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing &&
      block.type === "text" &&
      block.text_format === "plain" &&
      blocks.length < 1000
    ) {
      event.preventDefault();
      const input = event.currentTarget;
      const start = input.selectionStart ?? block.text.length;
      const end = input.selectionEnd ?? start;
      const next = [...blocks];
      const added = newBlock("text", undefined, block.text.slice(end));
      next.splice(
        index,
        1,
        { ...block, text: block.text.slice(0, start) },
        added,
      );
      onChange(next);
      focus(added.id);
    }
  }
  function closeMenu(restoreFocus = true) {
    if (!menu) return;
    const id = menu.replace
      ? blocks[menu.index]?.id
      : blocks[menu.index - 1]?.id;
    setMenu(null);
    if (!restoreFocus) return;
    if (id) focus(id);
    else
      root.current
        ?.querySelector<HTMLTextAreaElement>(".block-empty-line")
        ?.focus();
  }
  function picker(index: number) {
    return (
      menu?.index === index && <BlockMenu anchor={menu.anchor} onSelect={add} onClose={closeMenu} />
    );
  }
  return (
    <div ref={root} className="blocks-editor">
      {blocks.map((block, index) => {
        const List =
          block.type === "list" && block.style === "numbered" ? "ol" : "ul";
        return (
          <div
            key={block.id}
            data-block-id={block.id}
            className={`block-row block-${block.type} ${drop?.id === block.id ? drop.after ? "drop-after" : "drop-before" : ""}`}
            onDragOver={(event) => {
              if (dragging.current && !disabled) {
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                const bounds = event.currentTarget.getBoundingClientRect();
                setDrop({ id: block.id, after: event.clientY > bounds.top + bounds.height / 2 });
              }
            }}
            onDrop={(event) => {
              event.preventDefault();
              const from = blocks.findIndex(
                (item) => item.id === dragging.current,
              );
              const target = index + (drop?.id === block.id && drop.after ? 1 : 0);
              if (from >= 0) move(from, Math.min(blocks.length - 1, target > from ? target - 1 : target));
              dragging.current = null; setDrop(null);
            }}
          >
            {!readonly && (
              <div className="block-tools">
                <button
                  type="button"
                  className="block-insert"
                  aria-label={`Добавить блок перед ${index + 1}`}
                  disabled={disabled || blocks.length >= 1000}
                  onClick={() => openMenu(index)}
                >
                  +
                </button>
                <details
                  className="note-menu block-context"
                  onToggle={event => positionNoteMenu(event.currentTarget)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      event.currentTarget.open = false;
                      event.currentTarget.querySelector("summary")?.focus();
                    }
                  }}
                >
                  <summary
                    aria-label={`Действия блока ${index + 1}`}
                    draggable={!disabled}
                    onDragStart={(event) => {
                      if (disabled) {
                        event.preventDefault();
                        return;
                      }
                      dragging.current = block.id;
                      event.dataTransfer.effectAllowed = "move";
                      event.dataTransfer.setData("text/plain", block.id);
                    }}
                    onDragEnd={() => {
                      dragging.current = null; setDrop(null);
                    }}
                  >
                    ⠿
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
                    <button type="button" disabled={disabled || blocks.length >= 1000} onClick={() => openMenu(index)}>Добавить блок перед этим</button>
                    <button
                      type="button"
                      disabled={disabled || index === 0}
                      aria-label={`Поднять блок ${index + 1}`}
                      onClick={() => move(index, index - 1)}
                    >
                      ↑ Переместить выше
                    </button>
                    <button
                      type="button"
                      disabled={disabled || index === blocks.length - 1}
                      aria-label={`Опустить блок ${index + 1}`}
                      onClick={() => move(index, index + 1)}
                    >
                      ↓ Переместить ниже
                    </button>
                    {((block.type === "text" &&
                      block.text_format === "plain" &&
                      !/[\r\n]/.test(block.text)) ||
                      block.type === "heading") && (
                      <>
                        <label htmlFor={`convert-${block.id}`}>
                          Преобразовать в
                        </label>
                        <select
                          id={`convert-${block.id}`}
                          aria-label={`Тип блока ${index + 1}`}
                          disabled={disabled}
                          value={
                            block.type === "heading"
                              ? `h${block.level}`
                              : "text"
                          }
                          onChange={(event) =>
                            update(
                              index,
                              newBlock(
                                event.target.value,
                                block.id,
                                block.text,
                              ),
                            )
                          }
                        >
                          <option value="text">Текст</option>
                          {[1, 2, 3, 4, 5, 6].map((level) => (
                            <option key={level} value={`h${level}`}>
                              Заголовок H{level}
                            </option>
                          ))}
                        </select>
                      </>
                    )}
                    {block.type === "list" && (
                      <>
                        <label htmlFor={`style-${block.id}`}>Вид списка</label>
                        <select
                          id={`style-${block.id}`}
                          aria-label={`Вид списка ${index + 1}`}
                          value={block.style}
                          disabled={disabled}
                          onChange={(event) =>
                            update(index, {
                              ...block,
                              style: event.target.value as
                                | "bulleted"
                                | "numbered",
                            })
                          }
                        >
                          <option value="bulleted">Маркеры</option>
                          <option value="numbered">Нумерация</option>
                        </select>
                      </>
                    )}
                    <button
                      type="button"
                      className="danger-text"
                      aria-label={`Удалить блок ${index + 1}`}
                      disabled={disabled}
                      onClick={() => removeBlock(index)}
                    >
                      Удалить блок
                    </button>
                  </div>
                </details>
              </div>
            )}
            <div className="block-content">
              {block.type === "text" && (
                <>
                  {block.text_format === "markdown" && (
                    <small className="block-markdown-hint">Markdown</small>
                  )}
                  <textarea
                    className="block-text"
                    aria-label={`Текст блока ${index + 1}`}
                    value={block.text}
                    disabled={disabled}
                    placeholder="Начни писать или нажми / для выбора блока"
                    rows={1}
                    ref={(element) => {
                      if (element) {
                        element.style.height = "auto";
                        element.style.height = `${element.scrollHeight}px`;
                      }
                    }}
                    onKeyDown={(event) => blockKeys(event, block, index)}
                    onChange={(event) =>
                      update(index, { ...block, text: event.target.value })
                    }
                  />
                </>
              )}
              {block.type === "heading" && (
                <div
                  role="heading"
                  aria-level={block.level}
                  className={`note-heading heading-${block.level}`}
                >
                  <input
                    className="block-text"
                    aria-label={`Заголовок блока ${index + 1}`}
                    value={block.text}
                    placeholder={`Заголовок ${block.level}`}
                    disabled={disabled}
                    onChange={(event) =>
                      update(index, { ...block, text: event.target.value })
                    }
                  />
                </div>
              )}
              {block.type === "checkbox" && (
                <div
                  className={`checkbox-block ${block.checked ? "checked" : ""}`}
                >
                  <label className="block-check-control">
                  <input
                    type="checkbox"
                    aria-label={`Отметить пункт ${index + 1}`}
                    checked={block.checked}
                    disabled={disabled}
                    onChange={(event) =>
                      update(index, { ...block, checked: event.target.checked })
                    }
                  />
                  </label>
                  <input
                    className="block-text"
                    aria-label={`Пункт ${index + 1}`}
                    placeholder="Что нужно сделать?"
                    value={block.text}
                    disabled={disabled}
                    onChange={(event) =>
                      update(index, { ...block, text: event.target.value })
                    }
                  />
                </div>
              )}
              {block.type === "list" && (
                <List className="note-list">
                  {block.items.map((item, itemIndex) => (
                    <li key={itemIndex}>
                      <input
                        className="block-text"
                        aria-label={`Список ${index + 1}, пункт ${itemIndex + 1}`}
                        value={item}
                        placeholder="Пункт списка"
                        disabled={disabled}
                        onKeyDown={(event) => {
                          if (event.nativeEvent.isComposing) return;
                          if (
                            event.key === "Enter" &&
                            block.items.length < 1000
                          ) {
                            event.preventDefault();
                            const items = [...block.items];
                            items.splice(itemIndex + 1, 0, "");
                            update(index, { ...block, items });
                            focus(
                              block.id,
                              `li:nth-child(${itemIndex + 2}) input`,
                            );
                          }
                          if (
                            event.key === "Backspace" &&
                            !item &&
                            block.items.length > 1
                          ) {
                            event.preventDefault();
                            update(index, {
                              ...block,
                              items: block.items.filter(
                                (_, i) => i !== itemIndex,
                              ),
                            });
                            focus(
                              block.id,
                              `li:nth-child(${Math.max(1, itemIndex)}) input`,
                            );
                          }
                        }}
                        onChange={(event) =>
                          update(index, {
                            ...block,
                            items: block.items.map((value, i) =>
                              i === itemIndex ? event.target.value : value,
                            ),
                          })
                        }
                      />
                    </li>
                  ))}
                </List>
              )}
              {block.type === "link" && (
                <div className="note-link-block">
                  {/^https?:\/\//i.test(block.url) && (
                    <a
                      href={block.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {block.text || block.url} ↗
                    </a>
                  )}
                  {!readonly && (
                    <details
                      className="note-link-edit"
                      ref={(element) => {
                        if (element && !block.url) element.open = true;
                      }}
                    >
                      <summary>Изменить ссылку</summary>
                      <input
                        className="block-text"
                        aria-label={`Подпись ссылки ${index + 1}`}
                        placeholder="Подпись ссылки"
                        value={block.text}
                        disabled={disabled}
                        onChange={(event) =>
                          update(index, { ...block, text: event.target.value })
                        }
                      />
                      <input
                        className="block-url"
                        type="url"
                        pattern="https?://.*"
                        aria-label={`Адрес ссылки ${index + 1}`}
                        value={block.url}
                        placeholder="https://"
                        required
                        maxLength={2048}
                        disabled={disabled}
                        onChange={(event) =>
                          update(index, { ...block, url: event.target.value })
                        }
                      />
                    </details>
                  )}
                </div>
              )}
            </div>
            {picker(index)}
          </div>
        );
      })}
      {!readonly && (
        <div className="block-empty-row">
          <button
            type="button"
            className="block-empty-add"
            aria-label="Добавить блок"
            disabled={disabled || blocks.length >= 1000}
            onClick={() => openMenu(blocks.length)}
          >
            +
          </button>
          <textarea
            className="block-empty-line"
            aria-label="Новый блок"
            placeholder={
              blocks.length
                ? "Продолжи писать или нажми /…"
                : "Начни писать или нажми / для выбора блока…"
            }
            rows={1}
            value=""
            disabled={disabled || blocks.length >= 1000}
            onKeyDown={(event) => {
              if (event.key === "/") {
                event.preventDefault();
                openMenu(blocks.length);
              }
              if (
                event.key === "Enter" &&
                !event.nativeEvent.isComposing &&
                !disabled &&
                blocks.length < 1000
              ) {
                event.preventDefault();
                const block = newBlock("text");
                onChange([...blocks, block]);
                focus(block.id);
              }
            }}
            onChange={(event) => {
              if (event.target.value) {
                const block = newBlock("text", undefined, event.target.value);
                onChange([...blocks, block]);
                focus(block.id);
              }
            }}
          />
          {picker(blocks.length)}
          {blocks.length >= 1000 && (
            <p className="muted">Достигнут лимит: 1000 блоков.</p>
          )}
        </div>
      )}
      {undo && !readonly && (
        <div className="note-undo" role="status">
          <span>{undo.removed ? "Блок удалён" : "Блок перемещён"}</span>
          <button type="button" className="text-action" disabled={disabled || (undo.removed && blocks.length >= 1000)} onClick={undoStructure}>Отменить действие с блоком</button>
        </div>
      )}
    </div>
  );
}
