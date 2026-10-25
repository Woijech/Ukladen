"use client";

import { useRef, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  Pager,
  QueryState,
  useAction,
} from "@/shared/ui";
import { dateKey, shiftDate, startOfWeek } from "../calendar-time";
import type { PageSummary } from "./notes";

type List<T> = { items: T[]; limit: number; offset: number };
type Database = {
  id: string;
  name: string;
  color: string | null;
  version: number;
  schema_version: number;
  trashed_at: string | null;
};
type Kind =
  | "text"
  | "number"
  | "checkbox"
  | "select"
  | "multi_select"
  | "url"
  | "date";
type Property = {
  id: string;
  name: string;
  kind: Kind;
  options: { id: string; name: string }[];
  version: number;
  trashed_at: string | null;
};
type DateValue = {
  kind: "date" | "datetime";
  start: string;
  end: string | null;
};
type Value = string | number | boolean | string[] | DateValue | null;
type RecordItem = {
  record: {
    id: string;
    version: number;
    values: Record<string, Value>;
    trashed_at: string | null;
  };
  page: PageSummary;
  schema_version: number;
};
type ViewQuery = {
  version: 1;
  columns: string[] | null;
  filters: { property_id: string; operator: string; value?: Value }[];
  sorts: { property_id: string; direction: "asc" | "desc" }[];
};
type View = {
  query?: ViewQuery;
  calendar_layout?: "day" | "week" | "month" | null;
  id: string;
  name: string;
  layout: "table" | "calendar";
  date_property_id: string | null;
  version: number;
};
type Table = List<RecordItem> & {
  properties: Property[];
  schema_version: number;
  total: number;
};
type DateEntry = {
  id: string;
  title: string;
  page_id: string;
  date: DateValue;
  record_id: string;
};
const kinds: { value: Kind; label: string }[] = [
  { value: "text", label: "Текст" },
  { value: "number", label: "Число" },
  { value: "checkbox", label: "Чекбокс" },
  { value: "select", label: "Выбор" },
  { value: "multi_select", label: "Множественный выбор" },
  { value: "url", label: "Ссылка" },
  { value: "date", label: "Дата" },
];

function displayValue(
  value: Value | undefined,
  property: Property,
  timeZone: string,
) {
  if (value === null || value === undefined) return "—";
  if (property.kind === "checkbox") return value ? "✓" : "○";
  if (Array.isArray(value))
    return value
      .map(
        (id) => property.options.find((option) => option.id === id)?.name ?? id,
      )
      .join(", ");
  if (typeof value === "object") {
    if (value.kind === "date")
      return `${value.start}${value.end ? ` — ${value.end}` : ""}`;
    const format = (date: string) =>
      new Intl.DateTimeFormat("ru", {
        timeZone,
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date(date));
    return `${format(value.start)}${value.end ? ` — ${format(value.end)}` : ""}`;
  }
  if (property.kind === "select")
    return (
      property.options.find((option) => option.id === value)?.name ??
      String(value)
    );
  return String(value);
}

export function DatabasesPanel({
  timeZone,
  onOpenPage,
}: {
  timeZone: string;
  onOpenPage: (id: string) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [trashed, setTrashed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const action = useAction();
  const client = useQueryClient();
  const databases = useQuery({
    queryKey: ["databases", trashed, offset],
    queryFn: ({ signal }) =>
      requestJson<List<Database>>(
        `/api/v1/workspace/databases?trashed=${trashed}&limit=50&offset=${offset}`,
        { signal },
      ),
  });
  if (selected)
    return (
      <DatabaseDetail
        id={selected}
        timeZone={timeZone}
        onBack={() => setSelected(null)}
        onOpenPage={onOpenPage}
      />
    );
  return (
    <div className="feature-page">
      <div className="page-heading">
        <div>
          <span className="greeting">ПОРЯДОК ПО ТВОИМ ПРАВИЛАМ</span>
          <h1>Базы данных</h1>
          <p className="heading-subtitle">
            Страницы с полями, таблицами и календарными видами.
          </p>
        </div>
        <button className="primary-button" onClick={() => setCreating(true)}>
          + Новая база
        </button>
      </div>
      <div className="panel-toolbar standalone-toolbar">
        <div className="segmented-control">
          <button
            className={!trashed ? "selected" : ""}
            onClick={() => {
              setTrashed(false);
              setOffset(0);
            }}
          >
            Мои базы
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
      </div>
      <QueryState
        pending={databases.isPending}
        error={databases.error}
        retry={() => void databases.refetch()}
      />
      {databases.data && !databases.data.items.length && (
        <div className="panel">
          <EmptyState
            title={trashed ? "Корзина пуста" : "Своя система — с чистого листа"}
            icon="▦"
          >
            <p>
              Создай базу для курсов, тренировок или идей. Поля и порядок
              выбираешь ты.
            </p>
            {!trashed && (
              <button
                className="primary-button"
                onClick={() => setCreating(true)}
              >
                Создать базу
              </button>
            )}
          </EmptyState>
        </div>
      )}
      <div className="database-cards">
        {databases.data?.items.map((database) => (
          <button
            className="database-card panel"
            key={database.id}
            onClick={() => setSelected(database.id)}
          >
            <span
              className="database-symbol"
              style={{ color: database.color ?? undefined }}
            >
              ▦
            </span>
            <h2>{database.name}</h2>
            <span>
              {database.trashed_at
                ? "В корзине · восстановить"
                : "Таблицы, страницы и даты"}{" "}
              <span aria-hidden="true">→</span>
            </span>
          </button>
        ))}
      </div>
      {databases.data && (offset || databases.data.items.length === 50) ? (
        <Pager
          count={databases.data.items.length}
          offset={offset}
          onChange={setOffset}
        />
      ) : null}
      {creating && (
        <Modal title="Новая база" onClose={() => setCreating(false)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const name = new FormData(event.currentTarget).get("name");
              void action.run(async () => {
                const database = await writeJson<Database>(
                  "/api/v1/workspace/databases",
                  "POST",
                  { name },
                );
                await client.invalidateQueries({ queryKey: ["databases"] });
                setCreating(false);
                setSelected(database.id);
              });
            }}
          >
            <h2>Новая база данных</h2>
            <label htmlFor="database-name">Название базы</label>
            <input
              id="database-name"
              name="name"
              required
              maxLength={100}
              autoFocus
              placeholder="Например, учебные проекты"
            />
            <ActionFeedback {...action} />
            <div className="modal-actions">
              <button className="primary-button" disabled={action.busy}>
                Создать
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

function DatabaseDetail({
  id,
  timeZone,
  onBack,
  onOpenPage,
}: {
  id: string;
  timeZone: string;
  onBack: () => void;
  onOpenPage: (id: string) => void;
}) {
  const base = `/api/v1/workspace/databases/${id}`;
  const client = useQueryClient();
  const action = useAction();
  const [viewId, setViewId] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [trashRecords, setTrashRecords] = useState(false);
  const [dialog, setDialog] = useState<
    | "property"
    | "schema"
    | "record"
    | "view"
    | "edit-view"
    | "trash"
    | "rename"
    | null
  >(null);
  const [editing, setEditing] = useState<RecordItem | null>(null);
  const [week, setWeek] = useState(() => dateKey(new Date(), timeZone));
  const database = useQuery({
    queryKey: ["database", id],
    queryFn: ({ signal }) => requestJson<Database>(base, { signal }),
  });
  const active = !!database.data && !database.data.trashed_at;
  const properties = useQuery({
    queryKey: ["properties", id],
    queryFn: ({ signal }) =>
      requestJson<{ items: Property[]; schema_version: number }>(
        `${base}/properties`,
        { signal },
      ),
    enabled: active,
  });
  const views = useQuery({
    queryKey: ["database-views", id],
    queryFn: ({ signal }) =>
      requestJson<List<View>>(`${base}/views?limit=200`, { signal }),
    enabled: active,
  });
  const selectedView = views.data?.items.find((item) => item.id === viewId);
  const monthView = selectedView?.calendar_layout === "month";
  const dayView = selectedView?.calendar_layout === "day";
  const monthStart = `${week.slice(0, 7)}-01`;
  const rangeStart = dayView
    ? week
    : startOfWeek(monthView ? monthStart : week);
  const nextMonth = (value: string, delta: number) => {
    const [year, month] = value.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1 + delta, 1))
      .toISOString()
      .slice(0, 10);
  };
  const dayCount = dayView
    ? 1
    : monthView
      ? Math.ceil(
          (Date.parse(`${nextMonth(monthStart, 1)}T00:00:00Z`) -
            Date.parse(`${rangeStart}T00:00:00Z`)) /
            86400000 /
            7,
        ) * 7
      : 7;
  const rangeEnd = shiftDate(rangeStart, dayCount - 1);
  const records = useQuery({
    queryKey: ["records", id, viewId, trashRecords, offset],
    queryFn: ({ signal }) =>
      requestJson<Table>(
        selectedView?.layout === "table" && !trashRecords
          ? `${base}/views/${viewId}/records?limit=50&offset=${offset}`
          : `${base}/records?trashed=${trashRecords}&limit=50&offset=${offset}`,
        { signal },
      ),
    enabled:
      active &&
      views.isSuccess &&
      (!viewId || !!selectedView) &&
      selectedView?.layout !== "calendar",
  });
  const entries = useQuery({
    queryKey: ["database-dates", id, viewId, rangeStart, rangeEnd],
    queryFn: ({ signal }) =>
      requestJson<{ entries: DateEntry[] }>(
        `${base}/views/${viewId}/entries?date_from=${rangeStart}&date_to=${rangeEnd}`,
        { signal },
      ),
    enabled: active && selectedView?.layout === "calendar",
  });
  const definitions = records.data?.properties ?? properties.data?.items ?? [];
  const schema =
    properties.data?.schema_version ?? database.data?.schema_version ?? 1;
  async function refresh() {
    await Promise.all(
      [
        "database",
        "databases",
        "properties",
        "records",
        "database-views",
        "database-dates",
      ].map((key) =>
        client.invalidateQueries({
          queryKey: key === "databases" ? [key] : [key, id],
        }),
      ),
    );
  }
  function recordLifecycle(item: RecordItem, operation: "trash" | "restore") {
    return action.run(
      async () => {
        await writeJson(
          `${base}/records/${item.record.id}/${operation}`,
          "POST",
          { expected_version: item.record.version },
        );
        await refresh();
      },
      operation === "trash"
        ? "Запись в корзине. Страница сохранена."
        : "Запись восстановлена",
    );
  }
  return (
    <div className="feature-page">
      <button className="text-action back-link" onClick={onBack}>
        ← Все базы
      </button>
      <div className="page-heading">
        <div>
          <span className="greeting">ЛИЧНАЯ БАЗА</span>
          <h1>{database.data?.name ?? "База данных"}</h1>
          <p className="heading-subtitle">
            Общее содержимое страниц. Отдельные поля записей.
          </p>
        </div>
        {active && (
          <div className="heading-actions">
            <button
              className="secondary-button"
              onClick={() => setDialog("rename")}
            >
              Настроить
            </button>
            <button
              className="primary-button"
              onClick={() => setDialog("record")}
              disabled={!properties.data}
            >
              + Запись
            </button>
          </div>
        )}
      </div>
      <QueryState
        pending={database.isPending}
        error={database.error}
        retry={() => void database.refetch()}
      />
      {database.data?.trashed_at && (
        <div className="panel">
          <EmptyState title="База в корзине">
            <p>Её поля, записи и страницы сохранены.</p>
            <button
              className="primary-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await writeJson(`${base}/restore`, "POST", {
                    expected_version: database.data!.version,
                  });
                  await refresh();
                }, "База восстановлена")
              }
            >
              Восстановить базу
            </button>
          </EmptyState>
        </div>
      )}
      {active && (
        <>
          <QueryState
            pending={properties.isPending || views.isPending}
            error={properties.error || views.error}
            retry={() => {
              void properties.refetch();
              void views.refetch();
            }}
          />
          <div className="panel">
            <div className="database-toolbar">
              <div className="view-tabs" aria-label="Виды базы">
                <button
                  className={!viewId ? "selected" : ""}
                  onClick={() => {
                    setViewId(null);
                    setOffset(0);
                  }}
                >
                  ▦ Все записи
                </button>
                {views.data?.items.map((view) => (
                  <button
                    className={viewId === view.id ? "selected" : ""}
                    key={view.id}
                    onClick={() => {
                      setViewId(view.id);
                      setTrashRecords(false);
                      setOffset(0);
                    }}
                  >
                    {view.layout === "calendar" ? "▦" : "☷"} {view.name}
                  </button>
                ))}
                <button
                  onClick={() => setDialog("view")}
                  disabled={!properties.data}
                >
                  + Вид
                </button>
              </div>
              <div className="row-actions">
                <button
                  className="text-action"
                  onClick={() => setDialog("schema")}
                >
                  Поля
                </button>
                <button
                  className="text-action"
                  onClick={() => setDialog("property")}
                  disabled={!properties.data}
                >
                  + Поле
                </button>
              </div>
            </div>
            {selectedView?.layout === "calendar" ? (
              <>
                <div className="panel-toolbar">
                  <button
                    className="secondary-button"
                    aria-label="Предыдущая неделя базы"
                    onClick={() =>
                      setWeek((value) =>
                        monthView
                          ? nextMonth(value, -1)
                          : shiftDate(value, dayView ? -1 : -7),
                      )
                    }
                  >
                    ←
                  </button>
                  <span>
                    {rangeStart} — {rangeEnd} · даты не блокируют время
                  </span>
                  <button
                    className="secondary-button"
                    aria-label="Следующая неделя базы"
                    onClick={() =>
                      setWeek((value) =>
                        monthView
                          ? nextMonth(value, 1)
                          : shiftDate(value, dayView ? 1 : 7),
                      )
                    }
                  >
                    →
                  </button>
                </div>
                <QueryState
                  pending={entries.isPending}
                  error={entries.error}
                  retry={() => void entries.refetch()}
                />
                <div
                  className={`database-calendar ${monthView ? "month-record-calendar" : dayView ? "single-record-calendar" : ""}`}
                >
                  {Array.from({ length: dayCount }, (_, index) =>
                    shiftDate(rangeStart, index),
                  ).map((day) => (
                    <div className="database-calendar-day" key={day}>
                      <h3>
                        {new Intl.DateTimeFormat("ru", {
                          timeZone: "UTC",
                          weekday: "short",
                          day: "numeric",
                        }).format(new Date(`${day}T12:00:00Z`))}
                      </h3>
                      {entries.data?.entries
                        .filter((entry) => {
                          const start =
                            entry.date.kind === "date"
                              ? entry.date.start
                              : dateKey(new Date(entry.date.start), timeZone);
                          const end = entry.date.end
                            ? entry.date.kind === "date"
                              ? entry.date.end
                              : dateKey(
                                  new Date(
                                    Math.max(
                                      Date.parse(entry.date.start),
                                      Date.parse(entry.date.end) - 1,
                                    ),
                                  ),
                                  timeZone,
                                )
                            : start;
                          return start <= day && end >= day;
                        })
                        .map((entry) => (
                          <button
                            className="database-date-entry"
                            key={entry.id}
                            onClick={() => onOpenPage(entry.page_id)}
                          >
                            {entry.title}
                            <small>
                              {entry.date.kind === "date"
                                ? "Дата"
                                : "Время указано"}
                            </small>
                          </button>
                        ))}
                    </div>
                  ))}
                </div>
                {entries.data && !entries.data.entries.length && (
                  <p className="panel-note muted">
                    На этой неделе нет записей с датами.
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="panel-toolbar">
                  <span className="muted">
                    {trashRecords
                      ? "Записи в корзине"
                      : "Название открывает страницу"}
                  </span>
                  <button
                    className="text-action"
                    onClick={() => {
                      setTrashRecords((value) => !value);
                      setOffset(0);
                    }}
                  >
                    {trashRecords ? "Активные записи" : "Корзина записей"}
                  </button>
                </div>
                <QueryState
                  pending={records.isPending}
                  error={records.error}
                  retry={() => void records.refetch()}
                />
                <div className="table-scroll">
                  <table className="records-table">
                    <thead>
                      <tr>
                        <th>Название</th>
                        {definitions.map((property) => (
                          <th key={property.id}>{property.name}</th>
                        ))}
                        <th>
                          <span className="sr-only">Действия</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {records.data?.items.map((item) => (
                        <tr key={item.record.id}>
                          <td>
                            <button
                              className="table-page-link"
                              onClick={() => onOpenPage(item.page.id)}
                            >
                              ▤ {item.page.title}
                            </button>
                            {item.page.trashed_at && (
                              <small>Страница в корзине</small>
                            )}
                          </td>
                          {definitions.map((property) => (
                            <td key={property.id}>
                              {displayValue(
                                item.record.values[property.id],
                                property,
                                timeZone,
                              )}
                            </td>
                          ))}
                          <td>
                            <div className="row-actions">
                              {!item.record.trashed_at && (
                                <button
                                  className="text-action"
                                  disabled={action.busy || !definitions.length}
                                  onClick={() =>
                                    void action.run(async () => {
                                      const full =
                                        await requestJson<RecordItem>(
                                          `${base}/records/${item.record.id}`,
                                        );
                                      setEditing(full);
                                    }, "")
                                  }
                                >
                                  Изменить
                                </button>
                              )}
                              <button
                                className="text-action"
                                disabled={action.busy}
                                onClick={() =>
                                  void recordLifecycle(
                                    item,
                                    item.record.trashed_at
                                      ? "restore"
                                      : "trash",
                                  )
                                }
                              >
                                {item.record.trashed_at
                                  ? "Восстановить"
                                  : "В корзину"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {records.data && !records.data.items.length && (
                  <EmptyState title="Пока ни одной записи">
                    <p>
                      Добавь страницу и заполни её поля. Содержимое страницы
                      будет доступно и в заметках.
                    </p>
                    <button
                      className="primary-button"
                      onClick={() => setDialog("record")}
                    >
                      Добавить запись
                    </button>
                  </EmptyState>
                )}
                {records.data &&
                (offset || records.data.items.length === 50) ? (
                  <Pager
                    offset={offset}
                    count={records.data.items.length}
                    onChange={setOffset}
                  />
                ) : null}
              </>
            )}
          </div>
          {selectedView && (
            <button
              className="text-action configure-view"
              onClick={() => setDialog("edit-view")}
            >
              Настроить вид
            </button>
          )}
          {selectedView && (
            <button
              className="text-action delete-view"
              onClick={() => setDialog("trash")}
            >
              Удалить этот вид
            </button>
          )}
        </>
      )}
      <ActionFeedback {...action} />
      {(dialog === "record" || editing) && (
        <RecordEditor
          base={base}
          properties={properties.data?.items ?? []}
          schema={schema}
          record={editing}
          onClose={() => {
            setEditing(null);
            setDialog(null);
          }}
          onSaved={refresh}
        />
      )}
      {dialog === "schema" && (
        <PropertyManager
          base={base}
          databaseId={id}
          onSaved={refresh}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "property" && (
        <PropertyCreate
          base={base}
          schema={schema}
          onSaved={refresh}
          onClose={() => setDialog(null)}
        />
      )}
      {(dialog === "view" || dialog === "edit-view") && (
        <ViewCreate
          base={base}
          schema={schema}
          properties={properties.data?.items ?? []}
          editing={dialog === "edit-view" ? selectedView : undefined}
          onSaved={refresh}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "trash" && selectedView && (
        <Modal title="Удалить вид" onClose={() => setDialog(null)}>
          <h2>Удалить «{selectedView.name}»?</h2>
          <p>Записи, страницы и их содержимое сохранятся.</p>
          <ActionFeedback {...action} />
          <div className="modal-actions">
            <button
              className="secondary-button"
              onClick={() => setDialog(null)}
            >
              Отмена
            </button>
            <button
              className="danger-button"
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  await writeJson(
                    `${base}/views/${selectedView.id}?expected_version=${selectedView.version}`,
                    "DELETE",
                  );
                  setViewId(null);
                  setDialog(null);
                  await refresh();
                }, "Вид удалён")
              }
            >
              Удалить вид
            </button>
          </div>
        </Modal>
      )}
      {dialog === "rename" && database.data && (
        <DatabaseSettings
          database={database.data}
          base={base}
          onClose={() => setDialog(null)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}

function RecordEditor({
  base,
  properties,
  schema,
  record,
  onClose,
  onSaved,
}: {
  base: string;
  properties: Property[];
  schema: number;
  record: RecordItem | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const action = useAction();
  const touched = useRef(new Set<string>());
  const [pageMode, setPageMode] = useState("new");
  const [pageOffset, setPageOffset] = useState(0);
  const pages = useQuery({
    queryKey: ["record-page-options", pageOffset],
    queryFn: ({ signal }) =>
      requestJson<{ items: PageSummary[] }>(
        `/api/v1/notes/pages?limit=50&offset=${pageOffset}`,
        { signal },
      ),
    enabled: !record && pageMode === "existing",
  });
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await action.run(async () => {
      const values: Record<string, Value> = {};
      for (const property of properties) {
        if (record && !touched.current.has(property.id)) continue;
        const raw = String(data.get(property.id) ?? "");
        if (property.kind === "checkbox")
          values[property.id] = data.get(property.id) === "on";
        else if (property.kind === "multi_select")
          values[property.id] = data.getAll(property.id).map(String);
        else if (property.kind === "number") {
          const number = Number(raw);
          if (
            raw &&
            (!Number.isFinite(number) ||
              Math.abs(number) > Number.MAX_SAFE_INTEGER)
          )
            throw new Error(
              `«${property.name}»: число вне допустимого диапазона.`,
            );
          values[property.id] = raw === "" ? null : number;
        } else if (property.kind === "date") {
          const start = String(data.get(`${property.id}-start`) ?? "");
          values[property.id] = start
            ? {
                kind: data.get(`${property.id}-kind`) as "date" | "datetime",
                start,
                end: String(data.get(`${property.id}-end`) ?? "") || null,
              }
            : null;
        } else values[property.id] = raw === "" ? null : raw;
      }
      if (record && !Object.keys(values).length)
        throw new Error("Сначала измените хотя бы одно поле.");
      if (record)
        await writeJson(`${base}/records/${record.record.id}`, "PATCH", {
          expected_version: record.record.version,
          expected_schema_version: schema,
          values,
        });
      else
        await writeJson(`${base}/records`, "POST", {
          ...(pageMode === "existing"
            ? { page_id: data.get("page_id") }
            : { title: data.get("title") }),
          values,
          expected_schema_version: schema,
        });
      await onSaved();
      onClose();
    });
  }
  return (
    <Modal
      title={record ? "Изменить запись" : "Новая запись"}
      onClose={onClose}
    >
      <form
        onChange={(event) => {
          const target = event.target;
          if (
            target instanceof HTMLInputElement ||
            target instanceof HTMLSelectElement ||
            target instanceof HTMLTextAreaElement
          ) {
            const name = target.name;
            if (name)
              touched.current.add(name.replace(/-(start|end|kind)$/, ""));
          }
        }}
        onSubmit={(event) => void submit(event)}
      >
        <h2>{record ? record.page.title : "Новая запись"}</h2>
        {!record && (
          <>
            <label htmlFor="record-page-mode">Страница записи</label>
            <select
              id="record-page-mode"
              value={pageMode}
              onChange={(event) => setPageMode(event.target.value)}
            >
              <option value="new">Создать новую страницу</option>
              <option value="existing">Использовать существующую</option>
            </select>
            {pageMode === "new" ? (
              <>
                <label htmlFor="record-title">Название страницы</label>
                <input
                  id="record-title"
                  name="title"
                  maxLength={200}
                  required
                  autoFocus
                />
              </>
            ) : (
              <>
                <label htmlFor="record-page">Выбрать страницу</label>
                <select
                  id="record-page"
                  name="page_id"
                  required
                  key={pageOffset}
                >
                  <option value="">Выбрать…</option>
                  {pages.data?.items.map((page) => (
                    <option key={page.id} value={page.id}>
                      {page.title}
                    </option>
                  ))}
                </select>
                <QueryState
                  pending={pages.isPending}
                  error={pages.error}
                  retry={() => void pages.refetch()}
                />
                {pages.data &&
                (pageOffset || pages.data.items.length === 50) ? (
                  <Pager
                    offset={pageOffset}
                    count={pages.data.items.length}
                    onChange={setPageOffset}
                  />
                ) : null}
              </>
            )}
          </>
        )}
        <p className="muted">
          Поля принадлежат этой записи. Даты не резервируют время в календаре.
        </p>
        {properties.map((property) => {
          const value = record?.record.values[property.id];
          return (
            <div className="record-field" key={property.id}>
              <label htmlFor={`field-${property.id}`}>{property.name}</label>
              {property.kind === "checkbox" ? (
                <input
                  id={`field-${property.id}`}
                  name={property.id}
                  type="checkbox"
                  defaultChecked={value === true}
                />
              ) : property.kind === "select" ||
                property.kind === "multi_select" ? (
                <select
                  id={`field-${property.id}`}
                  name={property.id}
                  multiple={property.kind === "multi_select"}
                  defaultValue={
                    property.kind === "multi_select"
                      ? Array.isArray(value)
                        ? value
                        : []
                      : typeof value === "string"
                        ? value
                        : ""
                  }
                >
                  {property.kind === "select" && (
                    <option value="">Не выбрано</option>
                  )}
                  {property.options.map((option) => (
                    <option value={option.id} key={option.id}>
                      {option.name}
                    </option>
                  ))}
                </select>
              ) : property.kind === "date" ? (
                <DateFields
                  property={property}
                  value={
                    value && typeof value === "object" && !Array.isArray(value)
                      ? value
                      : null
                  }
                />
              ) : (
                <input
                  id={`field-${property.id}`}
                  name={property.id}
                  type={
                    property.kind === "number"
                      ? "number"
                      : property.kind === "url"
                        ? "url"
                        : "text"
                  }
                  step={property.kind === "number" ? "any" : undefined}
                  defaultValue={
                    typeof value === "string" || typeof value === "number"
                      ? value
                      : ""
                  }
                  maxLength={property.kind === "url" ? 2048 : 10000}
                />
              )}
            </div>
          );
        })}
        <ActionFeedback {...action} />
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Отмена
          </button>
          <button className="primary-button" disabled={action.busy}>
            {action.busy ? "Сохраняем…" : "Сохранить запись"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function DateFields({
  property,
  value,
}: {
  property: Property;
  value: DateValue | null;
}) {
  const [kind, setKind] = useState(value?.kind ?? "date");
  return (
    <>
      <select
        id={`field-${property.id}`}
        name={`${property.id}-kind`}
        value={kind}
        onChange={(event) => setKind(event.target.value as "date" | "datetime")}
      >
        <option value="date">Дата без времени</option>
        <option value="datetime">Дата и время с UTC-смещением</option>
      </select>
      <div className="form-row" key={kind}>
        <input
          aria-label={`${property.name}: начало`}
          type={kind === "date" ? "date" : "text"}
          name={`${property.id}-start`}
          defaultValue={value?.kind === kind ? value.start : ""}
          placeholder={
            kind === "datetime" ? "2026-10-21T12:00:00+03:00" : undefined
          }
        />
        <input
          aria-label={`${property.name}: конец (необязательно)`}
          type={kind === "date" ? "date" : "text"}
          name={`${property.id}-end`}
          defaultValue={value?.kind === kind ? (value.end ?? "") : ""}
          placeholder={
            kind === "datetime" ? "Конец с UTC-смещением" : undefined
          }
        />
      </div>
      {kind === "datetime" && (
        <small className="muted">
          Укажите ISO-время с Z или явным смещением. Часовой пояс браузера не
          подставляется.
        </small>
      )}
    </>
  );
}

function PropertyCreate({
  base,
  schema,
  onSaved,
  onClose,
  editing,
}: {
  base: string;
  schema: number;
  onSaved: () => Promise<void>;
  onClose: () => void;
  editing?: Property;
}) {
  const [kind, setKind] = useState<Kind>(editing?.kind ?? "text");
  const [options, setOptions] = useState(editing?.options ?? []);
  const action = useAction();
  return (
    <Modal title={editing ? "Изменить поле" : "Новое поле"} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void action.run(async () => {
            await writeJson(
              editing
                ? `${base}/properties/${editing.id}`
                : `${base}/properties`,
              editing ? "PATCH" : "POST",
              {
                name: data.get("name"),
                kind,
                options: ["select", "multi_select"].includes(kind)
                  ? options
                  : [],
                expected_schema_version: schema,
                ...(editing ? { expected_version: editing.version } : {}),
              },
            );
            await onSaved();
            onClose();
          });
        }}
      >
        <h2>{editing ? "Изменить поле" : "Добавить поле"}</h2>
        <label htmlFor="property-name">Название поля</label>
        <input
          id="property-name"
          name="name"
          maxLength={100}
          required
          autoFocus
          defaultValue={editing?.name ?? ""}
        />
        <label htmlFor="property-kind">Тип данных</label>
        <select
          id="property-kind"
          value={kind}
          onChange={(event) => setKind(event.target.value as Kind)}
        >
          {kinds.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        {["select", "multi_select"].includes(kind) && (
          <>
            <p className="field-label">Варианты выбора</p>
            {options.map((option, index) => (
              <div className="option-editor" key={option.id}>
                <input
                  aria-label={`Вариант ${index + 1}`}
                  value={option.name}
                  maxLength={100}
                  required
                  onChange={(event) =>
                    setOptions((items) =>
                      items.map((item) =>
                        item.id === option.id
                          ? { ...item, name: event.target.value }
                          : item,
                      ),
                    )
                  }
                />
                <button
                  className="icon-button"
                  type="button"
                  aria-label={`Удалить вариант ${index + 1}`}
                  onClick={() =>
                    setOptions((items) =>
                      items.filter((item) => item.id !== option.id),
                    )
                  }
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="secondary-button"
              type="button"
              disabled={options.length >= 100}
              onClick={() =>
                setOptions((items) => [
                  ...items,
                  { id: crypto.randomUUID(), name: "" },
                ])
              }
            >
              + Вариант
            </button>
          </>
        )}
        <p className="muted">
          Переименование сохраняет значения. Изменение типа или удаление
          используемого варианта может быть отклонено, чтобы защитить данные.
        </p>
        <ActionFeedback {...action} />
        <div className="modal-actions">
          <button className="primary-button" disabled={action.busy}>
            {editing ? "Сохранить поле" : "Добавить поле"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ViewCreate({
  base,
  schema,
  properties,
  onSaved,
  onClose,
  editing,
}: {
  base: string;
  schema: number;
  properties: Property[];
  onSaved: () => Promise<void>;
  onClose: () => void;
  editing?: View;
}) {
  const [layout, setLayout] = useState(editing?.layout ?? "table");
  const [automatic, setAutomatic] = useState(editing?.query?.columns == null);
  const [columns, setColumns] = useState(
    editing?.query?.columns ?? properties.map((property) => property.id),
  );
  const [filters, setFilters] = useState<ViewQuery["filters"]>(
    editing?.query?.filters ?? [],
  );
  const [sorts, setSorts] = useState<ViewQuery["sorts"]>(
    editing?.query?.sorts ?? [],
  );
  const action = useAction();
  const defaults = (property: Property | undefined): Value =>
    property?.kind === "checkbox"
      ? false
      : property?.kind === "date"
        ? { kind: "date", start: "", end: null }
        : "";
  return (
    <Modal
      title={editing ? "Настроить вид" : "Новый вид"}
      wide
      onClose={onClose}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void action.run(async () => {
            const normalized = filters.map((filter) => {
              const property = properties.find(
                (item) => item.id === filter.property_id,
              );
              if (
                property?.kind === "number" &&
                !["is_empty", "is_not_empty"].includes(filter.operator)
              ) {
                const value = Number(filter.value);
                if (
                  filter.value === "" ||
                  !Number.isFinite(value) ||
                  Math.abs(value) > Number.MAX_SAFE_INTEGER
                )
                  throw new Error("Укажите допустимое число в фильтре.");
                return { ...filter, value };
              }
              return filter;
            });
            const body = {
              name: data.get("name"),
              expected_schema_version: schema,
              query: {
                version: 1,
                columns: automatic ? null : columns,
                filters: normalized,
                sorts,
              },
              ...(layout === "calendar"
                ? {
                    date_property_id: data.get("date"),
                    calendar_layout: data.get("calendar_layout") ?? "week",
                  }
                : {}),
              ...(editing ? { expected_version: editing.version } : { layout }),
            };
            await writeJson(
              editing ? `${base}/views/${editing.id}` : `${base}/views`,
              editing ? "PATCH" : "POST",
              body,
            );
            await onSaved();
            onClose();
          });
        }}
      >
        <h2>{editing ? "Настроить представление" : "Сохранить вид"}</h2>
        <label htmlFor="view-name">Название вида</label>
        <input
          id="view-name"
          name="name"
          required
          maxLength={100}
          autoFocus
          defaultValue={editing?.name ?? ""}
        />
        <div className="form-row">
          <div>
            <label htmlFor="view-layout">Представление</label>
            <select
              id="view-layout"
              value={layout}
              disabled={!!editing}
              onChange={(event) =>
                setLayout(event.target.value as "table" | "calendar")
              }
            >
              <option value="table">Таблица</option>
              <option
                value="calendar"
                disabled={!properties.some((item) => item.kind === "date")}
              >
                Календарь
              </option>
            </select>
          </div>
          {layout === "calendar" && (
            <div>
              <label htmlFor="view-date">Поле даты</label>
              <select
                id="view-date"
                name="date"
                required
                defaultValue={editing?.date_property_id ?? ""}
              >
                <option value="">Выбрать поле…</option>
                {editing?.date_property_id &&
                  !properties.some(
                    (item) => item.id === editing.date_property_id,
                  ) && (
                    <option value={editing.date_property_id}>
                      Недоступное поле
                    </option>
                  )}
                {properties
                  .filter((item) => item.kind === "date")
                  .map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </div>
          )}
        </div>
        {layout === "calendar" && (
          <>
            <label htmlFor="view-calendar-layout">Масштаб календаря</label>
            <select
              id="view-calendar-layout"
              name="calendar_layout"
              defaultValue={editing?.calendar_layout ?? "week"}
            >
              <option value="day">День</option>
              <option value="week">Неделя</option>
              <option value="month">Месяц</option>
            </select>
          </>
        )}
        <h3>Поля таблицы</h3>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={automatic}
            onChange={(event) => setAutomatic(event.target.checked)}
          />
          Показывать все активные поля автоматически
        </label>
        {!automatic && (
          <div className="column-picker">
            {properties.map((property) => (
              <label className="inline-check" key={property.id}>
                <input
                  type="checkbox"
                  checked={columns.includes(property.id)}
                  onChange={(event) =>
                    setColumns((ids) =>
                      event.target.checked
                        ? [...ids, property.id]
                        : ids.filter((id) => id !== property.id),
                    )
                  }
                />
                {property.name}
              </label>
            ))}
            {columns
              .filter((id) => !properties.some((item) => item.id === id))
              .map((id) => (
                <label className="inline-check" key={id}>
                  <input
                    type="checkbox"
                    checked
                    onChange={() =>
                      setColumns((ids) => ids.filter((item) => item !== id))
                    }
                  />
                  Недоступное поле
                </label>
              ))}
          </div>
        )}
        <h3>Фильтры</h3>
        <p className="muted">
          Запись должна соответствовать всем условиям. Даты и занятость объектов
          не изменяются.
        </p>
        {filters.map((filter, index) => {
          const property = properties.find(
            (item) => item.id === filter.property_id,
          );
          return (
            <div className="filter-row" key={index}>
              <select
                aria-label={`Поле фильтра ${index + 1}`}
                value={filter.property_id}
                onChange={(event) =>
                  setFilters((items) =>
                    items.map((item, i) =>
                      i === index
                        ? {
                            property_id: event.target.value,
                            operator: "is_not_empty",
                            value: null,
                          }
                        : item,
                    ),
                  )
                }
              >
                <option value="">Выбрать поле…</option>
                {!property && filter.property_id && (
                  <option value={filter.property_id}>Недоступное поле</option>
                )}
                {properties.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
              <select
                aria-label={`Условие фильтра ${index + 1}`}
                value={filter.operator}
                onChange={(event) =>
                  setFilters((items) =>
                    items.map((item, i) =>
                      i === index
                        ? {
                            ...item,
                            operator: event.target.value,
                            value: ["is_empty", "is_not_empty"].includes(
                              event.target.value,
                            )
                              ? null
                              : defaults(property),
                          }
                        : item,
                    ),
                  )
                }
              >
                {filterOperators(property).map((item) => (
                  <option value={item.value} key={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
              {!["is_empty", "is_not_empty"].includes(filter.operator) &&
                property && (
                  <FilterValue
                    property={property}
                    value={filter.value ?? null}
                    label={`Значение фильтра ${index + 1}`}
                    onChange={(value) =>
                      setFilters((items) =>
                        items.map((item, i) =>
                          i === index ? { ...item, value } : item,
                        ),
                      )
                    }
                  />
                )}
              <button
                type="button"
                className="icon-button"
                aria-label={`Удалить фильтр ${index + 1}`}
                onClick={() =>
                  setFilters((items) => items.filter((_, i) => i !== index))
                }
              >
                ×
              </button>
            </div>
          );
        })}
        <button
          type="button"
          className="secondary-button"
          disabled={filters.length >= 20 || !properties.length}
          onClick={() =>
            setFilters((items) => [
              ...items,
              {
                property_id: properties[0].id,
                operator: "is_not_empty",
                value: null,
              },
            ])
          }
        >
          + Фильтр
        </button>
        <h3>Сортировка</h3>
        {sorts.map((sort, index) => (
          <div className="sort-row" key={index}>
            <select
              aria-label={`Поле сортировки ${index + 1}`}
              value={sort.property_id}
              onChange={(event) =>
                setSorts((items) =>
                  items.map((item, i) =>
                    i === index
                      ? { ...item, property_id: event.target.value }
                      : item,
                  ),
                )
              }
            >
              {!properties.some((item) => item.id === sort.property_id) && (
                <option value={sort.property_id}>Недоступное поле</option>
              )}
              {properties
                .filter((item) => item.kind !== "multi_select")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </select>
            <select
              aria-label={`Порядок сортировки ${index + 1}`}
              value={sort.direction}
              onChange={(event) =>
                setSorts((items) =>
                  items.map((item, i) =>
                    i === index
                      ? {
                          ...item,
                          direction: event.target.value as "asc" | "desc",
                        }
                      : item,
                  ),
                )
              }
            >
              <option value="asc">По возрастанию</option>
              <option value="desc">По убыванию</option>
            </select>
            <button
              type="button"
              className="icon-button"
              aria-label={`Удалить сортировку ${index + 1}`}
              onClick={() =>
                setSorts((items) => items.filter((_, i) => i !== index))
              }
            >
              ×
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary-button"
          disabled={
            sorts.length >= 3 ||
            !properties.some(
              (item) =>
                item.kind !== "multi_select" &&
                !sorts.some((sort) => sort.property_id === item.id),
            )
          }
          onClick={() => {
            const property = properties.find(
              (item) =>
                item.kind !== "multi_select" &&
                !sorts.some((sort) => sort.property_id === item.id),
            );
            if (property)
              setSorts((items) => [
                ...items,
                { property_id: property.id, direction: "asc" },
              ]);
          }}
        >
          + Сортировка
        </button>
        <ActionFeedback {...action} />
        <div className="modal-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Отмена
          </button>
          <button className="primary-button" disabled={action.busy}>
            {editing ? "Сохранить вид" : "Создать вид"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
function filterOperators(property: Property | undefined) {
  const empty = [
    { value: "is_empty", label: "Не заполнено" },
    { value: "is_not_empty", label: "Заполнено" },
  ];
  if (!property) return empty;
  if (property.kind === "multi_select")
    return [{ value: "contains", label: "Содержит вариант" }, ...empty];
  const equality = [
    { value: "eq", label: "Равно" },
    { value: "neq", label: "Не равно" },
  ];
  if (property.kind === "number" || property.kind === "date")
    return [
      ...equality,
      { value: "gt", label: "Больше / позже" },
      { value: "gte", label: "Не меньше / не раньше" },
      { value: "lt", label: "Меньше / раньше" },
      { value: "lte", label: "Не больше / не позже" },
      ...empty,
    ];
  if (property.kind === "text")
    return [
      ...equality,
      { value: "contains", label: "Содержит текст" },
      ...empty,
    ];
  return [...equality, ...empty];
}
function FilterValue({
  property,
  value,
  label,
  onChange,
}: {
  property: Property;
  value: Value;
  label: string;
  onChange: (value: Value) => void;
}) {
  if (property.kind === "checkbox")
    return (
      <select
        aria-label={label}
        value={String(value ?? false)}
        onChange={(event) => onChange(event.target.value === "true")}
      >
        <option value="true">Отмечено</option>
        <option value="false">Не отмечено</option>
      </select>
    );
  if (property.kind === "select" || property.kind === "multi_select")
    return (
      <select
        aria-label={label}
        value={typeof value === "string" ? value : ""}
        required
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Выбрать…</option>
        {property.options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
    );
  if (property.kind === "date") {
    const date =
      value && typeof value === "object" && !Array.isArray(value)
        ? value
        : { kind: "date" as const, start: "", end: null };
    return (
      <div className="filter-date">
        <select
          aria-label={`${label}: формат`}
          value={date.kind}
          onChange={(event) =>
            onChange({
              kind: event.target.value as "date" | "datetime",
              start: "",
              end: null,
            })
          }
        >
          <option value="date">Дата</option>
          <option value="datetime">Время со смещением</option>
        </select>
        <input
          type={date.kind === "date" ? "date" : "text"}
          aria-label={label}
          value={date.start}
          required
          placeholder="2026-10-21T12:00:00+03:00"
          onChange={(event) => onChange({ ...date, start: event.target.value })}
        />
        <input
          type={date.kind === "date" ? "date" : "text"}
          aria-label={`${label}: конец`}
          value={date.end ?? ""}
          onChange={(event) =>
            onChange({ ...date, end: event.target.value || null })
          }
        />
      </div>
    );
  }
  return (
    <input
      type={property.kind === "number" ? "number" : "text"}
      step={property.kind === "number" ? "any" : undefined}
      aria-label={label}
      value={
        typeof value === "string" || typeof value === "number" ? value : ""
      }
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function DatabaseSettings({
  database,
  base,
  onSaved,
  onClose,
}: {
  database: Database;
  base: string;
  onSaved: () => Promise<void>;
  onClose: () => void;
}) {
  const action = useAction();
  const [confirm, setConfirm] = useState(false);
  return (
    <Modal title="Настройки базы" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void action.run(async () => {
            await writeJson(base, "PATCH", {
              name: data.get("name"),
              expected_version: database.version,
            });
            await onSaved();
            onClose();
          });
        }}
      >
        <h2>Настройки базы</h2>
        <label htmlFor="rename-database">Название</label>
        <input
          id="rename-database"
          name="name"
          defaultValue={database.name}
          required
          maxLength={100}
        />
        <ActionFeedback {...action} />
        <div className="modal-actions">
          <button
            type="button"
            className="danger-button"
            onClick={() => setConfirm(true)}
          >
            В корзину
          </button>
          <button className="primary-button" disabled={action.busy}>
            Сохранить
          </button>
        </div>
      </form>
      {confirm && (
        <div className="confirm-inline">
          <p>Убрать базу в корзину? Страницы и значения сохранятся.</p>
          <button
            className="danger-button"
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                await writeJson(`${base}/trash`, "POST", {
                  expected_version: database.version,
                });
                await onSaved();
                onClose();
              }, "База в корзине")
            }
          >
            Подтвердить
          </button>
        </div>
      )}
    </Modal>
  );
}

function PropertyManager({
  base,
  databaseId,
  onSaved,
  onClose,
}: {
  base: string;
  databaseId: string;
  onSaved: () => Promise<void>;
  onClose: () => void;
}) {
  const [trashed, setTrashed] = useState(false);
  const [editing, setEditing] = useState<Property | null>(null);
  const [pending, setPending] = useState<Property | null>(null);
  const action = useAction();
  const query = useQuery({
    queryKey: ["property-manager", databaseId, trashed],
    queryFn: ({ signal }) =>
      requestJson<{ items: Property[]; schema_version: number }>(
        `${base}/properties?trashed=${trashed}`,
        { signal },
      ),
  });
  async function refresh() {
    await onSaved();
    await query.refetch();
  }
  return (
    <Modal title="Поля базы" onClose={onClose}>
      <h2>Поля базы данных</h2>
      <div className="segmented-control">
        <button
          className={!trashed ? "selected" : ""}
          onClick={() => setTrashed(false)}
        >
          Активные
        </button>
        <button
          className={trashed ? "selected" : ""}
          onClick={() => setTrashed(true)}
        >
          Корзина полей
        </button>
      </div>
      <QueryState
        pending={query.isPending}
        error={query.error}
        retry={() => void query.refetch()}
      />
      {query.data?.items.map((property) => (
        <div className="property-row" key={property.id}>
          <div>
            <strong>{property.name}</strong>
            <small>
              {kinds.find((item) => item.value === property.kind)?.label}
            </small>
          </div>
          <div className="row-actions">
            {!trashed && (
              <button
                className="text-action"
                onClick={() => setEditing(property)}
              >
                Изменить
              </button>
            )}
            <button
              className="text-action"
              onClick={() => setPending(property)}
            >
              {trashed ? "Восстановить" : "В корзину"}
            </button>
          </div>
        </div>
      ))}
      {query.data && !query.data.items.length && (
        <p className="muted">Здесь пока нет полей.</p>
      )}
      <ActionFeedback {...action} />
      {editing && query.data && (
        <PropertyCreate
          base={base}
          schema={query.data.schema_version}
          editing={editing}
          onSaved={refresh}
          onClose={() => setEditing(null)}
        />
      )}{" "}
      {pending && query.data && (
        <div className="confirm-inline">
          <p>
            {trashed
              ? "Восстановить поле и его сохранённые значения?"
              : "Убрать поле в корзину? Значения останутся в базе. Использующие поле виды могут потребовать настройки."}
          </p>
          <button className="secondary-button" onClick={() => setPending(null)}>
            Отмена
          </button>{" "}
          <button
            className={trashed ? "primary-button" : "danger-button"}
            disabled={action.busy}
            onClick={() =>
              void action.run(
                async () => {
                  await writeJson(
                    `${base}/properties/${pending.id}/${trashed ? "restore" : "trash"}`,
                    "POST",
                    {
                      expected_version: pending.version,
                      expected_schema_version: query.data!.schema_version,
                    },
                  );
                  setPending(null);
                  await refresh();
                },
                trashed ? "Поле восстановлено" : "Поле в корзине",
              )
            }
          >
            Подтвердить
          </button>
        </div>
      )}
    </Modal>
  );
}
