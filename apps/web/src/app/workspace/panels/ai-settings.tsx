"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { requestJson, writeJson } from "@/shared/api";
import { ActionFeedback, Modal, QueryState, useAction } from "@/shared/ui";
import { aiBase, type Connection } from "./ai-api";

type Preferences = { instructions: string; version: number };

export function AiSettings({
  onDirtyChange,
}: {
  onDirtyChange: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const action = useAction();
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState<Connection | null>(null);
  const preferences = useQuery({
    queryKey: ["ai-preferences"],
    queryFn: ({ signal }) =>
      requestJson<Preferences>(`${aiBase}/preferences`, { signal }),
  });
  const connections = useQuery({
    queryKey: ["ai-connections"],
    queryFn: ({ signal }) =>
      requestJson<{ items: Connection[] }>(`${aiBase}/connections`, { signal }),
  });
  return (
    <div className="ai-settings">
      <section className="panel">
        <h2>Как тебе отвечать</h2>
        <p className="muted">
          Тон, язык и подробность ответов. Сохраняются отдельно от чатов до
          изменения или очистки.
        </p>
        <QueryState
          pending={preferences.isPending}
          error={preferences.error}
          retry={() => void preferences.refetch()}
        />
        {preferences.data && (
          <InstructionsForm
            initial={preferences.data}
            onDirtyChange={onDirtyChange}
          />
        )}
      </section>
      <section className="panel">
        <div className="panel-toolbar">
          <h2>Мои API-подключения</h2>
          <button
            className="secondary-button"
            onClick={() => setConnecting(true)}
          >
            Подключить API
          </button>
        </div>
        <p className="muted">
          Для AI Ukladen свой ключ не нужен. Личное подключение OpenRouter —
          дополнительная возможность. Ключ хранится зашифрованным на сервере и
          больше не показывается. Выбор подключения и модели выполняется при
          создании чата.
        </p>
        <QueryState
          pending={connections.isPending}
          error={connections.error}
          retry={() => void connections.refetch()}
        />
        {connections.data?.items.length === 0 && (
          <p>Личных подключений пока нет.</p>
        )}
        {connections.data?.items.map((connection) => (
          <div className="resource-row" key={connection.id}>
            <div>
              <strong>{connection.label}</strong>
              <p className="muted">
                {connection.key_mask} ·{" "}
                {connection.disconnected_at ? "Отключено" : "Подключено"}
              </p>
            </div>
            {!connection.disconnected_at && (
              <button
                className="text-action danger-text"
                onClick={() => setDisconnecting(connection)}
              >
                Отключить
              </button>
            )}
          </div>
        ))}
        <ActionFeedback {...action} />
      </section>
      <section className="panel">
        <h2>Данные и ограничения</h2>
        <p>
          Запрос и необходимые фрагменты выбранных источников передаются
          выбранному провайдеру. Правила хранения провайдера отличаются от
          удаления в Ukladen.
        </p>
        <p>
          Чаты удаляются через 30 дней после последнего твоего сообщения.
          Просмотр и ответы AI этот срок не продлевают. Статистика хранится
          отдельно 30 дней.
        </p>
        <p className="muted">
          Настройки рабочего времени и планирование появятся вместе с модулем
          задач. Личные инструкции не дают AI разрешений изменять данные.
        </p>
      </section>
      {connecting && <ConnectionForm onClose={() => setConnecting(false)} />}
      {disconnecting && (
        <Modal title="Отключить API" onClose={() => setDisconnecting(null)}>
          <h2>Отключить {disconnecting.label}?</h2>
          <p>
            Ключ будет удалён с сервера. Незавершённые запросы через него
            остановятся; для другого подключения понадобится новый чат.
          </p>
          <button
            className="danger-button"
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                await writeJson(
                  `${aiBase}/connections/${disconnecting.id}`,
                  "DELETE",
                );
                setDisconnecting(null);
                await client.invalidateQueries({
                  queryKey: ["ai-connections"],
                });
              }, "Подключение отключено")
            }
          >
            Отключить
          </button>
          <ActionFeedback {...action} />
        </Modal>
      )}
    </div>
  );
}

function InstructionsForm({
  initial,
  onDirtyChange,
}: {
  initial: Preferences;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [saved, setSaved] = useState(initial);
  const [instructions, setInstructions] = useState(initial.instructions);
  const action = useAction();
  const client = useQueryClient();
  const dirty = instructions !== saved.instructions;
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void action.run(async () => {
          const result = await writeJson<Preferences>(
            `${aiBase}/preferences`,
            "PUT",
            { instructions, expected_version: saved.version },
          );
          setSaved(result);
          client.setQueryData(["ai-preferences"], result);
        });
      }}
    >
      <label className="field-label">
        Личные инструкции
        <textarea
          value={instructions}
          maxLength={8192}
          rows={7}
          onChange={(event) => setInstructions(event.target.value)}
          placeholder="Например: отвечай по-русски, кратко, с примерами."
        />
      </label>
      <p className="muted">
        До 8 КиБ текста. Обычные сообщения не становятся постоянной памятью.
      </p>
      <div className="panel-toolbar">
        <button className="primary-button" disabled={action.busy || !dirty}>
          Сохранить инструкции
        </button>
        <button
          className="secondary-button"
          type="button"
          disabled={action.busy || !instructions}
          onClick={() => setInstructions("")}
        >
          Очистить поле
        </button>
      </div>
      <ActionFeedback {...action} />
    </form>
  );
}

function ConnectionForm({ onClose }: { onClose: () => void }) {
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const client = useQueryClient();
  const action = useAction();
  return (
    <Modal title="Подключение OpenRouter" onClose={onClose}>
      <h2>Подключить OpenRouter</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          const credential = key;
          setKey("");
          void action.run(async () => {
            await writeJson(`${aiBase}/connections`, "POST", {
              label,
              key: credential,
            });
            await client.invalidateQueries({ queryKey: ["ai-connections"] });
            onClose();
          });
        }}
      >
        <label className="field-label">
          Название подключения
          <input
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            maxLength={100}
            required
          />
        </label>
        <label className="field-label">
          API-ключ
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            minLength={16}
            maxLength={1024}
            required
          />
        </label>
        <p className="muted">
          Сохранение не выполняет запрос к провайдеру. Ключ очищается из формы
          при отправке.
        </p>
        <button className="primary-button" disabled={action.busy}>
          Сохранить подключение
        </button>
        <ActionFeedback {...action} />
      </form>
    </Modal>
  );
}
