import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "./ai-api";
import { linkSourceCitations, type MarkdownNode } from "./ai-source-citations";
import "./ai-markdown.css";

function sourceLinks(sources: Source[]) {
  return () => (tree: MarkdownNode) => {
    linkSourceCitations(tree, sources);
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
