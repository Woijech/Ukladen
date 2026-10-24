# AI, Retrieval and Application Tools

Updated: 2026-10-24.
Status: AI-01 is complete within its offline scope, using a fake-only LangChain harness with neutral DTOs, typed
synthetic tools, review pauses and per-invocation limits. Owned persistence adapters
and preserving Alembic revisions are natively tested on disposable PostgreSQL; no application
database migration has been applied. The default-disabled [offline API](../development/ai-api.md)
adds authenticated chats/runs, admission, accounting, cancellation and deletion.
Bounded retries/deadlines and conservative overdue-run reconciliation are implemented;
see [execution and recovery limits](../development/ai-api.md#execution-deadlines-and-recovery).
Thirty-day physical cleanup and minimal replay/committed-context receipts are implemented;
the [retention contract](../development/ai-api.md#physical-retention-and-replay-protection)
defines the independent clocks and maintenance-only setting. Receipts cannot grant write authority.
An optional [OpenRouter adapter/catalog and encrypted personal connections](../development/ai-connections.md)
are implemented locally under AI-02; application migration and live account activation
remain pending. [AI-03 source tools](../development/ai-03.md) implement authorized
lexical search, page/material reads and calendar/database queries. Semantic retrieval,
write tools and product AI UI are not implemented. See the
[offline harness](../development/ai-setup.md#a1-implemented-offline-harness) and
[final verification](../development/ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24).
The [persistence guide](../development/ai-persistence.md) records the tested internal schema,
owner checks, short transactions and deletion boundaries.
Materials/extraction and basic lexical search are implemented separately;
see [P-08 contracts](../development/materials.md). They do not implement chunks,
embeddings, model tools or RAG. pgvector infrastructure alone is not retrieval.

## 1. Product responsibilities

Support workspace/calendar questions, content search, summaries grounded in selected
pages/materials, explanations of imported academic information and proposed changes.
AI must recognize that subjects/collections are optional and must never create an
academic hierarchy just because two events share a source subject label.

The owner confirmed reading/help, recommendations, confirmed execution and explicitly
permitted automatic actions. Deliver read-only tools/recommendations first, confirmed
writes next, then scoped automatic execution. RAG follows extraction/indexing.
Search or a calendar question must not mutate user data.

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

LLM, embedding and web-search providers are separate adapters under `app/integrations`.
The owner selected provider-neutral tools, an operator model catalog and user-owned
API connections. No particular LLM provider/model is required; the old Groq baseline
is superseded. CPU E5-small remains an embedding implementation candidate pending
runtime proof. The scripted offline model remains the default; the optional OpenRouter adapter is
implemented but unactivated. Other real adapters are not implemented.
Domain/application contracts must
not depend on SDK/framework response types. Streaming/cancellation is required target
behavior, never permission to execute incomplete or unconfirmed tool arguments.

[ADR 0009](../adr/0009-specify-provider-neutral-ai-orchestration.md) selects one logical
LangChain create_agent agent on LangGraph with PostgreSQL checkpoints behind neutral
ports. Use the ready-made model/tool loop, typed tools and HumanInTheLoopMiddleware;
do not build a parallel tool loop or custom graph without demonstrated need.
Checkpoints support pause/resume; normal services/execution records own authorization,
idempotency and atomic commits. Edited write arguments need a fresh proposal and
confirmation; middleware approval batches do not provide transaction atomicity.
Python 3.14.4 framework compatibility was proved in AI-01 step 2, including the
required websockets 17.1 to 16.1.1 replacement. No multi-agent subsystem
or separate AI/planning microservice is selected.

## 3. Planned tool capabilities

The read subset is implemented through [AI-03](../development/ai-03.md). Remaining
rows describe target capabilities, not existing tools.

| Capability | Required slice | Side effects |
| --- | --- | --- |
| Read resolved calendar and source freshness | Existing calendar | None |
| Read/search authorized pages and backlinks | Notes/relations/search | None |
| Query records/views/properties | Workspace | None |
| Read tasks and deadlines | Tasks | None |
| Query free slots/conflicts and propose feasible task sessions | P-06 calendar/task planning | None |
| Read permitted IIS context/sync state | Verified public integration; private account tools deferred | None |
| Retrieve cited material chunks | Materials/search | None |
| Search public web after insufficient local evidence | Bounded search adapter; AI-11 | External read only |
| Propose page/task/event/reminder changes | Implemented target service and action policy | Proposal only |
| Apply confirmed change | Same service as manual editing | Explicit, version-checked mutation |
| Apply an explicitly permitted automatic change | Implemented target service and scoped owner grant | Bounded, version-checked and recorded mutation |

Register only capabilities whose application services exist. Every tool has a
typed input/output schema, ownership context, result limits, timeout and declared
read/write behavior. Derive user identity server-side; arguments cannot impersonate
another user. Business errors are structured, sanitized outcomes.

## 4. Write proposal and execution

[ADR 0005](../adr/0005-support-scoped-ai-action-permissions.md) records two write
paths: exact confirmation or an explicit matching automatic-action permission.
The delegated initial automatic allowlist is new-page and new-task creation in
selected scopes; task tools require implemented task services. Concrete per-grant
limits/expiry/triggers remain mandatory execution inputs under Q-04a.
The model cannot select unrestricted execution as a mode on its own.

### Confirmed execution

1. Build a proposal with operation, exact targets/parameters and expected versions.
2. Present its effects, including calendar time/availability and destructive changes.
3. Record confirmation of that specific proposal by its owner.
4. Recheck ownership, versions and relevant source state before execution.
5. Execute through normal services and persist the outcome after commit.

Changing proposal parameters invalidates its confirmation. A stale target does not
silently receive a rewritten action.

### Scoped automatic execution

A planned owner-issued `AIActionGrant` identifies allowed operations, target scope,
validity, revocation state and applicable limits. Grant creation/change/revocation
requires normal user authentication and CSRF; a model/tool/content cannot grant it.
Store authoritative grants and execution records in PostgreSQL, not only Redis.

The selected policy permits new-page/task creates only through a matching owner grant;
existing edits, event/session moves and deletes remain confirmed operations. The
policy itself is not an actual grant. A grant alone does not create a recurring job
or authorize an unspecified trigger. Personal instructions cannot create a grant.

Before each automatic execution, validate the active owner, matching nonexpired grant,
operation/target/parameter limits and expected versions. Out-of-scope writes require
confirmation rather than silently broadening the grant. Serialize authorization and
revocation with the mutation so a queued job cannot reuse a revoked permission.

### Shared execution guarantees

Use a persisted owner-scoped idempotency key
so retries do not create duplicate events/tasks. Redis alone cannot retain the
canonical execution record. Multi-action plans and their outcomes commit atomically
in one shared database transaction. Revalidate current sources, target/preference
versions and full availability under serialization against concurrent busy-event
changes. Any stale/conflicting precondition applies nothing and requires a new
preview/confirmation. Do not claim atomicity without that implemented transaction.

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

For workspace questions retrieve local evidence first. If insufficient, disclose it
and distinguish general model knowledge from cited public web results. The web-search
port is search-owned; its adapter accepts minimal query terms and returns bounded
public results. Failed/unauthorized reads are not empty searches. External fallback
cannot invent private task/calendar facts, broaden explicit source-only scope or
silently switch model credentials. Retrieved pages remain untrusted content.

## 6. Trust, privacy and observability

Page text, retrieved files, IIS notes and model-generated tool arguments are data,
not authorization. Instructions embedded in those sources cannot grant tool access,
change owner identity or bypass confirmation. Validate every tool invocation.

Do not send auth/IIS credentials, cookies or unrelated private records to providers.
Using AI is the selected agreement to transmit relevant request/source context without
per-read dialogs; it does not authorize writes or unsolicited background work. Chats
and content-bearing checkpoints expire 30 days after the last user message; content-free
activity lasts 30 days from each event. Preferences and committed business objects
have independent lifecycles. Minimal replay protection must survive content cleanup.
Verify provider/account limits, billing/data terms and secret handling before
enabling real traffic. Logs contain safe tool names/outcomes and
correlation metadata, not full prompts, content or credentials by default.

Persist AI session/message ownership and cancellation/action state where required.
Ordinary request/worker correlation reuses existing structured diagnostics.

## 7. Acceptance checks

- A user's query cannot retrieve another user's page, record or material chunk.
- Prompt injection in a note cannot trigger an unauthorized write.
- Read-only requests perform no mutation.
- Execution requires matching confirmation or a valid scoped grant, plus owner,
  expected versions and durable idempotency.
- Expired/revoked/out-of-scope grants reject automatic writes; a queued retry cannot
  broaden permissions, ignore changed versions or duplicate completed work.
- Provider/tool failures preserve data and return actionable sanitized status.
- Answers cite supporting records and retain calendar freshness warnings.
- Fakes exercise orchestration and schemas without real provider/network calls.

See [roadmap](../development/implementation-roadmap.md) and
[open decisions](../product/open-questions.md) before starting this phase.

## 8. Planned delivery and analytics

The [AI product specification](../product/ai.md) owns the editable scenario catalog
and owner-only usage page requirements. The [implementation plan](../development/ai-implementation-plan.md)
defines staged ports, durable usage accounting, chat, indexing and confirmed/automatic
actions; [the setup runbook](../development/ai-setup.md) defines connection gates.
The AI-00 specification/acceptance data and offline AI-01 foundation are complete.
Owned offline runtime/usage persistence and chat/run endpoints are implemented;
the optional OpenRouter adapter and AI-03 read tools are implemented but unactivated;
write tools and product usage-summary endpoints remain not implemented.
`ai` owns implemented conversation/run/tool usage metadata and planned action metadata;
`search` owns derived retrieval/index jobs. Existing safe logs remain operator
diagnostics, not a source of prompts or cross-user product analytics.

## 9. Planning, settings and credentials

Calendar application services own occupied/free intervals and conflicts. A task
application planning service owns deterministic constraints/optimization inside the
monolith, using independent typed tasks. Checkboxes/database rows do not silently
become tasks. LLM estimates are labeled proposals, not completion/duration truth.
Use explicit work windows and editable 45/15-minute session/break defaults. General
replanning moves unprotected task sessions only; other personal events require a
direct request. Stale/missing official coverage allows conditional previews only;
applying affected plans waits for successful freshness/coverage revalidation.

An editable personal instructions field guides style/preferences below server policy.
Hard scheduling constraints remain structured/versioned; ambiguous free text cannot
override them. Proactive work is opt-in, bounded and uses existing Celery/in-app
delivery. Skip unchanged/non-actionable work and recheck settings on queued execution.

Operator keys are consumer-scoped deployment secrets. Personal supported API connections
require authenticated owner-only encrypted storage with a deployment-managed encryption
key, masking and disconnect/revocation. The credential resolver exposes secrets only
to the selected adapter consumer; prompts, checkpoints, client responses and analytics
receive no plaintext secrets. Arbitrary client base URLs are not a provider interface.
API/worker model consumers are explicitly configured; indexing workers do not inherit
unrelated LLM/search credentials. Exact storage/rotation and package contracts are
verified in AI-02 before activation. AI-01 proved only the offline framework/runtime;
AI-02 now implements encrypted credential storage/rotation and the OpenRouter
contract, with disabled profiles and pending live account verification. See
[connection limits and activation](../development/ai-connections.md).
