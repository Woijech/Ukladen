import type { Source } from "./ai-api";

export function resolveSourceCitation(value: string, sources: readonly Source[]) {
  const match = /^\[source:[ \t]*([^\s,\]]+)[ \t]*(?:,[ \t]*(page|slide)[ \t]*:[ \t]*([1-9]\d*)[ \t]*)?\]$/.exec(value);
  if (!match) return null;
  const [, id, kind, number] = match;
  const index = sources.findIndex((source) => {
    if (source.id !== id) return false;
    if (!kind) return true;
    if (source.source !== "material") return false;
    const location = /(?:^|;)(page|slide):(\d+)(?:;|$)/.exec(source.locator);
    return location?.[1] === kind && location[2] === number;
  });
  if (index < 0) return null;
  const title = sources[index].title || "Источник";
  const label = kind ? `${title} · ${kind === "page" ? "стр." : "слайд"} ${number}` : title;
  return { index, label };
}
