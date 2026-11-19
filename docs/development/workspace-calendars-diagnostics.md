# Personal calendars, keyboard layers and AI inspection

Date: 2026-11-19. This change implements the supplied workspace/diagnostics request.
No deployment, real provider call or production migration is part of verification.

## Existing-system audit and decisions

- Shared dialogs already use native `dialog.showModal()`, focus containment, Escape
  cancellation and focus restoration. Event, note, task, profile and database drafts
  already have save guards. The remaining work is event-inspector Escape, menu event
  propagation/IME guards, and preserving the upper layer rather than closing a
  calendar sidebar underneath it. Reuse `Modal`; no independent layer registry.
- `CalendarViewService` and `workspace_calendar_views` are saved compositions of
  sources/collections/tags. They cannot represent exactly one editable calendar for
  a personal event. Collections/tags remain nonexclusive organization; views and
  visibility remain display-only. A small calendar-owned entity is appropriate.
- IIS `lessonTypeAbbrev` is normalized to `lesson_type`. Committed BSUIR fixtures
  contain `ЛК` and `ЛР`; the UI compares exact `ЛК`, `ЛР`, `ПЗ` values. Every other
  value, including null, is `other`. Titles and personal overrides are not classifiers.
- Migration `0042_minsk_timezone` already makes real profiles Minsk-based. Retain
  the timezone-aware conversion engine and DST tests, remove timezone controls and
  repeated labels. Event rooms/meeting addresses are retained. Diagnostics format
  civil timestamps explicitly with Europe/Minsk rather than device timezone.
- Existing usage aggregation already fills zero days, separates fake usage and
  preserves unknown counts/costs. Reuse it for the ordinary dashboard and the
  operator chart. Detailed inspection stays behind existing backend operator grants.
- Existing opt-in diagnostics capture final application input after grounding and
  personal instructions. Extend these events; do not reconstruct old prompts or
  create another tracing system.

## Calendar contracts and migration

Apply `0043_personal_calendars` after `0042_minsk_timezone`. It adds
`personal_calendars`, `calendar_visibility`, and nullable
`personal_calendar_events.calendar_id`. Null is the built-in “Личные события”
calendar, so existing events require no reassignment. A composite foreign key
`(calendar_id, user_id)` prevents cross-owner assignments even outside the API.

All routes below require an active session, return `Cache-Control: no-store`,
use Pydantic DTOs and require existing CSRF checks for writes:

| Route | Contract |
| --- | --- |
| `GET /api/v1/calendar/calendars` | `{items: [{id, name, color, version, created_at, updated_at}]}` |
| `POST /api/v1/calendar/calendars` | `{name, color}`; 201 |
| `PATCH /api/v1/calendar/calendars/{id}` | `{name, color, expected_version}` |
| `DELETE /api/v1/calendar/calendars/{id}` | `{expected_version}`; 204; move events to built-in calendar |
| `GET /api/v1/calendar/visibility` | `{version, default_visible, hidden_calendar_ids, hidden_lesson_types}` |
| `PUT /api/v1/calendar/visibility` | Same shape; optimistic version, incremented response |

Names are trimmed, 1–100 characters, without control characters; colors are RGB
hex values. At most 100 user calendars. Foreign/missing calendar IDs return 404;
stale versions return 409. Deletion takes the active-owner lock, reassigns members
and increments affected event versions in the same transaction, then removes the
calendar and any obsolete hidden-calendar reference. Events and relations survive.
Downgrade refuses retained calendar/preference data instead of silently losing it.

Personal-event create/patch and resolved responses accept/return `calendar_id`.
The editor defaults to the built-in calendar and can change an existing assignment.
Colors decorate event edges, without using arbitrary colors for body text. Visibility
updates optimistically and rolls back on API errors. Group toggles batch changes.
Calendar reads and availability never consult these display preferences; hidden
training/work/classes remain actual busy time. Existing saved view APIs are unchanged.
AI event actions retain their previous confirmed payload/preview contract and do not
acquire an implicit calendar reassignment capability.

## Ordinary AI usage and help

The ordinary screen shows request/input/output/total token counts, 7/30-day daily
bars, refresh and plan limits. Unknown tokens remain unknown; partial known counts
and unknown costs are disclosed together. A cost indicator appears only when the
attempts are priced and there are no unpriced external searches. Fake usage stays
separate. Technical tables/run journals belong to diagnostics, not this screen.

Chart days work with focus, hover and touch. Empty dates are zero-filled, existing
series remain while switching periods, reduced motion disables feedback animation.
On narrow/coarse-pointer screens, the chart scrolls within its own area and keeps
44px day targets. `HelpTooltip` uses the native popover layer for outside dismissal,
Escape and keyboard access, with viewport-bounded positioning and no new dependency.

## Operator trace and context

Existing backend `AI_DIAGNOSTIC_ADMIN_IDS` checks, owner scoping, explicit chat opt-in,
seven-day detailed retention, 30-day aggregate window and capture size limits stay
unchanged. Export remains the permitted owner's JSON report. No foreign-user access
or new capture permission is introduced.

New/extended capture events include:

- `run_started`: actual current user message and source-only state;
- `history_loaded`: actual history fetch duration and message count;
- `source_context`: measured source refresh/tool-selection duration, references,
  result byte/item/source counts and placement; `source_analysis` holds captured
  analysis separately so a long body does not hide all metrics;
- `instructions`: actual construction duration, base/personal instruction sizes,
  permitted personal content and placement inside system (not a fictitious role);
- `model_input`: serialized characters/UTF-8 bytes and SHA-256 equality fingerprints
  for each disjoint part, plus individual schema sizes;
- `context_part`: separately bounded content for each nonempty final part;
- `model_request`: final application request including complete tool schemas,
  explicitly labelled as before provider serialization;
- `external_request`: identifies observed web-search attempts rather than assigning
  them a fictitious chat-model identity or external-service price;
- tool responses now retain the real call ID for matching against final tool-message
  parts in later model calls.

The dashboard combines stored attempt/tool intervals with these events. Missing
stage timing/content is marked unavailable. Per-model sections open on demand;
context and large results are collapsed. Byte composition bars and a detail table
never claim component token counts. Provider cache/reasoning totals remain separate
facts and are not added to input/output twice. Provider-wire time is shown only when
both transport events exist. Unknown external fees are explicitly excluded from a
complete-cost claim. Header/credential assignments and URL credentials are redacted,
including inside free-text captures; hidden reasoning remains excluded.

Local hints separate measured facts from hypotheses: largest parts, identical
fingerprints, successive byte growth and advertised tool count are measured.
Size thresholds (8KB system, 24KB history, 12KB schemas, 32KB results) are inspection
heuristics, not evidence that content is unnecessary or that bytes equal tokens.
Found references are distinguished from final system/tool-message content. Source
buttons use the existing authenticated source viewer and recheck current rights.
Old traces cannot supply new events; capture bounds can omit later details.

## Pipeline cost findings and optimization decision

Measured locally with `convert_to_openai_tool` and compact UTF-8 serialization,
without any provider call:

| Component | Bytes |
| --- | ---: |
| General source policy | 3,841 |
| General schemas, including web and confirmed actions (12 tools) | 17,464 |
| `propose_actions` alone | 10,654 |
| `query_database` schema | 1,215 |
| `preview_task_plan` schema | 1,028 |
| Existing calendar-only policy | 953 |
| Existing `get_calendar_events` schema | 632 |

The general static baseline is about 21KB before personal instructions, history,
results or provider framing. About 61% of schema bytes belong to confirmed actions.
Each subsequent model call can resend these parts, retained history and refreshed
results; the existing source refresh budget permits up to 49,152 bytes. Complete
source analyses may also appear in system context. These explain plausible high
input usage, but do not establish the token count or billing of a particular live
run. Tokenization, provider serialization and cache discounts differ.

The existing conservative calendar fast path already narrows tools/policy and
removes completed calendar tools. Preserve it and source revalidation. Do not remove
required evidence or aggressively truncate histories. A future explicit read-only
tool mode could omit the large action schema, but broad automatic inference could
break requested actions; no such behavior change is justified by this synthetic
measurement alone. Inspect real permitted traces before changing this contract.

## Verification

Executed locally:

- Frontend ESLint, TypeScript and production build passed. The build ran outside
  the sandbox because its nested TypeScript process returned empty captured stdout
  inside the sandbox; the application/configuration was not changed for that issue.
- All 352 Playwright scenarios passed. After the final directory-outage guard,
  all four calendar scenarios passed again, including the additional outage case
  (353 distinct browser scenarios covered across those runs). Light/dark contrast,
  desktop/mobile overflow, native popover Escape, nested dialogs, draft guards,
  provider-unknown values and captured-text safety are exercised with mocked APIs.
- Ruff and Pyright over `src tests alembic benchmarks` passed. The default unscoped
  Pyright invocation also includes optional `evaluations`; it cannot resolve four
  imports from the uninstalled `deepeval` extra. No optional evaluation/provider
  dependency was installed to hide that environment limitation.
- `docker compose config --quiet` and `git diff --check` passed.

The final complete backend pytest run passed **2,126 tests, with 3 skips**, in the
isolated PostgreSQL 18/pgvector and Redis environment. This includes native migrations,
Alembic model-diff checks, safe downgrades, ownership, CSRF, calendar CRUD/assignment,
event preservation, AI-confirmation compatibility, capture permissions/retention and
secret redaction. The final explicit null/zero reasoning-token redaction assertion
was also checked in the focused diagnostics/accounting/tool-selection run: 20 passed.

Earlier runs exposed and resolved the new-field AI-action regression and migration
fixtures that assumed the previous table set/ORM columns. Parser failures in the
initial container run were environment failures: switching from the bare interpreter
to the backend virtual environment supplied the isolated parser dependencies. The
final full run has no failures.
All integration data lives in disposable PostgreSQL 18/pgvector and Redis containers;
service containers, real databases and provider keys are untouched. Native S3 and
real-provider/embedding calls are not part of this follow-up. Existing Python 3.14
Pydantic-v1 compatibility warnings from dependencies are not suppressed.
