import { createContext } from "react";

export type AssistantTarget = { kind: "page" | "event"; id: string; title: string };
export type AssistantRequest = { id: string; target: AssistantTarget; prompt: string };
export const WorkspaceAssistantContext = createContext<{
  target: AssistantTarget | null;
  ask: (target: AssistantTarget, prompt: string) => void;
}>({ target: null, ask: () => {} });
