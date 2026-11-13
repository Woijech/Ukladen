# Workspace deep links

Date: 2026-11-13. Status: implemented locally on `workspace-deep-links`.
Frontend-only delivery; no API/schema changes, migrations, dependencies, deployment
or real provider requests.

## Address contract

| Destination | Address |
| --- | --- |
| Task | `/workspace?section=tasks&task=TASK_UUID` |
| Page | `/workspace?section=notes&page=PAGE_UUID` |
| Database / saved view | `/workspace?section=databases&database=DATABASE_UUID&view=VIEW_UUID` |
| Database calendar date | Same database/view address with `&date=2026-11-13` |
| Personal calendar | `/workspace?section=calendar&date=2026-11-13&view=week` |

Identifiers are UUIDs. Calendar `view` accepts `day` or `week`; a database `view`
identifies a saved view instead. Dates are civil dates in the profile timezone, not
UTC instants or the device's timezone. Missing dates use today; without an explicit
calendar layout, the initial narrow-screen default remains day and desktop week.
Explicit URL layouts survive viewport changes and reload.

Legacy `/workspace?page=PAGE_UUID` links still open notes. Newly copied page links
use the canonical section/page address, also used by search and related-page
navigation. Existing `/workspace/ai`, `/workspace/ai/usage`, chat parameters and
search `q` remain supported. Links contain no titles, bodies, credentials or drafts.

## Navigation and loading

`workspace-location.ts` owns typed parsing, UUID/date validation and serialization.
`use-section-location.ts` synchronizes the complete location with native history.
Explicit object/date/layout changes push history entries; invalid/duplicate values
are removed with replacement and a visible warning, without adding a history entry.
History writes preserve Next.js-owned state. Back/Forward and reload restore the
selected object, date and layout.

`src/instrumentation-client.ts` registers a lightweight traversal delegate before
hydration. Only the mounted workspace subscribes to it. Registration must precede
Next.js's history handler: a late rejection can leave the URL intact after a tab's
editor has already been unmounted. Rejected and compensating traversal events do
not reach that handler. History payloads let Next.js restore its own loop markers
and synchronize `usePathname`/`useSearchParams`, rather than passing markers that
skip synchronization. Dedicated AI-tab navigation is covered by regression tests;
no AI/provider behavior changed.

Tasks, pages and databases use direct owner-checked GETs for selected IDs, independent
of loaded rows. Saved database views have their own direct GET under the selected
database; both returned IDs are checked before rendering. A selected view outside
the first 200 list rows remains visible and usable. List pagination itself is unchanged.

Missing/forbidden objects share the generic **Object unavailable** state and a return
to the appropriate list; a foreign view never renders its records. Transient read
failures retain the link and expose Retry. A URL grants no access: existing API
ownership/session rules remain authoritative. Each authenticated identity still
gets a separate query client and mounted forms; account changes discard old data.

## Draft and write safety

Internal navigation retains existing editor confirmation flows. Browser Back/Forward
asks before discarding dirty edits, including transitions between two tasks or two
pages. Refusal restores the previous address and keeps the mounted draft; acceptance
discards the draft before changing objects. Tracked in-flight editor writes block
navigation until completion. The shared unload guard also covers dirty/busy state.
Database record/property/view/settings editors report their state to that guard.
Task relations and work-planning writes also report pending state. Guard signals
are synchronized before paint so a just-disabled Save control cannot race Back.

No autosave, browser storage, crash/offline recovery, durable scroll restoration or
URL-based task filters/pagination was added. Existing mounted task-list choices
remain local; leaving the section does not promise to retain them. Small-dialog
close/cancel policies and all-browser accessibility testing remain separate work.

## Verification

Final verification on 2026-11-13:

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `PLAYWRIGHT_PORT=3011 PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome npx playwright test --workers=4 --reporter=dot`: **341 passed (2.3m)**.
- `docker compose config --quiet`: passed.
- `git diff --check`: passed.

Focused cases cover parser normalization, Next.js state retention, calendar
date/layout reload and history (including explicit mobile week links), direct reads
outside loaded lists, unavailable/mismatched objects, network retry, stale ownership
rechecks, rejected/approved dirty traversal and in-flight page/task/database/planning
saves. Existing identity, editor, calendar, auth and synthetic AI suites also passed.
Preliminary failed runs identified the Next.js marker/handler-ordering and pending
signal defects; those runs are not counted as passing verification.

Backend checks were not rerun: no backend code changed. Earlier dated redesign
reports retain their original evidence. Verification uses installed Chrome; Firefox,
Safari, real-device and screen-reader checks remain separate release gates.

Browser tests use synthetic intercepted APIs and a dedicated production server.
To use an installed Chromium-compatible browser and an unoccupied port:

```bash
cd apps/web
npm run build
PLAYWRIGHT_PORT=3011 PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/google-chrome npm test
```

Both overrides are optional; defaults remain Playwright Chromium and port 3001.
These tests do not need the real API, SMTP, IIS or AI services.
