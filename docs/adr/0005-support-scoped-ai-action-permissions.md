# ADR 0005: Support Scoped AI Action Permissions

Date: 2026-10-12.
Status: accepted target direction from the repository owner; not implemented.

## Context

The initial AI proposal required confirmation for every write. The owner clarified
that AI must support reading/help, recommendations, confirmed execution and explicitly
permitted automatic actions. The exact automatic action list and limits are not yet
defined. This is a product capability decision, not unrestricted execution consent.

## Decision

- Read/help and recommendation operations do not change workspace data.
- Writes without a matching automatic permission use exact proposals and confirmation.
- Automatic writes require an explicit owner-issued, persisted, revocable grant
  identifying allowed operations, target scope, validity and applicable limits.
- Before each execution, recheck the active owner, grant/confirmation, target versions
  and normal business rules. Missing/expired/revoked/out-of-scope grants do not execute.
- Tool arguments, retrieved content and the model cannot grant or widen permissions.
- Both execution paths use the same application services, durable idempotency and
  execution records. Existing auth/CSRF/ownership/transaction rules remain applicable.
- Implement reads/recommendations, confirmed writes and scoped automatic actions
  in successive slices. No automatic write is enabled before its permission contract.

## Consequences

The primary architecture, requirements and roadmap support both write authorization
paths. Details remain in Q-04a. No LLM provider or global allowlist is selected.
No scheduler, AI runtime, permission table or workspace mutation is implemented by
this documentation change. Private IIS remains future-only and outside current AI tools.

References: [AI architecture](../architecture/ai.md),
[decision register](../product/open-questions.md),
[implementation roadmap](../development/implementation-roadmap.md).
