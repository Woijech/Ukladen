"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useSearchParams } from "next/navigation";
import Image from "next/image";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import symbol from "@/shared/assets/ukladen-avatar.png";
import { requestJson, writeJson } from "@/shared/api";
import {
  ActionFeedback,
  EmptyState,
  Modal,
  Pager,
  QueryState,
  useAction,
} from "@/shared/ui";
import {
  activeRun,
  aiBase,
  runLabels,
  streamMessage,
  type Connection,
  type Conversation,
  type Message,
  type Model,
  type Run,
  type Scope,
  type Source,
} from "./ai-api";
import { AiSettings } from "./ai-settings";
import { SourcePicker, SourceViewer } from "./ai-sources";
import { AiUsage, RunDetails } from "./ai-usage";
import "./ai.css";

const toolLabels: Record<string, string> = {
  search_workspace: "Ищу в твоём пространстве",
  read_page: "Читаю страницу",
  read_material_excerpt: "Читаю материал",
  get_calendar_events: "Смотрю календарь",
  list_databases: "Ищу базы данных",
  read_database: "Смотрю структуру базы",
  query_database: "Читаю записи",
  fake_double: "Проверяю тестовый инструмент",
};

export function AiPanel({
  onDirtyChange,
}: {
  onDirtyChange: (dirty: boolean) => void;
}) {
  const path = usePathname();
  const params = useSearchParams();
  const tab = path.endsWith("/usage")
    ? "usage"
    : params.get("tab") === "settings"
      ? "settings"
      : "chat";
  const selected = params.get("chat");
  const [dirty, setDirty] = useState(false);
  const [pendingUrl, setPendingUrl] = useState<string | null>(null);
  const changeDirty = useCallback(
    (value: boolean) => {
      setDirty(value);
      onDirtyChange(value);
    },
    [onDirtyChange],
  );
  function go(url: string) {
    if (dirty) setPendingUrl(url);
    else window.history.pushState(null, "", url);
  }
  useEffect(() => {
    const prevent = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  return (
    <div className="feature-page ai-page">
      <div className="page-heading">
        <div>
          <span className="greeting">РЯДОМ С ТВОИМИ МЫСЛЯМИ</span>
          <h1>Твой AI</h1>
          <p className="heading-subtitle">
            Найти, разобраться, связать главное.
          </p>
        </div>
      </div>
      <div className="ai-tabs" aria-label="Разделы AI">
        {[
          ["chat", "Чаты", "/workspace/ai"],
          ["usage", "Использование", "/workspace/ai/usage"],
          ["settings", "Настройки AI", "/workspace/ai?tab=settings"],
        ].map(([key, label, url]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            aria-current={tab === key ? "page" : undefined}
            onClick={() => go(url)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "settings" ? (
        <AiSettings onDirtyChange={changeDirty} />
      ) : tab === "usage" ? (
        <AiUsage />
      ) : (
        <ChatArea
          selected={selected}
          onChoose={(id) =>
            go(
              id
                ? `/workspace/ai?chat=${encodeURIComponent(id)}`
                : "/workspace/ai",
            )
          }
          onDirtyChange={changeDirty}
        />
      )}
      {pendingUrl && (
        <Modal title="Отменить изменения" onClose={() => setPendingUrl(null)}>
          <h2>Оставить несохранённый текст?</h2>
          <p>Черновик не сохранится после перехода.</p>
          <button
            className="danger-button"
            onClick={() => {
              changeDirty(false);
              window.history.pushState(null, "", pendingUrl);
              setPendingUrl(null);
            }}
          >
            Перейти без сохранения
          </button>
        </Modal>
      )}
    </div>
  );
}

function ChatArea({
  selected,
  onChoose,
  onDirtyChange,
}: {
  selected: string | null;
  onChoose: (id: string | null) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const [offset, setOffset] = useState(0);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Conversation | null>(null);
  const action = useAction();
  const client = useQueryClient();
  const list = useQuery({
    queryKey: ["ai-conversations", offset],
    staleTime: 0,
    queryFn: ({ signal }) =>
      requestJson<{ items: Conversation[] }>(
        `${aiBase}/conversations?limit=20&offset=${offset}`,
        { signal },
      ),
  });
  return (
    <>
      <QueryState
        pending={list.isPending}
        error={list.error}
        retry={() => void list.refetch()}
      />
      {list.isError && (
        <p className="muted">
          Если AI ещё не включён, потребуется настройка сервера и модели. Твои
          страницы и календарь доступны независимо от AI.
        </p>
      )}
      {list.data && (
        <div className="ai-layout panel">
          <aside className="ai-history" aria-label="История чатов">
            <button
              className="primary-button"
              onClick={() => setCreating(true)}
            >
              ＋ Новый чат
            </button>
            <h2>Твои чаты</h2>
            {list.data.items.map((chat) => (
              <div className="ai-history-row" key={chat.id}>
                <button
                  className={selected === chat.id ? "active" : ""}
                  aria-current={selected === chat.id ? "true" : undefined}
                  onClick={() => onChoose(chat.id)}
                >
                  {chat.title}
                  <small>
                    {chat.provider === "fake" ? "Демонстрация" : chat.model}
                  </small>
                </button>
                <button
                  className="icon-button"
                  aria-label={`Удалить чат ${chat.title}`}
                  onClick={() => setDeleting(chat)}
                >
                  ×
                </button>
              </div>
            ))}
            {list.data.items.length === 0 && (
              <p className="muted">
                Начни новую беседу. История останется здесь.
              </p>
            )}
            <Pager
              offset={offset}
              count={list.data.items.length}
              size={20}
              onChange={setOffset}
            />
            <p className="ai-retention muted">
              30 дней с последнего твоего сообщения. Удаление чата
              окончательное.
            </p>
          </aside>
          {selected ? (
            <Chat key={selected} id={selected} onDirtyChange={onDirtyChange} />
          ) : (
            <div className="ai-welcome">
              <Image src={symbol} alt="" width={72} height={72} />
              <EmptyState title="Что хочешь прояснить?" icon="">
                <p>Спроси о своих заметках, материалах или календаре.</p>
                <button
                  className="secondary-button"
                  onClick={() => setCreating(true)}
                >
                  Начать беседу
                </button>
              </EmptyState>
              <div className="ai-suggestions">
                <span>Что запланировано на завтра?</span>
                <span>Найди заметку по теме</span>
                <span>Объясни выбранный материал</span>
              </div>
            </div>
          )}
        </div>
      )}
      {creating && (
        <NewChat
          onClose={() => setCreating(false)}
          onCreated={(chat) => {
            setCreating(false);
            onChoose(chat.id);
            void client.invalidateQueries({ queryKey: ["ai-conversations"] });
          }}
        />
      )}
      {deleting && (
        <Modal title="Удалить чат" onClose={() => setDeleting(null)}>
          <h2>Удалить «{deleting.title}»?</h2>
          <p>
            Переписка будет удалена без корзины. Независимые страницы и события
            сохранятся.
          </p>
          <button
            className="danger-button"
            disabled={action.busy}
            onClick={() =>
              void action.run(async () => {
                await writeJson(
                  `${aiBase}/conversations/${deleting.id}`,
                  "DELETE",
                );
                if (selected === deleting.id) onChoose(null);
                setDeleting(null);
                await client.invalidateQueries({
                  queryKey: ["ai-conversations"],
                });
              })
            }
          >
            Удалить чат
          </button>
          <ActionFeedback {...action} />
        </Modal>
      )}
    </>
  );
}

function NewChat({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (chat: Conversation) => void;
}) {
  const [title, setTitle] = useState("Новая беседа");
  const [chosenOffering, setOffering] = useState<string | null>(null);
  const [connection, setConnection] = useState("");
  const action = useAction();
  const models = useQuery({
    queryKey: ["ai-models"],
    queryFn: ({ signal }) =>
      requestJson<Model[]>(`${aiBase}/models`, { signal }),
  });
  const connections = useQuery({
    queryKey: ["ai-connections"],
    queryFn: ({ signal }) =>
      requestJson<{ items: Connection[] }>(`${aiBase}/connections`, { signal }),
  });
  const offering =
    chosenOffering ??
    models.data?.find((item) => item.is_default)?.id ??
    models.data?.find(
      (item) => item.available && item.operator_available && item.streaming,
    )?.id ??
    (models.data?.length === 0 ? "__demo__" : "");
  const model = models.data?.find((item) => item.id === offering);
  const personalConnections =
    connections.data?.items.filter((item) => !item.disconnected_at) ?? [];
  const canUse = (item: Model) =>
    item.available &&
    item.streaming &&
    (item.operator_available ||
      (item.personal_allowed && personalConnections.length > 0));
  const canCreate =
    offering === "__demo__" ||
    (model &&
      canUse(model) &&
      (connection
        ? model.personal_allowed &&
          personalConnections.some((item) => item.id === connection)
        : model.operator_available));
  return (
    <Modal title="Новый AI-чат" onClose={onClose}>
      <h2>Новая беседа</h2>
      <QueryState
        pending={models.isPending || connections.isPending}
        error={models.error ?? connections.error}
        retry={() => {
          void models.refetch();
          void connections.refetch();
        }}
      />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!canCreate) return;
          void action.run(async () =>
            onCreated(
              await writeJson<Conversation>(`${aiBase}/conversations`, "POST", {
                title,
                ...(offering === "__demo__"
                  ? { demo: true }
                  : {
                      offering_id: offering,
                      ...(connection ? { connection_id: connection } : {}),
                    }),
              }),
            ),
          );
        }}
      >
        <label className="field-label">
          Название чата
          <input
            value={title}
            maxLength={200}
            required
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="field-label">
          Модель
          <select
            aria-label="Модель"
            value={offering}
            onChange={(event) => {
              setOffering(event.target.value);
              setConnection("");
            }}
          >
            <option value="" disabled>
              Выбери модель
            </option>
            {models.data?.map((item) => (
              <option key={item.id} value={item.id} disabled={!canUse(item)}>
                {item.name}
                {!item.available ? " · пока недоступно" : ""}
                {item.available && !item.operator_available && !canUse(item)
                  ? " · подключение не настроено"
                  : ""}
                {item.free_only ? " · только бесплатные маршруты" : ""}
                {!item.streaming ? " · нет стриминга" : ""}
              </option>
            ))}
            <option value="__demo__">Демонстрация — без внешнего API</option>
          </select>
        </label>
        {model?.available && (
          <>
            <label className="field-label">
              Подключение
              <select
                aria-label="Подключение"
                value={connection}
                onChange={(event) => setConnection(event.target.value)}
              >
                <option value="" disabled={!model.operator_available}>
                  AI Ukladen
                  {!model.operator_available ? " · подключение не настроено" : ""}
                </option>
                {model.personal_allowed &&
                  personalConnections.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.label} · {item.key_mask}
                    </option>
                  ))}
              </select>
            </label>
            <p className="muted">
              {connection
                ? "Личное API-подключение."
                : model.operator_available
                  ? "Работает через подключение Ukladen. Свой ключ не нужен."
                  : "Для этой модели нужно настроенное подключение."}{" "}
              {model.tools
                ? "Доступны поиск и чтение твоих источников."
                : "Эта модель отвечает без доступа к пространству."}
            </p>
          </>
        )}
        {model && !canCreate && (
          <p className="muted">
            Подключение этой модели пока не настроено. Если у тебя есть личное
            подключение, выбери его; иначе модель должен подключить владелец Ukladen.
          </p>
        )}
        {offering === "__demo__" && (
          <p className="muted">
            Тестовая модель показывает заранее заданный ответ. Для настоящего
            помощника выбери настроенную модель.
          </p>
        )}
        <p className="muted">
          Модель и подключение закрепляются за чатом. Для смены создай новый
          чат.
        </p>
        <button
          className="primary-button"
          disabled={action.busy || !models.data || !connections.data || !canCreate}
        >
          Создать чат
        </button>
        <ActionFeedback {...action} />
      </form>
    </Modal>
  );
}

function Chat({
  id,
  onDirtyChange,
}: {
  id: string;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [scope, setScope] = useState<Scope | null>(null);
  const [picking, setPicking] = useState(false);
  const [source, setSource] = useState<Source | null>(null);
  const [details, setDetails] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [hasPending, setHasPending] = useState(false);
  const [draft, setDraft] = useState({ id: "", text: "" });
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const busy = useRef(false);
  const pending = useRef<{
    submission_id: string;
    message: string;
    source_scope?: Scope;
  } | null>(null);
  const action = useAction();
  const bottom = useRef<HTMLDivElement>(null);
  const stateKey = ["ai-state", id];
  const state = useQuery({
    queryKey: stateKey,
    staleTime: 0,
    queryFn: ({ signal }) =>
      requestJson<{ conversation: Conversation; run: Run | null }>(
        `${aiBase}/conversations/${id}/state`,
        { signal },
      ),
    refetchInterval: (query) =>
      !streaming && activeRun(query.state.data?.run) ? 1500 : false,
  });
  const history = useInfiniteQuery({
    queryKey: ["ai-messages", id],
    initialPageParam: null as number | null,
    staleTime: 0,
    queryFn: ({ signal, pageParam }) =>
      requestJson<{ items: Message[] }>(
        `${aiBase}/conversations/${id}/messages?recent=true&limit=50${pageParam ? `&before=${pageParam}` : ""}`,
        { signal },
      ),
    getNextPageParam: (last) =>
      last.items.length === 50 ? last.items[0].sequence : undefined,
  });
  const run = state.data?.run;
  const conversation = state.data?.conversation;
  const messages =
    history.data?.pages
      .slice()
      .reverse()
      .flatMap((page) => page.items) ?? [];
  const running = streaming || activeRun(run);
  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );
  useEffect(() => {
    onDirtyChange(!!text);
    return () => onDirtyChange(false);
  }, [text, onDirtyChange]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "nearest" });
  }, [draft.text, messages.length]);
  useEffect(() => {
    if (run && !activeRun(run))
      void client.invalidateQueries({ queryKey: ["ai-messages", id] });
  }, [run, client, id]);

  async function recover() {
    const current = await state.refetch({ throwOnError: true });
    await history.refetch({ throwOnError: true });
    if (current.data?.run?.submission_id === pending.current?.submission_id) {
      pending.current = null;
      setHasPending(false);
      setText("");
    }
    setDraft({ id: "", text: "" });
  }
  async function send(retry = false) {
    if (busy.current || (!retry && (!text.trim() || running))) return;
    const payload = retry
      ? pending.current
      : {
          submission_id: crypto.randomUUID(),
          message: text,
          ...(scope === null ? {} : { source_scope: scope }),
        };
    if (!payload) return;
    if (new TextEncoder().encode(payload.message).length > 16384) {
      setError("Сообщение превышает 16 КиБ. Сократи текст.");
      return;
    }
    busy.current = true;
    pending.current = payload;
    setHasPending(true);
    const abort = new AbortController();
    controller.current = abort;
    setStreaming(true);
    setError("");
    setDraft({ id: "", text: "" });
    setProgress("Отправляю запрос");
    try {
      await streamMessage(id, payload, abort.signal, (event, data) => {
        if (abort.signal.aborted) return;
        if (event === "run") {
          client.setQueryData(
            stateKey,
            (
              old: { conversation: Conversation; run: Run | null } | undefined,
            ) => (old ? { ...old, run: data as unknown as Run } : old),
          );
          setText("");
        } else if (
          event === "delta" &&
          typeof data.text === "string" &&
          typeof data.id === "string"
        ) {
          const part = data.text,
            messageId = data.id;
          setDraft((old) => ({
            id: messageId,
            text: (old.id === messageId ? old.text : "") + part,
          }));
        } else if (event === "progress") {
          setProgress(
            data.kind === "tool" && typeof data.name === "string"
              ? (toolLabels[data.name] ?? "Читаю источник")
              : "Готовлю ответ",
          );
          if (data.kind === "model") setDraft({ id: "", text: "" });
        }
      });
      if (!abort.signal.aborted) {
        pending.current = null;
        setHasPending(false);
        await recover();
        await client.invalidateQueries({ queryKey: ["ai-conversations"] });
      }
    } catch (caught) {
      if (!abort.signal.aborted) {
        setError(
          caught instanceof Error
            ? caught.message
            : "Не удалось получить ответ.",
        );
        await recover().catch(() => {});
      }
    } finally {
      busy.current = false;
      if (!abort.signal.aborted) setStreaming(false);
    }
  }
  async function stop() {
    controller.current?.abort();
    setStreaming(false);
    await action.run(async () => {
      const current = await state.refetch({ throwOnError: true });
      if (current.data?.run && activeRun(current.data.run))
        await writeJson(`${aiBase}/runs/${current.data.run.id}/cancel`, "POST");
      await recover();
    }, "Запрос остановлен");
  }
  return (
    <section className="ai-chat" aria-label="Переписка">
      <QueryState
        pending={state.isPending || history.isPending}
        error={state.error ?? history.error}
        retry={() => {
          void state.refetch();
          void history.refetch();
        }}
      />
      {conversation && (
        <>
          <header className="ai-chat-heading">
            <h2>{conversation.title}</h2>
            <p className="muted">
              {conversation.provider === "fake"
                ? "Тестовая модель · без внешнего API"
                : `${conversation.provider} · ${conversation.model} · ${conversation.connection_id ? "личный API" : "ключ приложения"}`}
            </p>
          </header>
          <div
            className="ai-messages"
            role="log"
            aria-label="Сообщения чата"
            aria-live="polite"
            aria-relevant="additions"
          >
            {messages.length === 0 && (
              <p className="muted">
                Начни с вопроса. AI пока может читать данные и объяснять, а
                изменения появятся в следующих этапах.
              </p>
            )}
            {messages.map((message) => (
              <article
                key={message.id}
                className={`ai-message ${message.role === "user" ? "from-user" : "from-ai"}`}
              >
                <strong>{message.role === "user" ? "Ты" : "Ukladen AI"}</strong>
                <div className="ai-message-text">
                  <CitedText
                    text={message.content}
                    sources={message.sources}
                    onOpen={setSource}
                  />
                </div>
                {message.sources.length > 0 && (
                  <div className="ai-citations" aria-label="Источники ответа">
                    {message.sources.map((item, index) => (
                      <button
                        className="ai-source-chip"
                        key={`${item.source}:${item.id}:${index}`}
                        onClick={() => setSource(item)}
                      >
                        {item.title || "Открыть источник"}
                      </button>
                    ))}
                  </div>
                )}
              </article>
            ))}
            {history.hasNextPage && (
              <button
                className="secondary-button"
                disabled={history.isFetchingNextPage}
                onClick={() => void history.fetchNextPage()}
              >
                Более ранние сообщения
              </button>
            )}
            {draft.text && (
              <article className="ai-message from-ai">
                <strong>Ukladen AI · ответ формируется</strong>
                <div className="ai-message-text">{draft.text}</div>
              </article>
            )}
            <div ref={bottom} />
          </div>
          {run && (
            <div className="ai-run-status">
              <span role="status">
                {running
                  ? progress || runLabels[run.status]
                  : runLabels[run.status]}
              </span>
              <button className="text-action" onClick={() => setDetails(true)}>
                Подробности
              </button>
            </div>
          )}
          <form
            className="ai-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void send();
            }}
          >
            <label className="visually-hidden" htmlFor="ai-message">
              Сообщение AI
            </label>
            <textarea
              id="ai-message"
              placeholder="Спроси о том, что важно…"
              value={text}
              maxLength={16384}
              disabled={running || hasPending}
              onChange={(event) => setText(event.target.value)}
              rows={3}
            />
            <div className="ai-composer-toolbar">
              <button
                className="secondary-button"
                type="button"
                disabled={running || hasPending}
                onClick={() => setPicking(true)}
              >
                {scope === null
                  ? "Все источники"
                  : `Источники: ${scope.page_ids.length + scope.material_ids.length + scope.database_ids.length}${scope.calendar ? " + календарь" : ""}`}
              </button>
              {running ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={action.busy || !activeRun(run)}
                  onClick={() => void stop()}
                >
                  Остановить
                </button>
              ) : (
                <button
                  className="primary-button"
                  disabled={!text.trim() || hasPending}
                >
                  Отправить ↑
                </button>
              )}
            </div>
            <p className="ai-processing muted">
              Запрос и нужные фрагменты передаются выбранному провайдеру. AI
              может ошибаться — проверяй источники.
            </p>
          </form>
          {error && (
            <div role="alert" className="form-error">
              <p>{error}</p>
              <button
                className="secondary-button"
                onClick={() =>
                  void action.run(recover, "Состояние восстановлено")
                }
              >
                Восстановить состояние
              </button>
              {hasPending && (
                <button
                  className="secondary-button"
                  disabled={streaming}
                  onClick={() => void send(true)}
                >
                  Повторить ту же отправку
                </button>
              )}
            </div>
          )}
          <ActionFeedback {...action} />
        </>
      )}
      {picking && (
        <SourcePicker
          value={scope}
          onSave={setScope}
          onClose={() => setPicking(false)}
        />
      )}
      {source && (
        <SourceViewer
          key={`${source.source}:${source.id}:${source.locator}`}
          source={source}
          onClose={() => setSource(null)}
        />
      )}
      {details && run && (
        <RunDetails runId={run.id} onClose={() => setDetails(false)} />
      )}
    </section>
  );
}

function CitedText({
  text,
  sources,
  onOpen,
}: {
  text: string;
  sources: Source[];
  onOpen: (source: Source) => void;
}): ReactNode {
  return text.split(/(\[source:[^\]\n]+\])/g).map((part, index) => {
    const reference = part.startsWith("[source:")
      ? sources.find((source) => source.id === part.slice(8, -1))
      : undefined;
    return reference ? (
      <button
        className="ai-inline-citation"
        key={index}
        onClick={() => onOpen(reference)}
      >
        {reference.title || "Источник"}
      </button>
    ) : (
      <span key={index}>{part}</span>
    );
  });
}
