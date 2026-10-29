# Ukladen Documentation Index

Updated: 2026-10-29.

## Contract and reading order

1. [Agent instructions](../AGENTS.md): mandatory development and commit workflow.
2. [System architecture](../SYSTEM_ARCHITECTURE.md): primary architecture contract.
3. [Product overview](product/overview.md): direction and implementation status.
4. [Workspace requirements](product/workspace.md): behaviors and acceptance cases.
5. [Decision register](product/open-questions.md): confirmed answers and remaining choices.
6. [Implementation roadmap](development/implementation-roadmap.md): backend slices/dependencies.
7. Relevant design, current implementation guide and code for the requested slice.

If specifications conflict, report the conflict and align them through an explicit
decision; do not guess which obsolete paragraph authorizes new functionality.
Planned contracts do not override the current implemented API silently.

## Architecture and decisions

- [Architecture overview](architecture/overview.md): actual module/runtime baseline.
- [Backend](architecture/backend.md): current backend contracts and verification.
- [Workspace](architecture/workspace.md): implemented pages, organization, user databases and table/calendar views.
- [AI](architecture/ai.md): planned tools, confirmed actions, retrieval and provider boundaries.
- [Frontend](architecture/frontend.md): shared workspace design, calendar/tasks, page and database editors, materials/search, session isolation and timezone behavior.
- [Brand exports](../assets/branding/README.md): approved Ukladen logo files and reuse in product screens.
- [Infrastructure](architecture/infrastructure.md): actual processes/storage/exposure.
- [ADR 0001](adr/0001-use-seaweedfs.md): local object storage.
- [ADR 0002](adr/0002-use-opaque-browser-sessions.md): browser authentication.
- [ADR 0003](adr/0003-use-cloudflare-tunnel-for-home-hosting.md): home hosting.
- [ADR 0004](adr/0004-keep-workspace-organization-optional.md): optional user organization.
- [ADR 0005](adr/0005-support-scoped-ai-action-permissions.md): confirmed/scoped automatic AI actions.
- [ADR 0006](adr/0006-use-versioned-page-block-documents.md): notes block document schema and preserving migration.
- [ADR 0007](adr/0007-use-page-backed-database-records.md): database record ownership, schema versions and recovery.
- [ADR 0008](adr/0008-require-completed-registration.md): completed registration before workspace access.
- [ADR 0009](adr/0009-specify-provider-neutral-ai-orchestration.md): provider-neutral AI orchestration, credentials and deterministic planning boundaries.

## Current implementation guides

- [Local development](development/local-development.md).
- [Environment reference](development/environment.md): all implemented settings, sources and safe setup.
- [Auth email delivery](development/auth-email.md).
- [Google sign-in, registration completion and account linking](development/google-auth.md).
- [User profile](development/user-profile.md) and [avatar](development/user-avatar.md).
- [Academic profile](development/academic-profile.md).
- [Public university reads](development/university-api.md).
- [Official schedule](development/schedule.md).
- [Personal calendar](development/calendar.md).
- [Calendar availability](development/calendar-availability.md): local read-only busy/free/conflict queries and explicit coverage uncertainty.
- [Tasks delivery contract](development/tasks.md): typed tasks, hierarchy, dependencies, provenance and page links.
- [Task sessions and planning](development/task-planning.md): weekly preferences, explicit work remainder, deterministic previews and atomic confirmed application.
- [Reminders and in-app notifications](development/reminders.md).
- [Materials, page attachments and basic search](development/materials.md).
- [Notes and page hierarchy](development/notes.md).
- [Workspace collections and tags](development/workspace.md).
- [Saved calendar views](development/calendar-views.md).
- [User databases delivery status](development/databases.md).
- [Page and calendar links](development/relations.md).
- [Diagnostics](development/logging.md).
- [Home-server deployment](deployment/home-server.md).

These guides document existing behavior. Dated verification is evidence of that
implementation task, not a guarantee that its checks were rerun during a later edit.

## AI implementation and planned delivery

- [AI product specification](product/ai.md): owner-agreed chat, knowledge, planning, actions, provider choices and lifecycle.
- [AI implementation plan](development/ai-implementation-plan.md): AI-00 through AI-12, dependencies and acceptance gates.
- [AI-01 execution steps](development/ai-01-execution-plan.md): individually approved scopes, deliverables and verification.
- [AI tool contracts](development/ai-tool-contracts.md): capabilities, typed boundaries, budgets and synthetic acceptance data.
- [Synthetic AI acceptance fixtures](../apps/backend/tests/fixtures/ai/README.md): versioned specification cases and their implementation boundary.
- [AI setup runbook](development/ai-setup.md): staged operator/BYOK providers, embeddings, web search and activation gates.
- [Prepared home AI activation](development/ai-activation.md): lifetime shared-key budget, personal-key separation and owner launch steps.
- [AI persistence](development/ai-persistence.md): schema, owner checks, transaction boundaries and migration impact; tested on disposable data, unapplied to the app.
- [AI-03 source reads](development/ai-03.md): read-only workspace/calendar/database tools, current evidence and structured source references; unactivated.
- [AI-04 chat/settings/usage](development/ai-04.md): local streaming, stored-state recovery, source inspection, instructions and owner usage; activation pending.
- [AI-05 CPU embeddings](development/ai-05.md): optional pinned ONNX runtime, disposable hardware proof and measured load limits; no production index.
- [AI-06 retrieval and full-source processing](development/ai-06.md): local versioned chunks, recoverable index, hybrid search, located sources and durable analyses; unactivated.
- [AI-07 confirmed actions](development/ai-07.md): immutable previews, atomic owner-confirmed batches and independent replay receipts; default-disabled and unactivated.
- [AI-09 release hardening](development/ai-09.md): agreed local scope, bilingual acceptance and separate live-model/activation gates.
- [AI-10 task planning](development/ai-10.md): local extraction, editable task proposals, work sessions/preferences and confirmed deterministic planning/replanning.
- [AI-11 web fallback](development/ai-11.md): local source-first chat fallback, bounded public search and external citations; unactivated.
- [AI-12 proactive reviews](development/ai-12.md): opt-in summaries, warnings, source scope and in-app delivery; unactivated.
- [AI model connections](development/ai-connections.md): optional OpenRouter catalog, restricted offerings, encrypted personal keys and AI-consumer-only secret setup; unactivated.
- [AI chat/run API](development/ai-api.md): default-disabled fake chats/runs, idempotency, cancellation, accounting, bounded recovery, physical retention and minimal replay/context markers.

AI-00 and the offline AI-01 foundation are complete; see the setup runbook and
[final verification](development/ai-01-execution-plan.md#13-final-ai-01-verification-2026-10-24)
for the tested scope. Owned persistence adapters/migrations are tested on disposable
data. The home database was subsequently prepared through revision 0040 with AI
flags off; see [prepared activation](development/ai-activation.md). The default-disabled fake API includes accounting,
bounded recovery, 30-day cleanup and minimal replay/context receipts.
The optional AI-02 OpenRouter adapter/catalog and encrypted credentials are
implemented locally but unactivated. AI-03 source tools and lexical grounding are
implemented locally. AI-04 chat/settings/usage UI/API is implemented locally.
AI-05 adds a locally verified optional CPU embedding runtime and synthetic hardware proof.
AI-06 adds local hybrid retrieval and durable complete-source processing.
AI-07 adds locally implemented confirmed actions. AI-08 is deferred indefinitely; AI-09 local hardening is complete; live-model acceptance remains pending. AI-10 implements task extraction and confirmed deterministic planning locally.
Real-model quality and activation remain pending. Plans do not authorize later changes/deployment.

## IIS contracts and future integration

- [Public contract](integrations/bsuir-iis-public-api.md): verified requests and limitations.
- [Deep integration roadmap](integrations/bsuir-iis-roadmap.md): private capability gates.
- [Sanitized fixture notes](../apps/backend/tests/fixtures/bsuir/README.md).

## Updating documentation

Keep requirements in product documents, ownership in architecture documents and
implemented DTOs/operations in development guides. Use links rather than duplicating
whole specifications. Keep reusable contracts and operating instructions here;
one-off audit reports and task handoffs belong in Git/chat history.

Every new capability must say whether it is implemented, planned or unverified.
An empty package, infrastructure extension or fake adapter is not implementation.
Record owner decisions in the register and major boundary changes in an ADR.
Verify local links and status consistency before committing documentation changes.
