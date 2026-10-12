# Ukladen Documentation Index

Updated: 2026-10-12.

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
- [Workspace](architecture/workspace.md): planned pages, organization, databases and views.
- [AI](architecture/ai.md): planned tools, confirmed actions, retrieval and provider boundaries.
- [Frontend](architecture/frontend.md): existing shell and target responsibilities.
- [Infrastructure](architecture/infrastructure.md): actual processes/storage/exposure.
- [ADR 0001](adr/0001-use-seaweedfs.md): local object storage.
- [ADR 0002](adr/0002-use-opaque-browser-sessions.md): browser authentication.
- [ADR 0003](adr/0003-use-cloudflare-tunnel-for-home-hosting.md): home hosting.
- [ADR 0004](adr/0004-keep-workspace-organization-optional.md): optional user organization.
- [ADR 0005](adr/0005-support-scoped-ai-action-permissions.md): confirmed/scoped automatic AI actions.

## Current implementation guides

- [Local development](development/local-development.md).
- [Auth email delivery](development/auth-email.md).
- [User profile](development/user-profile.md) and [avatar](development/user-avatar.md).
- [Academic profile](development/academic-profile.md).
- [Public university reads](development/university-api.md).
- [Official schedule](development/schedule.md).
- [Personal calendar](development/calendar.md).
- [Notes and page hierarchy](development/notes.md).
- [Diagnostics](development/logging.md).
- [Home-server deployment](deployment/home-server.md).

These guides document existing behavior. Dated verification is evidence of that
implementation task, not a guarantee that its checks were rerun during a later edit.

## IIS evidence and future integration

- [Original investigation](integrations/bsuir-iis-investigation.md): historical evidence.
- [Public contract](integrations/bsuir-iis-public-api.md): verified requests and limitations.
- [Deep integration roadmap](integrations/bsuir-iis-roadmap.md): private capability gates.
- [Sanitized fixture notes](../apps/backend/tests/fixtures/bsuir/README.md).

## Updating documentation

Keep requirements in product documents, ownership in architecture documents and
implemented DTOs/operations in development guides. Use links rather than duplicating
whole specifications. [Root overview](../overview.md) is a navigation entry.

Every new capability must say whether it is implemented, planned or unverified.
An empty package, infrastructure extension or fake adapter is not implementation.
Record owner decisions in the register and major boundary changes in an ADR.
Verify local links and status consistency before committing documentation changes.
