import { expect, test } from "@playwright/test";
import { proposalMessageId } from "../src/app/workspace/panels/ai-proposal-history";
import type { Message } from "../src/app/workspace/panels/ai-api";

const at = "2026-11-23T10:08:07.416390Z";
const run = { id: "create-run", conversation_id: "chat", created_at: at };
const message = (id: string, sequence: number, role: string, created_at = at): Message => ({
  id, sequence, role, created_at, content: "Synthetic content", sources: [],
});

test("proposal binding uses the originating run timestamp, not the latest answer or proposal time", () => {
  expect(proposalMessageId([
    message("create", 1, "user"), message("create-answer", 2, "assistant"),
    message("friday", 3, "user", "2026-11-23T10:54:00Z"), message("friday-answer", 4, "assistant"),
  ], run, "chat")).toBe("create-answer");
});

test("proposal binding does not cross failed user turns or guess across a history boundary", () => {
  expect(proposalMessageId([
    message("failed", 1, "user"), message("retry", 2, "user", "2026-11-23T10:09:00Z"),
    message("retry-answer", 3, "assistant"),
  ], run, "chat")).toBeUndefined();
  expect(proposalMessageId([message("answer-without-request", 2, "assistant")], run, "chat")).toBeUndefined();
});

test("proposal binding preserves microseconds and rejects foreign or ambiguous runs", () => {
  const messages = [
    message("other", 1, "user", "2026-11-23T10:08:07.416389Z"), message("other-answer", 2, "assistant"),
    message("request", 3, "user"), message("answer", 4, "assistant"),
  ];
  expect(proposalMessageId(messages, run, "chat")).toBe("answer");
  expect(proposalMessageId(messages, run, "another-chat")).toBeUndefined();
  expect(proposalMessageId([...messages, message("duplicate", 5, "user")], run, "chat")).toBeUndefined();
  expect(proposalMessageId(messages, { ...run, created_at: "" }, "chat")).toBeUndefined();
});
