# AI, Retrieval and Application Tools

Updated: 2026-10-12.
Status: not implemented. `ai`, `search`, `materials`, LLM and embedding boundaries
currently contain package markers; pgvector infrastructure is available, not RAG.

## 1. Product responsibilities

Support workspace/calendar questions, content search, summaries grounded in selected
pages/materials, explanations of imported academic information and proposed changes.
AI must recognize that subjects/collections are optional and must never create an
academic hierarchy just because two events share a source subject label.

Implement read-only tools first, confirmed writes second and material-grounded RAG
after extraction/indexing. Search or a calendar question must not mutate user data.

## 2. Boundaries

```text
Authenticated user -> AI application orchestrator -> provider-neutral LLM adapter
                                     |
                                     v
                              authorized tool registry
                                     |
                 calendar / notes / workspace / tasks / search / academics
```

AI does not receive SQL access, ORM models, a shell, raw storage credentials or
an unrestricted IIS HTTP client. Tool adapters call application interfaces; normal
services own validation, transactions, permissions and concurrency checks.

LLM and embedding providers are separate adapters under `app/integrations`. No
provider, model or budget has been selected. Domain/application contracts must
not depend on one SDK's response types. Streaming/cancellation is a later transport
decision, not an excuse to leak partially confirmed mutations.

## 3. Planned tool capabilities

Names are illustrative application capabilities, not implemented APIs.

| Capability | Required slice | Side effects |
| --- | --- | --- |
| Read resolved calendar and source freshness | Existing calendar | None |
| Read/search authorized pages and backlinks | Notes/relations/search | None |
| Query records/views/properties | Workspace | None |
| Read tasks and deadlines | Tasks | None |
| Query free slots/conflicts | Calendar availability | None |
| Read permitted IIS context/sync state | Public integration; private adapter only after verification | None |
| Retrieve cited material chunks | Materials/search | None |
| Propose page/task/event/property changes | Implemented target service and action policy | Proposal only |
| Apply confirmed change | Same service as manual editing | Explicit, version-checked mutation |

Register only capabilities whose application services exist. Every tool has a
typed input/output schema, ownership context, result limits, timeout and declared
read/write behavior. Derive user identity server-side; arguments cannot impersonate
another user. Business errors are structured, sanitized outcomes.

## 4. Write proposal and execution

The current architecture's action-confirmation requirement is retained. Q-04 tracks
whether the owner later wants bounded automatic actions.

1. Build a proposal with operation, exact targets/parameters and expected versions.
2. Present its effects, including calendar time/availability and destructive changes.
3. Record confirmation of that specific proposal by its owner.
4. Recheck ownership, versions and relevant source state before execution.
5. Execute through normal services and persist the outcome after commit.

Changing proposal parameters invalidates its confirmation. A stale target does not
silently receive a rewritten action. Use a persisted owner-scoped idempotency key
so retries do not create duplicate events/tasks. Redis alone cannot retain the
canonical execution record. Multi-action plans must declare transactional scope
and partial-failure behavior; do not pretend unrelated services form one atomic
operation without an actual transaction strategy.

IIS write-back is outside the verified integration and initial AI scope. A proposed
workspace event is a local change, not a university timetable edit.

## 5. Retrieval and indexing

Pipeline: authorized material/page content -> extraction/normalization -> versioned
chunks -> embeddings -> PostgreSQL/pgvector -> permission-filtered retrieval.

Every chunk carries owner, source type/ID, content version and source location.
Indexes are derived; canonical documents/material metadata remain in their modules.
Edits mark old indexed versions stale. Trash/deletion/revoked access must prevent
retrieval immediately, even if asynchronous index cleanup has not run yet.

Use metadata/ownership filters before any content enters the LLM request. Cite
actual retrieved page/material locations and event/source references; separate
source facts from model suggestions. No fabricated citations, complete-source
claims or confident free-time claims from missing/stale schedule coverage.

Document extraction and embedding jobs use Celery, idempotent source/version keys
and bounded retry policies. A failed job retains source content and reports status.
External links need a separately constrained fetch contract; arbitrary user URLs
must not give the worker access to internal service endpoints.

## 6. Trust, privacy and observability

Page text, retrieved files, IIS notes and model-generated tool arguments are data,
not authorization. Instructions embedded in those sources cannot grant tool access,
change owner identity or bypass confirmation. Validate every tool invocation.

Do not send auth/IIS credentials, cookies or unrelated private records to providers.
Resolve provider data sharing, content retention, supported limits and costs before
enabling real model traffic under Q-04. Logs contain safe tool names/outcomes and
correlation metadata, not full prompts, content or credentials by default.

Persist AI session/message ownership and cancellation/action state where required.
Ordinary request/worker correlation reuses existing structured diagnostics.

## 7. Acceptance checks

- A user's query cannot retrieve another user's page, record or material chunk.
- Prompt injection in a note cannot trigger an unauthorized write.
- Read-only requests perform no mutation.
- Execution requires matching confirmation, owner, versions and idempotency state.
- Provider/tool failures preserve data and return actionable sanitized status.
- Answers cite supporting records and retain calendar freshness warnings.
- Fakes exercise orchestration and schemas without real provider/network calls.

See [roadmap](../development/implementation-roadmap.md) and
[open decisions](../product/open-questions.md) before starting this phase.
