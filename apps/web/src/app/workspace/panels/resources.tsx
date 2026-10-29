"use client";

import { ReviewNotificationButton } from "./ai-reviews";

import { useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { csrfToken, requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  Pager,
  QueryState,
  useAction,
} from "@/shared/ui";

export type Material = {
  id: string;
  title: string;
  kind: "file" | "link";
  filename: string | null;
  size_bytes: number | null;
  url: string | null;
  status: "uploading" | "pending" | "processing" | "ready" | "failed";
  version: number;
  error_code: string | null;
  trashed_at: string | null;
};
type List<T> = { items: T[]; offset: number; limit: number };
const statusLabels = {
  uploading: "Загрузка не завершена",
  pending: "В очереди",
  processing: "Обработка",
  ready: "Готово",
  failed: "Ошибка обработки",
};
const mimeTypes: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  txt: "text/plain",
  md: "text/markdown",
};
export const formatBytes = (value: number) =>
  value === 0
    ? "0 Б"
    : value < 1024 * 1024
      ? `${Math.max(1, Math.round(value / 1024))} КБ`
      : `${(value / 1024 / 1024).toFixed(1)} МБ`;

export function MaterialsPanel() {
  const [offset, setOffset] = useState(0);
  const [trashed, setTrashed] = useState(false);
  const [creating, setCreating] = useState<"file" | "link" | null>(null);
  const [trash, setTrash] = useState<Material | null>(null);
  const [editing, setEditing] = useState<Material | null>(null);
  const client = useQueryClient();
  const action = useAction();
  const list = useQuery({
    queryKey: ["materials", trashed, offset],
    queryFn: ({ signal }) =>
      requestJson<List<Material>>(
        `/api/v1/materials?trashed=${trashed}&limit=50&offset=${offset}`,
        { signal },
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some((item) =>
        ["pending", "processing"].includes(item.status),
      )
        ? 4000
        : false,
  });
  const storage = useQuery({
    queryKey: ["material-storage"],
    queryFn: ({ signal }) =>
      requestJson<{ used_bytes: number; limit_bytes: number }>(
        "/api/v1/materials/storage",
        { signal },
      ),
  });
  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["materials"] }),
      client.invalidateQueries({ queryKey: ["material-storage"] }),
    ]);
  }
  function lifecycle(item: Material, operation: "trash" | "restore" | "retry") {
    return action.run(
      async () => {
        await writeJson(`/api/v1/materials/${item.id}/${operation}`, "POST", {
          expected_version: item.version,
        });
        setTrash(null);
        await refresh();
      },
      operation === "trash"
        ? "Материал в корзине"
        : operation === "restore"
          ? "Материал восстановлен"
          : "Обработка запущена",
    );
  }
  return (
    <div className="feature-page">
      <div className="page-heading">
        <div>
          <span className="greeting">ТВОЯ БИБЛИОТЕКА</span>
          <h1>Материалы</h1>
          <p className="heading-subtitle">
            Файлы и ссылки, к которым хочется вернуться.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="secondary-button"
            onClick={() => setCreating("link")}
          >
            + Ссылка
          </button>
          <button
            className="primary-button"
            onClick={() => setCreating("file")}
          >
            Загрузить файл
          </button>
        </div>
      </div>
      <div className="panel">
        <div className="panel-toolbar">
          <div className="segmented-control">
            <button
              className={!trashed ? "selected" : ""}
              onClick={() => {
                setTrashed(false);
                setOffset(0);
              }}
            >
              Библиотека
            </button>
            <button
              className={trashed ? "selected" : ""}
              onClick={() => {
                setTrashed(true);
                setOffset(0);
              }}
            >
              Корзина
            </button>
          </div>
          {storage.data && (
            <span className="muted storage-meter">
              {formatBytes(storage.data.used_bytes)} /{" "}
              {formatBytes(storage.data.limit_bytes)}
              <progress
                aria-label="Использованное хранилище"
                value={storage.data.used_bytes}
                max={storage.data.limit_bytes}
              />
            </span>
          )}
        </div>
        <QueryState
          pending={list.isPending}
          error={list.error}
          retry={() => void list.refetch()}
        />
        {!list.isPending && !list.isError && !list.data?.items.length && (
          <EmptyState
            title={trashed ? "Корзина пуста" : "Собери свою библиотеку"}
            icon="▱"
          >
            <p>
              {trashed
                ? "Удалённые материалы можно восстановить в течение 30 дней."
                : "Добавь конспект, презентацию или полезную ссылку. Файлы доступны только тебе."}
            </p>
            {!trashed && (
              <button
                className="primary-button"
                onClick={() => setCreating("file")}
              >
                Загрузить первый файл
              </button>
            )}
          </EmptyState>
        )}
        <div className="resource-list">
          {list.data?.items.map((item) => (
            <article className="resource-row" key={item.id}>
              <span
                className={`file-icon ${item.kind === "link" ? "link-icon" : ""}`}
                aria-hidden="true"
              >
                {item.kind === "link"
                  ? "↗"
                  : item.filename?.split(".").at(-1)?.toUpperCase()}
              </span>
              <div className="resource-copy">
                <h2>{item.title}</h2>
                <p>
                  {item.kind === "link"
                    ? item.url
                    : `${item.filename} · ${formatBytes(item.size_bytes ?? 0)}`}
                  <span className={`status-pill status-${item.status}`}>
                    {statusLabels[item.status]}
                  </span>
                </p>
                {item.error_code && (
                  <small className="muted">
                    {item.error_code === "no_extractable_text"
                      ? "Текст не найден. Оригинал доступен для скачивания."
                      : `Код обработки: ${item.error_code}`}
                  </small>
                )}
              </div>
              <div className="row-actions">
                {trashed ? (
                  <button
                    className="secondary-button"
                    disabled={action.busy}
                    onClick={() => void lifecycle(item, "restore")}
                  >
                    Восстановить
                  </button>
                ) : (
                  <>
                    {item.kind === "link" && item.url ? (
                      <a
                        className="secondary-button"
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Открыть ↗
                      </a>
                    ) : (
                      item.status !== "uploading" && (
                        <a
                          className="secondary-button"
                          href={`/api/v1/materials/${item.id}/content`}
                          download
                        >
                          Скачать
                        </a>
                      )
                    )}
                    {item.status === "failed" && (
                      <button
                        className="secondary-button"
                        disabled={action.busy}
                        onClick={() => void lifecycle(item, "retry")}
                      >
                        Повторить
                      </button>
                    )}
                    <button
                      className="icon-button"
                      aria-label={`Изменить ${item.title}`}
                      onClick={() => setEditing(item)}
                    >
                      ✎
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`В корзину: ${item.title}`}
                      onClick={() => setTrash(item)}
                    >
                      ×
                    </button>
                  </>
                )}
              </div>
            </article>
          ))}
        </div>
        {list.data && (offset > 0 || list.data.items.length === 50) && (
          <Pager
            count={list.data.items.length}
            offset={offset}
            onChange={setOffset}
          />
        )}
      </div>
      <ActionFeedback {...action} />
      {creating && (
        <MaterialCreate
          kind={creating}
          onClose={() => setCreating(null)}
          onSaved={refresh}
        />
      )}
      {trash && (
        <Modal title="Удаление материала" onClose={() => setTrash(null)}>
          <h2>Убрать материал в корзину?</h2>
          <p>
            «{trash.title}» можно восстановить в течение 30 дней. Связанные
            страницы сохранятся.
          </p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button className="secondary-button" onClick={() => setTrash(null)}>
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={action.busy}
              onClick={() => void lifecycle(trash, "trash")}
            >
              В корзину
            </button>
          </div>
        </Modal>
      )}
      {editing && (
        <Modal title="Изменить материал" onClose={() => setEditing(null)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const fields = new FormData(event.currentTarget);
              void action.run(async () => {
                await writeJson(`/api/v1/materials/${editing.id}`, "PATCH", {
                  expected_version: editing.version,
                  title: fields.get("title"),
                  ...(editing.kind === "link"
                    ? { url: fields.get("url") }
                    : {}),
                });
                await refresh();
                setEditing(null);
              });
            }}
          >
            <h2>Изменить материал</h2>
            <label htmlFor="material-edit-title">Название</label>
            <input
              id="material-edit-title"
              name="title"
              defaultValue={editing.title}
              required
              maxLength={200}
            />
            {editing.kind === "link" && (
              <>
                <label htmlFor="material-edit-url">Адрес</label>
                <input
                  id="material-edit-url"
                  name="url"
                  type="url"
                  defaultValue={editing.url ?? ""}
                  maxLength={2048}
                  required
                />
              </>
            )}
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button className="primary-button" disabled={action.busy}>
                Сохранить
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function MaterialCreate({
  kind,
  onClose,
  onSaved,
}: {
  kind: "file" | "link";
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const action = useAction();
  const reservation = useRef<{ key: string; id: string } | null>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await action.run(async () => {
      if (kind === "link")
        await writeJson("/api/v1/materials/links", "POST", {
          title: data.get("title"),
          url: data.get("url"),
        });
      else {
        const file = data.get("file") as File;
        const extension = file.name.split(".").at(-1)?.toLowerCase() ?? "";
        if (!mimeTypes[extension])
          throw new Error("Поддерживаются PDF, DOCX, PPTX, TXT и MD.");
        if (!file.size || file.size > 25 * 1024 * 1024)
          throw new Error("Выберите непустой файл размером до 25 МБ.");
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (reservation.current?.key !== key) {
          const item = await writeJson<Material>(
            "/api/v1/materials/uploads",
            "POST",
            {
              filename: file.name,
              size_bytes: file.size,
              ...(data.get("title") ? { title: data.get("title") } : {}),
            },
          );
          reservation.current = { key, id: item.id };
        }
        const current = await requestJson<Material>(
          `/api/v1/materials/${reservation.current.id}`,
        );
        if (current.status !== "uploading") {
          await onSaved();
          onClose();
          return;
        }
        const token = await csrfToken();
        await requestJson(
          `/api/v1/materials/${reservation.current.id}/content`,
          {
            method: "PUT",
            headers: {
              "Content-Type": mimeTypes[extension],
              "X-CSRF-Token": token,
            },
            body: file,
          },
        );
      }
      await onSaved();
      onClose();
    }, "Материал добавлен");
  }
  return (
    <Modal
      title={kind === "file" ? "Загрузить файл" : "Сохранить ссылку"}
      onClose={() => {
        if (!action.busy) onClose();
      }}
    >
      <form onSubmit={(event) => void submit(event)}>
        <span className="greeting">БИБЛИОТЕКА</span>
        <h2>{kind === "file" ? "Загрузить материал" : "Сохранить ссылку"}</h2>
        <p className="muted">
          {kind === "file"
            ? "PDF, DOCX, PPTX, TXT или MD · до 25 МБ. Текст будет подготовлен для поиска."
            : "Страница по ссылке не скачивается. В поиске будет доступно её название."}
        </p>
        {kind === "file" && (
          <label className="upload-zone">
            Выбрать файл
            <input
              type="file"
              name="file"
              required
              accept=".pdf,.docx,.pptx,.txt,.md"
              disabled={action.busy}
            />
          </label>
        )}
        <label htmlFor="material-title">
          Название{kind === "file" ? " (необязательно)" : ""}
        </label>
        <input
          id="material-title"
          name="title"
          maxLength={200}
          required={kind === "link"}
          disabled={action.busy}
        />
        {kind === "link" && (
          <>
            <label htmlFor="material-url">Адрес ссылки</label>
            <input
              id="material-url"
              name="url"
              type="url"
              maxLength={2048}
              placeholder="https://"
              required
              disabled={action.busy}
            />
          </>
        )}
        <ActionFeedback {...action} />
        <div className="modal-actions">
          <button
            type="button"
            className="secondary-button"
            disabled={action.busy}
            onClick={onClose}
          >
            Отмена
          </button>
          <button className="primary-button" disabled={action.busy}>
            {action.busy
              ? "Загружаем…"
              : kind === "file"
                ? "Загрузить"
                : "Сохранить ссылку"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

type SearchHit = {
  id: string;
  source: "page" | "material";
  title: string;
  snippet: string;
  kind: string | null;
};
export function SearchPanel({
  onOpenPage,
  onMaterials,
}: {
  onOpenPage: (id: string) => void;
  onMaterials: () => void;
}) {
  const [search, setSearch] = useState({ text: "", source: "", offset: 0 });
  const [materialId, setMaterialId] = useState<string | null>(null);
  const material = useQuery({
    queryKey: ["search-material", materialId],
    queryFn: ({ signal }) =>
      requestJson<Material>(`/api/v1/materials/${materialId}`, { signal }),
    enabled: !!materialId,
  });
  const result = useQuery({
    queryKey: ["search", search],
    queryFn: ({ signal }) =>
      requestJson<List<SearchHit>>(
        `/api/v1/search?q=${encodeURIComponent(search.text)}${search.source ? `&source=${search.source}` : ""}&limit=20&offset=${search.offset}`,
        { signal },
      ),
    enabled: !!search.text,
  });
  return (
    <div className="feature-page search-page">
      <div className="page-heading">
        <div>
          <span className="greeting">НАЙДИ НУЖНОЕ</span>
          <h1>Поиск</h1>
          <p className="heading-subtitle">
            По страницам и тексту твоих материалов.
          </p>
        </div>
      </div>
      <form
        className="search-bar panel"
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          setSearch({
            text: String(data.get("q")).trim(),
            source: String(data.get("source")),
            offset: 0,
          });
        }}
      >
        <span aria-hidden="true">⌕</span>
        <input
          name="q"
          type="search"
          aria-label="Поисковый запрос"
          placeholder="Что хочешь найти?"
          maxLength={200}
          required
          autoFocus
        />
        <select name="source" aria-label="Где искать">
          <option value="">Везде</option>
          <option value="page">Страницы</option>
          <option value="material">Материалы</option>
        </select>
        <button className="primary-button">Найти</button>
      </form>
      {!search.text ? (
        <EmptyState title="Всё ближе, чем кажется" icon="⌕">
          <p>
            Ищи по названию, содержимому заметок или извлечённому тексту файлов.
          </p>
        </EmptyState>
      ) : (
        <>
          <QueryState
            pending={result.isPending}
            error={result.error}
            retry={() => void result.refetch()}
          />
          {result.data && !result.data.items.length && (
            <EmptyState title="Ничего не найдено">
              <p>Попробуй другие слова или измени источник поиска.</p>
            </EmptyState>
          )}
          <div className="search-results">
            {result.data?.items.map((hit) => (
              <button
                className="search-result panel"
                key={`${hit.source}:${hit.id}`}
                onClick={() =>
                  hit.source === "page"
                    ? onOpenPage(hit.id)
                    : setMaterialId(hit.id)
                }
              >
                <small>
                  {hit.source === "page"
                    ? "СТРАНИЦА"
                    : hit.kind === "link"
                      ? "ССЫЛКА"
                      : "МАТЕРИАЛ"}
                </small>
                <h2>{hit.title}</h2>
                <p>{hit.snippet}</p>
                <span>
                  Открыть {hit.source === "page" ? "страницу" : "материал"} →
                </span>
              </button>
            ))}
          </div>
          {result.data && (search.offset || result.data.items.length === 20) ? (
            <Pager
              size={20}
              offset={search.offset}
              count={result.data.items.length}
              onChange={(offset) =>
                setSearch((value) => ({ ...value, offset }))
              }
            />
          ) : null}
        </>
      )}
      {materialId && (
        <Modal title="Материал из поиска" onClose={() => setMaterialId(null)}>
          <QueryState
            pending={material.isPending}
            error={material.error}
            retry={() => void material.refetch()}
          />
          {material.data && (
            <>
              <span className="greeting">МАТЕРИАЛ</span>
              <h2>{material.data.title}</h2>
              <p className="muted">
                {material.data.kind === "file"
                  ? material.data.filename
                  : material.data.url}
              </p>
              <div className="modal-actions">
                <button className="secondary-button" onClick={onMaterials}>
                  Вся библиотека
                </button>
                {material.data.kind === "link" && material.data.url ? (
                  <a
                    className="primary-button"
                    href={material.data.url}
                    rel="noopener noreferrer"
                    target="_blank"
                  >
                    Открыть ссылку ↗
                  </a>
                ) : (
                  material.data.status !== "uploading" && (
                    <a
                      className="primary-button"
                      href={`/api/v1/materials/${material.data.id}/content`}
                      download
                    >
                      Скачать
                    </a>
                  )
                )}
              </div>
            </>
          )}
        </Modal>
      )}
    </div>
  );
}

type Notification = {
  id: string;
  title: string;
  starts_at: string | null;
  kind?: "reminder" | "ai_review";
  review_id?: string | null;
  created_at: string;
  read_at: string | null;
};
type Reminder = {
  id: string;
  minutes_before: number;
  due_at: string;
  status: string;
  version: number;
};
export function NotificationsPanel({ timeZone }: { timeZone: string }) {
  const [unread, setUnread] = useState(false);
  const [offset, setOffset] = useState(0);
  const client = useQueryClient();
  const action = useAction();
  const items = useQuery({
    queryKey: ["notifications", unread, offset],
    queryFn: ({ signal }) =>
      requestJson<List<Notification>>(
        `/api/v1/notifications?unread_only=${unread}&limit=50&offset=${offset}`,
        { signal },
      ),
  });
  const reminders = useQuery({
    queryKey: ["reminders"],
    queryFn: ({ signal }) =>
      requestJson<List<Reminder>>("/api/v1/reminders?limit=50", { signal }),
  });
  const date = (value: string) =>
    new Intl.DateTimeFormat("ru", {
      timeZone,
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  return (
    <div className="feature-page">
      <div className="page-heading">
        <div>
          <span className="greeting">НИЧЕГО НЕ УПУСТИ</span>
          <h1>Уведомления</h1>
          <p className="heading-subtitle">Напоминания и обзоры по твоим данным.</p>
        </div>
      </div>
      <div className="notification-layout">
        <section className="panel">
          <div className="panel-toolbar">
            <strong>Входящие</strong>
            <label className="inline-check">
              <input
                type="checkbox"
                checked={unread}
                onChange={(event) => {
                  setUnread(event.target.checked);
                  setOffset(0);
                }}
              />
              Только непрочитанные
            </label>
          </div>
          <QueryState
            pending={items.isPending}
            error={items.error}
            retry={() => void items.refetch()}
          />
          {items.data && !items.data.items.length && (
            <EmptyState title="Всё спокойно" icon="♧">
              <p>
                Новые напоминания и включённые обзоры AI появятся здесь.
                Напоминания настраиваются в событии, обзоры — в настройках AI.
              </p>
            </EmptyState>
          )}
          {items.data?.items.map((item) => (
            <article
              className={`inbox-row ${!item.read_at ? "unread" : ""}`}
              key={item.id}
            >
              <span className="inbox-dot" />
              <div>
                <h2>{item.title}</h2>
                <p>{item.starts_at ? `Начало события: ${date(item.starts_at)}` : "Обзор по твоим данным"}</p>
                {item.kind === "ai_review" && item.review_id && <ReviewNotificationButton id={item.review_id} timeZone={timeZone} />}
                <small>Получено {date(item.created_at)}</small>
              </div>
              {!item.read_at && (
                <button
                  className="text-action"
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      await writeJson(
                        `/api/v1/notifications/${item.id}/read`,
                        "POST",
                      );
                      await client.invalidateQueries({
                        queryKey: ["notifications"],
                      });
                    }, "Отмечено как прочитанное")
                  }
                >
                  Прочитано
                </button>
              )}
            </article>
          ))}
          {items.data && (offset || items.data.items.length === 50) ? (
            <Pager
              offset={offset}
              count={items.data.items.length}
              onChange={setOffset}
            />
          ) : null}
        </section>
        <aside className="panel reminder-list">
          <h2>Ближайшие напоминания</h2>
          <QueryState
            pending={reminders.isPending}
            error={reminders.error}
            retry={() => void reminders.refetch()}
          />
          {reminders.data?.items
            .filter((item) => item.status === "pending")
            .map((item) => (
              <div className="reminder-row" key={item.id}>
                <strong>{date(item.due_at)}</strong>
                <span>За {item.minutes_before} мин. до события</span>
                <button
                  className="text-action danger-text"
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      await writeJson(
                        `/api/v1/reminders/${item.id}/cancel`,
                        "POST",
                        { expected_version: item.version },
                      );
                      await client.invalidateQueries({
                        queryKey: ["reminders"],
                      });
                    }, "Напоминание отменено")
                  }
                >
                  Отменить
                </button>
              </div>
            ))}
          {reminders.data &&
            !reminders.data.items.some((item) => item.status === "pending") && (
              <p className="muted">
                В последних 50 записях нет ожидающих напоминаний.
              </p>
            )}
        </aside>
      </div>
      <ActionFeedback {...action} />
    </div>
  );
}
