import { useInfiniteQuery, useQueries } from "@tanstack/react-query";
import { RequestError, requestJson } from "@/shared/api";
import { aiBase, type Message, type Run } from "./ai-api";
import type { Proposal } from "./ai-actions";

type ProposalRun = Pick<Run, "id" | "conversation_id" | "created_at">;
export type ProposalEntry = { proposal: Proposal; offset: number };

export function proposalMessageId(messages: Message[], run: ProposalRun, chatId: string) {
  if (run.conversation_id !== chatId || !run.created_at) return undefined;
  // Admission stores the run and its user message with the same timestamp.
  // Compare the server strings, retaining microseconds (Date would truncate them).
  const starts = messages.filter(message => message.role === "user" && message.created_at === run.created_at);
  if (starts.length !== 1) return undefined;
  const index = messages.indexOf(starts[0]);
  for (const message of messages.slice(index + 1)) {
    if (message.role === "user") break;
    if (message.role === "assistant") return message.id;
  }
  return undefined;
}

export function useProposalHistory(chatId: string, runId: string | undefined, running: boolean, messages: Message[]) {
  const history = useInfiniteQuery({
    queryKey: ["ai-proposals", chatId, "history", runId],
    initialPageParam: 0,
    enabled: !running,
    staleTime: 0,
    queryFn: async ({ signal, pageParam }) => {
      try {
        return await requestJson<Proposal[]>(`${aiBase}/conversations/${chatId}/proposals?limit=10&offset=${pageParam}`, { signal });
      } catch (error) {
        if (error instanceof RequestError && error.status === 503) return [];
        throw error;
      }
    },
    getNextPageParam: (last, _pages, offset) => last.length === 10 ? offset + 10 : undefined,
  });
  const entries = history.data?.pages.flatMap((page, index) => page.map(proposal => ({ proposal, offset: index * 10 }))) ?? [];
  const ids = [...new Set(entries.map(entry => entry.proposal.run_id))];
  const runs = useQueries({ queries: ids.map(id => ({
    queryKey: ["ai-proposal-run", chatId, id],
    queryFn: ({ signal }: { signal: AbortSignal }) => requestJson<ProposalRun>(`${aiBase}/runs/${id}`, { signal }),
    staleTime: Infinity,
    retry: false,
  })) });
  const byMessage = new Map<string, ProposalEntry[]>(), unmatched: ProposalEntry[] = [];
  for (const entry of entries) {
    const result = runs[ids.indexOf(entry.proposal.run_id)];
    if (result.isPending) continue;
    const messageId = result.data?.id === entry.proposal.run_id
      ? proposalMessageId(messages, result.data, chatId) : undefined;
    if (messageId) byMessage.set(messageId, [...(byMessage.get(messageId) ?? []), entry]);
    else unmatched.push(entry);
  }
  return {
    history, byMessage, unmatched,
    resolving: history.isPending || history.isFetching || runs.some(result => result.isPending),
    error: history.error ?? runs.find(result => result.error)?.error,
    retry: () => { void history.refetch(); for (const run of runs) if (run.isError) void run.refetch(); },
  };
}
