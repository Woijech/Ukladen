import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import { uniqueAnswerSources, type Source } from "./ai-api";

export type MarkdownNode = { type: string; value?: string; url?: string; identifier?: string; children?: MarkdownNode[] };
const markdown = unified().use(remarkParse).use(remarkGfm).freeze();

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

export function linkSourceCitations(tree: MarkdownNode, sources: readonly Source[]): Source[] {
  const cited: Source[] = [];
  const footnotes = new Map<string, MarkdownNode>();
  for (const node of tree.children ?? []) {
    if (node.type === "footnoteDefinition" && node.identifier && !footnotes.has(node.identifier)) footnotes.set(node.identifier, node);
  }
  const visitedFootnotes = new Set<string>();
  function visit(node: MarkdownNode, referencedFootnote = false) {
    if (node.type === "footnoteDefinition" && !referencedFootnote) return;
    if (node.type === "footnoteReference" && node.identifier && !visitedFootnotes.has(node.identifier)) {
      visitedFootnotes.add(node.identifier);
      const definition = footnotes.get(node.identifier);
      if (definition) visit(definition, true);
    }
    if (!node.children || ["link", "linkReference", "image", "imageReference"].includes(node.type)) return;
    node.children = node.children.flatMap((child) => {
      if (child.type !== "text") { visit(child); return [child]; }
      return (child.value ?? "").split(/(\[source:[^\]\n]+\])/g).filter(Boolean).map((value) => {
        const citation = resolveSourceCitation(value, sources);
        if (!citation) return { type: "text", value };
        cited.push(sources[citation.index]);
        return {
          type: "link", url: `#ukladen-source-${citation.index}`,
          children: [{ type: "text", value: citation.label }],
        };
      });
    });
  }
  visit(tree);
  return uniqueAnswerSources(cited);
}

export function citedAnswerSources(text: string, sources: readonly Source[]): Source[] {
  if (!sources.length || !text.includes("[source:")) return [];
  return linkSourceCitations(markdown.parse(text), sources);
}
