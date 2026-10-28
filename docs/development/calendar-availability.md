# Calendar Availability Queries

Date: 2026-10-28.
Status: implemented locally, backend only. This is the read-only personal/official
interval subset of P-06/AI-10. Work blocks, saved work windows, planning and their
browser controls are not implemented. No application activation was performed.

## API

`POST /api/v1/calendar/availability` uses the existing completed-registration session,
CSRF/Origin and no-store rules. It changes no events, tasks or preferences. Reads
share one caller-owned PostgreSQL repeatable-read snapshot across calendar sources.

```json
{
  "starts_at": "2026-10-29T15:00:00+03:00",
  "ends_at": "2026-10-29T21:00:00+03:00",
  "windows": [
    {"starts_at": "2026-10-29T18:00:00+03:00", "ends_at": "2026-10-29T21:00:00+03:00"}
  ],
  "candidates": [
    {"starts_at": "2026-10-29T18:00:00+03:00", "ends_at": "2026-10-29T18:45:00+03:00"}
  ],
  "minimum_minutes": 15
}
```

All timestamps require explicit offsets; numeric epochs, date-only and naive
timestamps are rejected. Ends are exclusive and strictly later than starts.
Windows/candidates must be wholly inside the requested range. The existing calendar
limit of 366 local dates and an elapsed-range limit of 366 days apply. Each list is
bounded to 1024 intervals; minimum duration is a strict integer from 1 to 525600.
Unknown fields are rejected. Invalid input is 422.

The result contains:

- `occupied`: merged/clipped busy intervals for the complete requested range.
- `events`: individual busy event IDs, source IDs, titles, versions and times,
  without descriptions or owner IDs.
- `free`: the allowed windows minus the complete busy set, filtered by minimum
  elapsed duration. An absent/empty window list produces no free windows; it does
  not imply that the whole range is allowed work time.
- `conflicts`: one entry per candidate, with its zero-based `candidate_index` and
  overlapping event IDs. Touching endpoints do not conflict.
- `timezone`, existing source metadata and warnings, plus `verified` and `snapshot`.

Optional `exclude_personal_event_id` authorizes an owned personal event before
excluding its old interval, for checking a proposed edit. A missing/foreign event
is 404. It does not permit editing or ignoring an official occurrence. Exclusion is
a read input, never authority to move a protected event or apply a future plan.

## Busy truth and coverage

Queries always include hidden busy events and personal overrides. Skipped lessons,
nonblocking events, task deadlines and database date projections do not occupy time.
Saved calendar filters are never inputs to this calculation. UTC normalization
precedes interval comparison, including ambiguous DST folds; minimum duration is
elapsed time. Work blocks must be added to this complete-set boundary when their
storage is implemented; there are currently no stored work blocks to omit.

`verified=true` currently means that no official source is expected (no academic
profile) and personal calendar data was read successfully. An expected official
source adds `schedule_coverage_unknown` and `verified=false`, even when its status
is `ready`. The current schedule application contract supplies freshness/status,
not proof of complete coverage for arbitrary dates. Term boundaries alone are
insufficient. Existing stale/failed/unpublished warnings remain visible. Conditional
free windows are suggestions, not verified availability for academic plan writes.

`snapshot` is a deterministic SHA-256 fingerprint of the range, timezone, current
busy facts and source state/warnings. It is not authorization, a persisted plan or
a substitute for rechecking availability under write serialization. Work preferences,
task versions and explicit constraints must also bind any future plan confirmation.
No new IIS endpoint or completeness guarantee is assumed.

## Verification

Domain/service checks cover union/subtraction, nested/duplicate/touching intervals,
clipping, minimum duration, offsets/DST, hidden events, conditional coverage,
owned exclusions and fingerprint changes. HTTP checks exercise real sessions,
CSRF, exact timestamps, nonblocking events/deadlines, exclusions and unchanged
canonical events. Combined backend verification is recorded in [AI-10](ai-10.md).
