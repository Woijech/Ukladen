# Ukladen Documentation Index

Updated: 2026-10-24.

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
- [Frontend](architecture/frontend.md): authentication, weekly calendar, session isolation and timezone behavior.
- [Brand exports](../assets/branding/README.md): approved Ukladen logo files and reuse in product screens.
- [Infrastructure](architecture/infrastructure.md): actual processes/storage/exposure.
- [ADR 0001](adr/0001-use-seaweedfs.md): local object storage.
- [ADR 0002](adr/0002-use-opaque-browser-sessions.md): browser authentication.
- [ADR 0003](adr/0003-use-cloudflare-tunnel-for-home-hosting.md): home hosting.
- [ADR 0004](adr/0004-keep-workspace-organization-optional.md): optional user organization.
- [ADR 0005](adr/0005-support-scoped-ai-action-permissions.md): confirmed/scoped automatic AI actions.
- [ADR 0006](adr/0006-use-versioned-page-block-documents.md): notes block document schema and preserving migration.
- [ADR 0007](adr/0007-use-page-backed-database-records.md): database record ownership, schema versions and recovery.
- [ADR 0009](adr/0009-specify-provider-neutral-ai-orchestration.md): provider-neutral AI orchestration, credentials and deterministic planning boundaries.

## Current implementation guides

- [Local development](development/local-development.md).
- [Environment reference](development/environment.md): all implemented settings, sources and safe setup.
- [Auth email delivery](development/auth-email.md).
- [Google sign-in, registration completion and account linking](development/google-auth.md).
- [ADR 0008: completed registration](adr/0008-require-completed-registration.md).
- [User profile](development/user-profile.md) and [avatar](development/user-avatar.md).
- [Academic profile](development/academic-profile.md).
- [Public university reads](development/university-api.md).
- [Official schedule](development/schedule.md).
- [Personal calendar](development/calendar.md).
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

## Planned AI delivery

- [AI product specification](product/ai.md): owner-agreed chat, knowledge, planning, actions, provider choices and lifecycle.
- [AI implementation plan](development/ai-implementation-plan.md): AI-00 through AI-12, dependencies and acceptance gates.
- [AI-01 execution steps](development/ai-01-execution-plan.md): individually approved scopes, deliverables and verification.
- [AI tool contracts](development/ai-tool-contracts.md): capabilities, typed boundaries, budgets and synthetic acceptance data.
- [AI setup runbook](development/ai-setup.md): staged operator/BYOK providers, embeddings, web search and activation gates.
- [AI persistence](development/ai-persistence.md): schema, owner checks, transaction boundaries and migration impact; tested on disposable data, unapplied to the app.
- [Offline AI API](development/ai-api.md): default-disabled fake chats/runs, idempotency, cancellation, accounting, bounded recovery, physical retention and minimal replay/context markers.

AI-00 and the AI-01 internal offline harness are delivered; see the setup runbook for
its tested scope. Owned persistence adapters/migration are tested on disposable data,
unapplied to the app. A default-disabled fake chat/run API and accounting are implemented.
Real providers, retrieval, actions, planning and usage analytics UI
remain pending. Plans do not authorize later changes/deployment.

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
