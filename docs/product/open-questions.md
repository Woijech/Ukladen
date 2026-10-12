# Product Decisions and Open Questions

Updated: 2026-10-12.
Status: decision register. Proposed defaults are not owner-confirmed requirements.
An agent may implement independent confirmed scope, but must resolve a relevant
open decision before committing an incompatible schema, integration or behavior.

## Confirmed direction

- Combine a freely organized workspace and calendar with AI and deep IIS integration.
- Standalone notes/pages must work without an event or academic context.
- Organization and links are user-controlled; lecture/lab grouping is never automatic.
- Keep official facts separate from personal interpretation; preserve the existing backend.
- This task edits documentation only; it does not authorize implementation of a new phase.
- Technical documentation/code is English; initial product text may be Russian.

The [ADR](../adr/0004-keep-workspace-organization-optional.md) records this direction.

## Decisions to clarify

| ID | Question | Proposed default | What depends on it |
| --- | --- | --- | --- |
| Q-01 | Does the target require blocks, nested pages and user-defined databases, or only notes/calendar links? Which database features belong in the first release? | Full workspace is the target; deliver standalone text pages first, then blocks and basic typed databases. Formulas/rollups later. | Content contract, database ownership, editor integration and release scope |
| Q-02 | Which private IIS capabilities are required and actually available: grades, curriculum, attendance, assignments, materials? Is write-back ever wanted? | Rich public integration plus a separately connected private account, read-only first. Every private capability remains unverified until investigated. | Adapter interfaces, private storage, authorization and sync jobs |
| Q-03 | Personal spaces first, or shared spaces and concurrent editing immediately? | Personal ownership first; sharing and real-time collaboration later. | Ownership model, access control, transactions and document operations |
| Q-04 | Must AI confirm every mutation, or may users authorize bounded automatic actions? Which provider, budget and data sharing policy apply? | Read-only tools first; exact action preview and explicit confirmation for every write. Provider-neutral adapters; no provider selected. | Tool authorization, action state, costs and external content transfer |
| Q-05 | Which calendar features are essential first: all-day entries, recurring personal events, multiple calendars, database dates, external providers? What should be busy? | Existing timed events first; date labels/deadlines are nonblocking. All-day/recurrence are separate contracts; no Google/Microsoft sync assumed. | Date DTOs, recurrence/exception model, view bindings and availability |
| Q-06 | How should trash, nested-page deletion, history, permanent purge and export behave? | Recoverable trash; no silent child/content destruction. Exact subtree/restore policy decided before hierarchy implementation. | Foreign keys, cleanup jobs, relation visibility and restore semantics |
| Q-07 | Are tasks typed planning objects, customizable database records, or both with an explicit binding? | Keep typed tasks for planning; ordinary database records do not acquire task semantics automatically. | Task API, property bindings, deadlines and AI tools |
| Q-08 | Which block types and editor document format are required? Must external editor JSON be portable? | Text, headings, lists/checklists and links first; attachments after materials. Select and version the transport schema before block persistence. | Validation, migrations, rendering, history and exports |
| Q-09 | Should subjects be a user-created aid, an optional template or a separately imported catalogue? | Defer subjects; offer optional academic templates later. Never merge by label or require `subject_id`. | Subject module and academic-to-workspace relations |
| Q-10 | How should upstream replacements be reconciled when stable IDs are missing? | Preserve historical references and surface uncertain replacements; explicit user relinking. | Import matching, local overrides, references and notifications |
| Q-11 | What are first-release limits and operational requirements? | Set explicit content/file/query limits per slice. No promise of unlimited storage or provider usage; deployment secrets and backup policy remain separate. | Uploads, indexing, quotas, observability and production readiness |

Q-01, Q-02 and Q-03 were presented to the owner during the documentation task.
Until answered, their proposed defaults remain provisional. Silence is not acceptance.

## How agents record answers

Record the owner's actual answer, its date and the affected requirements here.
Update the primary architecture/ADR if boundaries change, then affected requirement
and roadmap sections. Do not add a second conflicting product plan elsewhere.

An unverified external API is a different kind of unknown from a product preference:
owner intent cannot establish an endpoint or payload. Keep those capability rows
unverified until evidence, sanitized fixtures and adapter contract tests exist.

## Next decisions by implementation slice

- Standalone text pages: confirm the deliberately limited first slice, content limits
  and trash policy; no IIS account or collaboration dependency is required.
- Nested/block pages: Q-03, Q-06 and Q-08.
- Databases/calendar projection: Q-01, Q-05 and Q-07.
- AI writes: Q-04, including confirmation, idempotency and provider data policy.
- Authenticated IIS: Q-02 plus verified upstream authentication/capability contracts.
