# Deep BSUIR IIS Integration

Updated: 2026-10-12.
Status: public read/schedule integration implemented within the verified contracts;
authenticated account integration and capabilities below are not implemented.
This roadmap is not evidence that a private endpoint exists.

## 1. Evidence and current coverage

Read the [original investigation](bsuir-iis-investigation.md),
[verified public contract](bsuir-iis-public-api.md),
[university API](../development/university-api.md) and
[schedule storage](../development/schedule.md) before modifying adapters.

The existing cookie-free public adapter covers group/teacher schedules, catalogues,
rooms, announcements, academic week and update hints. Academic profiles select
group/subgroup; Celery imports supported official occurrences and retains historical
facts. Calendar applies personal overrides without changing shared official data.

Source strings are metadata. No verified stable subject ID is present in public
lesson rows. Stable occurrence identity across arbitrary source changes is not
guaranteed. Last-update dates are not reliable monotonic change tokens.

## 2. Capability matrix

| Capability | Evidence / runtime status | Next action |
| --- | --- | --- |
| Public catalogues and group/teacher schedule reads | Verified; implemented | Preserve contracts; improve only with new evidence |
| Group schedule persistence, supported dated expansion and sync | Implemented | Preserve shared identities, source states and last valid data |
| Personal attendance/visibility/time overrides | Implemented in calendar | Keep user interpretation out of the source adapter |
| Exception/split/cancellation precedence | Contract incomplete; unsupported cases preserve last valid import | Obtain authoritative rules and sanitized examples before expansion changes |
| Rich teacher/room/announcement context in workspace | Public reads exist; workspace enrichment not implemented | Add explicit links/context without duplicate calendar occurrences |
| Authenticated student identity and enrollment | Contract unverified; not implemented | Verify login/consent/session lifecycle and account identity |
| Grades and academic progress | Candidate requirement; endpoint/payload unverified | Confirm owner need, then investigate read contract |
| Curriculum and student-specific course context | Candidate requirement; endpoint/payload unverified | Verify terminology, identifiers and periods |
| Attendance or student-specific lesson state | Candidate requirement; endpoint/payload unverified | Verify availability; do not confuse with local skipped state |
| Assignments, deadlines and course materials | Candidate requirement; endpoint/payload unverified | Verify existence, dates, resource access and permissions |
| Private announcements/messages | Candidate requirement; unverified | Confirm scope before handling additional private content |
| Write-back to IIS | Not requested as a defined capability; unverified and not implemented | Requires separate owner authorization and documented upstream mutation contract |

Private candidates are conditional targets under Q-02. Do not invent endpoint
names, authentication forms, permission scopes, fields or a successful student-data
import in documentation or code.

## 3. Adapter and application boundaries

Keep verified public reads independent of private account connection. Logging into
Ukladen or selecting a group must not implicitly log into IIS. A Google identity
is not an IIS student identity.

- `integrations/bsuir`: concrete external clients, validation, authentication/session
  handling and conversion to application-owned contracts.
- `academics`: academic selection/context and verified student-specific academic data
  when its slice exists.
- `schedule`: official dated facts and shared-source synchronization.
- `calendar`: the user's personal interpretation, not upstream writes.
- `notes`/`workspace`/`tasks`/`materials`: user-owned content and explicit imports/links.

Introduce a connected-account application boundary only when a verified capability
needs it. Public facts may be shared; private student data is owner-scoped and never
cached under a group-only key. Source provenance and last-success timestamps must
be retained. Do not create one table per guessed API response in advance.

If a required upstream contract is missing, define a narrow application port and
fake, add a clear TODO and report the missing evidence. A fake is not live integration.

## 4. Investigation gate for private capabilities

Before implementation, record:

1. The requested capability and authorized account/test context.
2. Official documentation or directly observed requests, method and parameters.
3. Authentication, consent, expiry, refresh/re-authentication and revocation behavior.
4. Sanitized responses including empty/error/pagination and access-denied cases.
5. Identity stability, update signals, rate limits and source terminology.
6. Which fields may enter storage, logs, search or an external AI provider.
7. Mapping to Ukladen-owned DTOs and explicit unsupported behavior.

Investigations must not access another person's account or commit credentials,
tokens, cookies, grades or identifiable private fixtures. A new endpoint is not
verified just because its name appears in a frontend bundle. No authenticated
investigation was performed by this documentation task.

## 5. Connection and synchronization targets

After a verified authentication contract exists, support explicit connect,
connection status, re-authentication and disconnect. Decide credential/token storage
and unlink retention before adding persistent secrets; use encrypted credential
storage with deployment-provided key management if the chosen flow requires it.
Never ask users for passwords until the actual supported flow is established.

Private background jobs run per owner/account, have bounded network timeouts,
idempotent writes and safe retries, and report source/connection health. Expired
credentials require re-authentication, not endless retry. No external network
operation holds a database transaction open.

Disconnect immediately stops new jobs and access through that account. Retention
versus purge of imported private records must be explicit; disconnect never deletes
unrelated pages, notes or personal events. Existing ephemeral Redis is not durable
credential storage or authoritative import state.

## 6. Bringing IIS data into the workspace

Imported academic facts retain source provenance. They do not automatically create
subject pages, combine lecture/lab notes, schedule work or convert ambiguous source
text into tasks. Offer explicit import/template/link actions instead.

If a verified assignment exposes a due date, a user-approved mapping may create or
update a linked task. Track source identity and user edits separately; retries must
not duplicate it, and a refresh must not overwrite a user-authored page body.

Source withdrawals leave understandable historical references. Ambiguous replacements
must be surfaced for review until stable IDs or verified reconciliation rules exist.
Calendar views, planning and AI carry freshness/unsupported warnings forward.

## 7. Delivery order and acceptance

1. Improve known public exception/identity rules only after evidence is available.
2. Investigate private account authentication and the owner's highest-priority capability.
3. Implement one read-only, owner-scoped private slice with a fake and adapter tests.
4. Add bounded background refresh/status/disconnect for that verified slice.
5. Add explicit workspace import/linking, then further capabilities individually.

Tests verify owner isolation, expired/revoked connection handling, sync retry/rollback,
no secret logging, preserved user content and unsupported capability reporting.
Normal checks use HTTP mocks and sanitized fixtures, never a real IIS login.

See [open decisions](../product/open-questions.md) and
[implementation roadmap](../development/implementation-roadmap.md).
