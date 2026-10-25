import { csrfToken, request } from "@/shared/api";

export const aiBase = "/api/v1/ai";
export type Source = {
  source:
    | "page"
    | "material"
    | "database"
    | "database_record"
    | "personal"
    | "official"
    | "record_date";
  id: string;
  title: string;
  version: number;
  locator: string;
  parent_id: string | null;
};
export type Conversation = {
  id: string;
  title: string;
  provider: string;
  model: string;
  offering_id: string | null;
  connection_id: string | null;
};
export type Message = {
  id: string;
  sequence: number;
  role: string;
  content: string;
  sources: Source[];
};
export type Run = {
  estimated_cost: string | null;
  unpriced_attempts: number;
  id: string;
  status:
    | "queued"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "interrupted";
  provider: string;
  model: string;
  submission_id: string;
  attempts: {
    number: number;
    status: string;
    input_tokens: number | null;
    output_tokens: number | null;
    error_code: string | null;
  }[];
  tools: {
    tool_name: string;
    number: number;
    status: string;
    error_code: string | null;
  }[];
  price: {
    date: string;
    currency: string;
    input_per_million: string;
    output_per_million: string;
  } | null;
};
export type Model = {
  id: string;
  name: string;
  provider: string;
  model: string;
  streaming: boolean;
  tools: boolean;
  free_only: boolean;
  personal_allowed: boolean;
  available: boolean;
  operator_available: boolean;
  is_default: boolean;
};
export type AiAccessStatus = {
  plan: string;
  monthly_request_limit: number | null;
  monthly_token_limit: number | null;
};
export type Connection = {
  id: string;
  label: string;
  key_mask: string;
  disconnected_at: string | null;
};
export type Scope = {
  page_ids: string[];
  material_ids: string[];
  database_ids: string[];
  calendar: boolean;
};
export const emptyScope = (): Scope => ({
  page_ids: [],
  material_ids: [],
  database_ids: [],
  calendar: false,
});
export const activeRun = (run?: Run | null) =>
  !!run && ["queued", "running", "interrupted"].includes(run.status);
export const runLabels: Record<Run["status"], string> = {
  queued: "В очереди",
  running: "Готовлю ответ",
  completed: "Готово",
  failed: "Не удалось завершить ответ",
  cancelled: "Остановлено",
  interrupted: "Выполнение приостановлено",
};

export async function streamMessage(
  conversationId: string,
  payload: { submission_id: string; message: string; source_scope?: Scope },
  signal: AbortSignal,
  receive: (event: string, data: Record<string, unknown>) => void,
) {
  const token = await csrfToken(signal);
  const response = await request(
    `${aiBase}/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": token,
        Accept: "text/event-stream",
      },
      body: JSON.stringify(payload),
    },
  );
  if (
    !response.headers.get("content-type")?.startsWith("text/event-stream") ||
    !response.body
  )
    throw new Error("Поток ответа недоступен. Обновите состояние чата.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "",
    done = false;
  try {
    while (!signal.aborted) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value, { stream: !chunk.done });
      if (buffer.length > 262144)
        throw new Error("Ответ превышает допустимый размер.");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = frame
          .split("\n")
          .find((line) => line.startsWith("event: "))
          ?.slice(7);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data: "))
          .map((line) => line.slice(6))
          .join("\n");
        if (event && data) {
          const parsed: unknown = JSON.parse(data);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
            throw new Error("Некорректный поток ответа.");
          receive(event, parsed as Record<string, unknown>);
          if (event === "done") done = true;
        }
      }
      if (chunk.done) break;
    }
    if (!done && !signal.aborted)
      throw new Error("Соединение прервано. Восстановите состояние чата.");
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
