import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "./ai-api";
import { resolveSourceCitation } from "./ai-source-citations";
import "./ai-markdown.css";

type MarkdownNode = { type: string; value?: string; url?: string; children?: MarkdownNode[] };

function sourceLinks(sources: Source[]) {
  return () => (tree: MarkdownNode) => {
    function visit(node: MarkdownNode) {
      if (!node.children || node.type === "link") return;
      node.children = node.children.flatMap(child => {
        if (child.type !== "text") { visit(child); return [child]; }
        return (child.value ?? "").split(/(\[source:[^\]\n]+\])/g).filter(Boolean).map(value => {
          const citation = resolveSourceCitation(value, sources);
          return !citation ? { type: "text", value } : {
            type: "link", url: `#ukladen-source-${citation.index}`,
            children: [{ type: "text", value: citation.label }],
          };
        });
      });
    }
    visit(tree);
  };
}

export function AiMarkdown({ text, sources = [], onOpen }: {
  text: string; sources?: Source[]; onOpen?: (source: Source) => void;
}) {
  return <div className="ai-markdown"><ReactMarkdown remarkPlugins={[remarkGfm, sourceLinks(sources)]} components={{
    a: ({ href, children }) => {
      const match = /^#ukladen-source-(\d+)$/.exec(href ?? "");
      const source = match ? sources[Number(match[1])] : undefined;
      if (source && onOpen) return <button type="button" className="ai-inline-citation" onClick={() => onOpen(source)}>{children}</button>;
      if (!href || !/^(https?:|mailto:)/i.test(href)) return <span>{children}</span>;
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
    img: ({ alt }) => <span>{alt || "Изображение"}</span>,
    table: ({ children }) => <div className="ai-markdown-table" tabIndex={0} role="region" aria-label="Таблица в ответе"><table>{children}</table></div>,
  }}>{text}</ReactMarkdown></div>;
}
