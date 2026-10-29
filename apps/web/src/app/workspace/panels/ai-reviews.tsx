"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, QueryState, useAction } from "@/shared/ui";
import { aiBase, type Connection, type Model, type Scope, type Source } from "./ai-api";
import { SourcePicker, SourceViewer } from "./ai-sources";

type Configuration = {
  enabled: boolean;
  daily: boolean;
  weekly: boolean;
  warnings: boolean;
  materials: boolean;
  daily_time: string;
  weekly_time: string;
  weekly_day: number;
  offering_id: string | null;
  connection_id: string | null;
  source_scope: Scope | null;
};
type SavedSettings = {
  configuration: Configuration;
  version: number;
  runtime_enabled: boolean;
  paused_reason: string | null;
  timezone: string;
};

export function ReviewSettings({ onDirtyChange }: { onDirtyChange: (dirty: boolean) => void }) {
  const settings = useQuery({
    queryKey: ["ai-review-settings"],
    queryFn: ({ signal }) => requestJson<SavedSettings>(`${aiBase}/reviews/settings`, { signal }),
  });
  return (
    <section className="panel">
      <h2>Обзоры и предупреждения AI</h2>
      <p>
        Ежедневный и недельный обзор, сроки, пересечения и нагрузка. Только твои данные,
        без фонового поиска в интернете. Изменения — после подтверждения в чате.
      </p>
      <QueryState
        pending={settings.isPending}
        error={settings.error}
        retry={() => void settings.refetch()}
      />
      {settings.data && <ReviewForm initial={settings.data} onDirtyChange={onDirtyChange} />}
    </section>
  );
}

function ReviewForm({
  initial,
  onDirtyChange,
}: {
  initial: SavedSettings;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [saved, setSaved] = useState(initial);
  const [value, setValue] = useState(initial.configuration);
  const [picking, setPicking] = useState(false);
  const action = useAction();
  const client = useQueryClient();
  const models = useQuery({
    queryKey: ["ai-models"],
    queryFn: ({ signal }) => requestJson<Model[]>(`${aiBase}/models`, { signal }),
  });
  const connections = useQuery({
    queryKey: ["ai-connections"],
    queryFn: ({ signal }) =>
      requestJson<{ items: Connection[] }>(`${aiBase}/connections`, { signal }),
  });
  const model = models.data?.find((item) => item.id === value.offering_id);
  const personal = connections.data?.items.filter((item) => !item.disconnected_at) ?? [];
  const canEnable = model?.available && model.tools && (value.connection_id
    ? model.personal_allowed && personal.some((item) => item.id === value.connection_id)
    : model.operator_available);
  const dirty = JSON.stringify(value) !== JSON.stringify(saved.configuration);
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  function toggle(key: "enabled" | "daily" | "weekly" | "warnings" | "materials", checked: boolean) {
    setValue({ ...value, [key]: checked });
  }
  const paused = saved.paused_reason === "connection_unavailable"
    ? "выбранное подключение или модель недоступны"
    : saved.paused_reason === "generation_unavailable"
      ? "не удалось подготовить обзор"
      : "не удалось проверить источники";

  return (
    <form onSubmit={(event) => {
      event.preventDefault();
      void action.run(async () => {
        const result = await writeJson<SavedSettings>(`${aiBase}/reviews/settings`, "PUT", {
          configuration: value,
          expected_version: saved.version,
        });
        setSaved(result);
        setValue(result.configuration);
        client.setQueryData(["ai-review-settings"], result);
      }, "Настройки обзоров сохранены");
    }}>
      {!saved.runtime_enabled && (
        <p className="muted" role="status">
          Фоновые обзоры пока не запущены на сервере. Настройки можно сохранить заранее.
        </p>
      )}
      {value.enabled && saved.paused_reason && (
        <p role="status">
          Обзоры приостановлены: {paused}. Можно изменить настройки или выключить обзоры.
        </p>
      )}
      <label className="checkbox-label">
        <input type="checkbox" checked={value.enabled}
          onChange={(event) => toggle("enabled", event.target.checked)} />
        Включить обзоры
      </label>
      <p className="muted">
        Время в часовом поясе профиля: {saved.timezone}. Результаты появятся в уведомлениях.
        Одинаковые предупреждения повторно не присылаются без изменения ситуации.
      </p>
      <QueryState
        pending={models.isPending || connections.isPending}
        error={models.error ?? connections.error}
        retry={() => { void models.refetch(); void connections.refetch(); }}
      />
      <label className="field-label">
        Модель для обзоров
        <select value={value.offering_id ?? ""} required={value.enabled}
          onChange={(event) => setValue({
            ...value, offering_id: event.target.value || null, connection_id: null,
          })}>
          <option value="">Выбери модель</option>
          {value.offering_id && !model && (
            <option value={value.offering_id}>Сохранённая модель недоступна</option>
          )}
          {models.data?.filter((item) => item.tools).map((item) => (
            <option key={item.id} value={item.id} disabled={!item.available}>
              {item.name}{!item.available ? " · недоступна" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="field-label">
        Подключение для обзоров
        <select value={value.connection_id ?? ""}
          onChange={(event) => setValue({ ...value, connection_id: event.target.value || null })}>
          <option value="" disabled={!model?.operator_available}>
            AI Ukladen{model && !model.operator_available ? " · недоступно" : ""}
          </option>
          {value.connection_id && !personal.some((item) => item.id === value.connection_id) && (
            <option value={value.connection_id}>Сохранённое подключение отключено</option>
          )}
          {model?.personal_allowed && personal.map((item) => (
            <option key={item.id} value={item.id}>{item.label} · {item.key_mask}</option>
          ))}
        </select>
      </label>
      {value.enabled && !canEnable && (
        <p className="muted">Выбери доступную модель и подключение. Без этого обзоры не запустятся.</p>
      )}
      <label className="checkbox-label">
        <input type="checkbox" checked={value.daily}
          onChange={(event) => toggle("daily", event.target.checked)} />
        Ежедневный обзор
      </label>
      <label className="field-label">
        Время ежедневного обзора
        <input type="time" value={value.daily_time} required
          onChange={(event) => setValue({ ...value, daily_time: event.target.value })} />
      </label>
      <label className="checkbox-label">
        <input type="checkbox" checked={value.weekly}
          onChange={(event) => toggle("weekly", event.target.checked)} />
        Недельный обзор
      </label>
      <label className="field-label">
        День недельного обзора
        <select value={value.weekly_day}
          onChange={(event) => setValue({ ...value, weekly_day: Number(event.target.value) })}>
          {["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
            .map((day, index) => <option key={day} value={index}>{day}</option>)}
        </select>
      </label>
      <label className="field-label">
        Время недельного обзора
        <input type="time" value={value.weekly_time} required
          onChange={(event) => setValue({ ...value, weekly_time: event.target.value })} />
      </label>
      <label className="checkbox-label">
        <input type="checkbox" checked={value.warnings}
          onChange={(event) => toggle("warnings", event.target.checked)} />
        Предупреждать о сроках, пересечениях и перегрузке
      </label>
      <label className="checkbox-label">
        <input type="checkbox" checked={value.materials}
          onChange={(event) => toggle("materials", event.target.checked)} />
        Подбирать мои заметки и материалы
      </label>
      <p className="muted">
        Просрочка и сроки в ближайшие 24 часа; пересечения и нагрузка на 7 дней.
        Неизвестные оценки и неполное расписание будут отмечены явно.
      </p>
      <button type="button" className="secondary-button" onClick={() => setPicking(true)}>
        Источники обзоров
      </button>
      <p className="muted">
        {value.source_scope
          ? "Только выбранные задачи, страницы, материалы и календарь."
          : "Мои активные задачи, календарь и относящиеся к ним заметки и материалы."}{" "}
        Ограничение сохраняется для следующих обзоров.
      </p>
      <button className="primary-button" disabled={
        action.busy || !dirty ||
        (value.enabled && (!canEnable || !(value.daily || value.weekly || value.warnings)))
      }>
        Сохранить обзоры
      </button>
      <button type="button" className="secondary-button" disabled={action.busy || !dirty}
        onClick={() => void action.run(async () => {
          const result = await requestJson<SavedSettings>(`${aiBase}/reviews/settings`);
          setSaved(result);
          setValue(result.configuration);
          client.setQueryData(["ai-review-settings"], result);
        }, "Загружены сохранённые настройки")}>
        Отменить изменения обзоров
      </button>
      <ActionFeedback {...action} />
      {picking && (
        <SourcePicker purpose="reviews" value={value.source_scope}
          onSave={(source_scope) => setValue({ ...value, source_scope })}
          onClose={() => setPicking(false)} />
      )}
    </form>
  );
}

type Report = {
  id: string;
  kind: string;
  status: string;
  created_at: string;
  expires_at: string;
  content: string | null;
  sources: Source[];
  stale: boolean;
};

export function ReviewNotificationButton({ id, timeZone }: { id: string; timeZone: string }) {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<Source | null>(null);
  return (
    <>
      <button className="text-action" onClick={() => setOpen(true)}>Открыть обзор</button>
      {source ? (
        <SourceViewer source={source} onClose={() => setSource(null)} />
      ) : open && (
        <ReviewDialog id={id} timeZone={timeZone} onClose={() => setOpen(false)} onSource={setSource} />
      )}
    </>
  );
}

function ReviewDialog({
  id, timeZone, onClose, onSource,
}: {
  id: string;
  timeZone: string;
  onClose: () => void;
  onSource: (source: Source) => void;
}) {
  const router = useRouter();
  const report = useQuery({
    queryKey: ["ai-review", id],
    queryFn: ({ signal }) => requestJson<Report>(`${aiBase}/reviews/${id}`, { signal }),
    staleTime: 0,
  });
  const action = useAction();
  const client = useQueryClient();
  const data = report.data;
  const content = data?.content?.replace(/\[source:([^\]\n]+)\]/g, (_, identifier) =>
    data.sources.find((item) => item.id === identifier)?.title ?? "Источник недоступен",
  );
  return (
    <Modal title="Обзор AI" onClose={onClose}>
      <h2>Обзор по твоим данным</h2>
      <QueryState pending={report.isPending} error={report.error} retry={() => void report.refetch()} />
      {data && (
        <>
          <p className="muted">
            Подготовлен {new Date(data.created_at).toLocaleString("ru", { timeZone })}.
            Данные могли измениться; срок хранения обзора — 30 дней. Фонового веб-поиска нет.
          </p>
          {data.stale ? (
            <p role="status">
              Источники изменились или недоступны. Старый текст скрыт.
              Получи актуальные данные в AI-чате.
            </p>
          ) : content ? (
            <div className="ai-message-content" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {content}
            </div>
          ) : (
            <p role="status">
              {["queued", "running"].includes(data.status)
                ? "Обзор готовится."
                : "Не удалось подготовить обзор. Проверь настройки AI."}
            </p>
          )}
          {data.sources.map((item) => (
            <button className="text-action" key={`${item.source}:${item.id}:${item.locator}`}
              onClick={() => onSource(item)}>{item.title || "Источник"}</button>
          ))}
          {data.status === "completed" && !data.stale && (
            <button className="primary-button" disabled={action.busy}
              onClick={() => void action.run(async () => {
                const result = await writeJson<{ conversation_id: string }>(
                  `${aiBase}/reviews/${id}/discuss`, "POST",
                );
                await client.invalidateQueries({ queryKey: ["ai-conversations"] });
                onClose();
                router.push(`/workspace/ai?chat=${encodeURIComponent(result.conversation_id)}`);
              }, "Чат открыт")}>
              Обсудить в AI-чате
            </button>
          )}
          <p className="muted">
            Открытие чата не отправляет запрос к модели. Изменения задач, заметок и календаря
            потребуют подтверждения.
          </p>
        </>
      )}
      <ActionFeedback {...action} />
    </Modal>
  );
}
