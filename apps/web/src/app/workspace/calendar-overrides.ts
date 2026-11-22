import { requestJson, writeJson } from "@/shared/api";

type Override = {
  official_event_id: string; version: number; hidden: boolean; skipped: boolean;
  title: string | null; description: string | null; location: string | null;
  starts_at: string | null; ends_at: string | null;
};

export async function hideOfficialEvent(event: { source_event_id: string; version: number }) {
  let current: Override | undefined;
  if (event.version > 0) {
    for (let offset = 0; ; offset += 100) {
      const result = await requestJson<{ items: { override: Override }[] }>(
        `/api/v1/calendar/overrides?limit=100&offset=${offset}`,
      );
      current = result.items.find(item => item.override.official_event_id === event.source_event_id)?.override;
      if (current || result.items.length < 100) break;
    }
    if (!current || current.version !== event.version)
      throw new Error("Пара изменилась. Обнови календарь и повтори действие.");
  }
  return writeJson<Override>(`/api/v1/calendar/overrides/${event.source_event_id}`, "PUT", {
    expected_version: event.version, hidden: true, skipped: true,
    title: current?.title ?? null, description: current?.description ?? null,
    location: current?.location ?? null, starts_at: current?.starts_at ?? null,
    ends_at: current?.ends_at ?? null,
  });
}
