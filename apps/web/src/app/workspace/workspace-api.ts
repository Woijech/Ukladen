export class RequestError extends Error {
  constructor(readonly status: number, message: string, readonly code?: string) { super(message); }
}

export class SessionExpiredError extends RequestError {}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string; code?: string } | null;
    if (response.status === 403 && payload?.code === "registration_incomplete") {
      window.location.replace("/auth/complete-registration");
      throw new SessionExpiredError(403, "Завершите регистрацию.", payload.code);
    }
    if (path === "/api/v1/auth/login" && response.status === 401) throw new RequestError(response.status, "Неверная почта или пароль.");
    if (path === "/api/v1/auth/register" && response.status === 409) throw new RequestError(response.status, "Аккаунт с такой почтой уже существует.");
    if (response.status === 401) throw new SessionExpiredError(response.status, "Войдите в аккаунт, чтобы открыть личное пространство.");
    if (payload?.code === "task_version_conflict") throw new RequestError(response.status, "Задача изменилась в другой вкладке. Загрузите актуальную версию перед повторным сохранением.", payload.code);
    if (payload?.code === "task_hierarchy_conflict") throw new RequestError(response.status, "Так нельзя изменить иерархию или статус задачи. Проверьте вложенные задачи и завершённые ветки.", payload.code);
    if (payload?.code === "task_not_found") throw new RequestError(response.status, "Задача не найдена или больше недоступна.", payload.code);
    if (response.status === 409) throw new RequestError(response.status, "Данные изменились. Обновите страницу и попробуйте ещё раз.", payload?.code);
    if (response.status === 403) throw new RequestError(response.status, "Сессия защиты устарела. Обновите страницу и повторите действие.", payload?.code);
    if (response.status === 422) throw new RequestError(response.status, payload?.detail === "Invalid academic selection." ? "Выбери группу и подгруппу из списка." : "Проверь заполненные данные.", payload?.code);
    throw new RequestError(response.status, response.status === 503 ? "Сервис временно недоступен." : "Не удалось выполнить запрос.", payload?.code);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function csrfToken() {
  const result = await requestJson<{ csrf_token: string }>("/api/v1/auth/csrf");
  return result.csrf_token;
}
