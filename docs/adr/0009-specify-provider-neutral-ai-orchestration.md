# ADR 0009: Specify Provider-Neutral AI Orchestration and Planning Boundaries

Date: 2026-10-21.
Status: accepted target direction from the owner's draft and decisions; not implemented.
Complements ADR 0005 without changing existing API contracts.

## Context

The target now includes chat, RAG, note editing, task extraction, deterministic
planning/replanning, confirmed actions, bounded automatic creates, personal instructions
and opt-in proactive work. Operator-offered models and user-owned API connections
are required. Provider choice must not redesign application tools. The earlier
Groq-specific baseline is superseded; model examples are not verified contracts.

## Decision

- Keep one logical agent in the modular monolith. Select LangGraph with PostgreSQL
  checkpointing as the target for multi-step execution, pause/resume and cancellation.
  Ports/DTOs stay framework-neutral; framework/SDK types stay in infrastructure/composition.
- Checkpoints own continuity, not authorization or commit truth. Exact proposals and
  execution records own confirmation/idempotency under ADR 0005; normal services own
  writes. Resuming a graph node revalidates permissions/versions and cannot replay effects.
- Search owns chunks/hybrid retrieval and the web-search application port. Separate
  integrations implement LLM/embedding/search adapters. Missing local evidence permits
  labeled general knowledge and bounded web search, never invented private facts.
- Calendar owns interval/conflict truth; tasks owns task state and a deterministic
  planning application service. No new microservice or LLM feasibility check. Consider
  OR-Tools only when concrete constraints justify its dependency.
- General replanning keeps personal appointments and official occurrences fixed.
  Confirmed multi-action plans and execution outcomes commit atomically after source,
  version and availability revalidation. Failed preconditions apply nothing.
- Support operator models and encrypted owner-only API credentials. Keys never enter
  prompts/checkpoints/client responses. Validate model features per adapter; no
  unrestricted URL/plugin system or silent provider/credential fallback.
- Personal assistant instructions are editable settings below immutable authorization
  policy; hard planning constraints remain structured/versioned.
- AI use implies the selected processing policy, not write permission. Chats expire
  after 30 days of user-message inactivity; content-free activity lasts 30 days.
  Minimal replay protection remains independent of chat deletion.

## Consequences

LangGraph/checkpoints solve resumable orchestration but add framework/schema lifecycle
complexity. Prove Python 3.14/lockfile compatibility before installation. Test restart
and replay on fakes. No dependency, migration, secret storage, external call or
deployment is implemented by this specification change.

BYOK needs encryption-key management, owner isolation and disconnect handling. Web
search needs bounded egress/untrusted-result handling. Exact vendor/search contracts,
account budgets and package versions are verified in their stages, not invented here.

References: [product specification](../product/ai.md), [AI architecture](../architecture/ai.md),
[tool contracts](../development/ai-tool-contracts.md),
[decisions](../product/open-questions.md).
