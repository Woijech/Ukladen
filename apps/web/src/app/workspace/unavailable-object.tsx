import { RequestError } from "@/shared/api";

export function isUnavailableObject(error: unknown) {
  return error instanceof RequestError && (error.status === 404 || error.status === 403);
}

export function UnavailableObject({ onBack }: { onBack: () => void }) {
  return <div className="ui-error" role="alert">
    <strong>Объект недоступен</strong>
    <p>Запись удалена или у текущего аккаунта нет доступа.</p>
    <button type="button" className="secondary-button" onClick={onBack}>К списку</button>
  </div>;
}
