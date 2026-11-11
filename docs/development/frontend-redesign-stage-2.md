# Frontend redesign stage 2: calendar and event time controls

Date: 2026-11-11. Status: implemented locally; not merged or deployed.
Follow-up: [calendar composition and safe selection](frontend-calendar-refinement.md)
supersedes this report's working-area layout; verification below remains historical.

Scope: Calendar only, following the approved [interaction specification](frontend-interaction-spec.md),
[visual direction](frontend-visual-redesign.md) and [UX audit](frontend-ux-audit.md).
Stage 1 remains documented [separately](frontend-redesign-stage-1.md).

## Delivered behavior

The calendar uses a compact heading and date toolbar instead of a large introductory
heading. Day and Week switch directly through a segmented control; the redundant
menu and unavailable Month entry are removed. Source filters remain available in
an explicitly labelled disclosure and affect display only. The scrollable time grid
uses more of the available viewport while keeping access to every hour.

The full desktop sidebar includes a small month calendar, with selected/today states,
month navigation and keyboard date selection. Its fine-pointer targets are compact;
on tablet, phone, collapsed rail and coarse pointers the same date selection is
available through the larger calendar date dialog. Tablet/phone initially select
Day at widths up to 1100px; Week remains selectable. No resize listener repeatedly
overrides an explicitly selected view.

Event inspection keeps the grid mounted. At 1440px and wider, details occupy a
320px contextual column; narrower screens use a focused detail surface with Back.
The original grid scroll and event focus return on exit. Existing descriptions,
official facts, reminders, note/material links and related-event navigation remain.
Personal-event editing, confirmed deletion and academic source setup retain their
existing API paths and ownership/session boundaries. Official events remain read-only.

Personal intervals can be dragged with a mouse within the rendered day columns;
a labelled ghost previews the target and elapsed duration is preserved. Alt+Up/Down
previews 15-minute moves; Enter commits, Escape cancels. Edge resize and range-create
retain their existing pointer/keyboard behavior and original interval identity.
Move sessions retain the source version, share the existing single-flight lock and
show failures without a success claim. A continuation segment opens the original
event; use its explicit move/editor path when the starting segment is outside view.

Touch has a deliberate placement mode: Open event → Move event → tap/select a new
start in the grid → Apply move. Cancel/Escape discards the destination preview and
no write occurs before Apply. Ordinary touch scrolling never starts whole-event
dragging. Exact date/time editing is another alternative for other dates/weeks.

## Time Strip

Event forms now expose designed start/end chips and an anchored temporal dialog on
desktop, switching to a full-width bottom sheet on phones. It contains a custom
month grid, Start/End selection, a large editable clock, labelled hour/minute
steppers, quarter-hour minute suggestions, ±5-minute actions, elapsed-duration
presets and an explicit timezone/offset summary. Enter in the clock applies the
local picker draft; it does not submit the event form.

The clock accepts `9:37`, `09:37` and numeric-keyboard entry `0937`. Every minute
remains available. Minute/hour stepping rolls the visible civil date over midnight.
A duration preset computes End from Start using elapsed instants. Moving Start alone
does not silently change End; invalid intervals explain how to choose an End or
next day. Apply updates the event draft; Create/Save is still the persistence boundary.
Cancel/Escape leaves the outer draft unchanged and returns focus to its trigger.

All conversion uses the existing calendar-time helpers. Nonexistent DST times are
rejected; repeated times require an explicit occurrence/offset selection. Unchanged
minute displays preserve original seconds/instants. The native exact date/time
fields remain under a labelled disclosure as an alternate precise input path.
They are not the default presentation. Pending saves cannot be dismissed; edited
event forms require confirmation before closing. The picker is viewport-bounded,
scrolls internally when necessary, and keeps its Apply action reachable.

This changes event controls only. Task deadlines, session/preferences and AI review
time controls are outside this stage and retain their current interfaces.

## Preserved contracts and boundaries

No backend, API, database, provider configuration, logo or dependency change. No
real AI/provider calls, installation, push, merge or deployment. Existing official
source freshness/coverage warnings remain; the UI does not claim verified free time.
Personal-event overlaps remain allowed. Hiding sources changes no busy intervals.

Event DELETE remains confirmed and has no fictitious Undo/restore. No recurrence,
all-day creation, official override editor, saved mixed calendar UI or new search
contract is added. Task projections, daily agenda and academic setup remain available;
this stage does not reinterpret task deadlines as scheduled work.

Date/view selection remains mounted workspace state; saved calendar views and full
object/filter/scroll restoration across reload are not introduced here. The stage-1
section links/history and existing private page/AI links remain intact. Whole-event
dragging targets rendered columns and uses a 15-minute grid; the editor retains
arbitrary-minute precision and provides access beyond the rendered week.

## Verification

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `docker compose config --quiet`: passed.
- `npm test -- --workers=4`: **241 passed (1.7m)** across the complete frontend suite.
- After final viewport bounding of the temporal editor, including three additional
  DST/scroll/focus regressions, `npm test -- workspace-calendar-redesign.spec.ts --workers=4`:
  **17 passed (17.7s)**. This includes 320/390×844 phone checks, 834/1440px layouts,
  both themes, all-minute input, midnight rollover, gap/fold validation, exact-second
  preservation, version-conflict recovery, mouse/keyboard movement and simulated
  touch placement. Apply must be fully inside the viewport in all four layouts.

The initial targeted runs found test timing/fixture assumptions and a real desktop
popover height issue. These were corrected; failed/intermediate runs are not counted
as passing verification. The full-suite result predates only the final picker
height refinement; the 17-test rerun covers that final implementation.
Tests use synthetic API fixtures; no real user content/provider account is involved.
The working tree includes pre-existing owner changes. Only stage-2 hunks are included
in the commit; those earlier changes remain uncommitted.

## UX and visual review

Used frontend-design and interaction-design for the implementation, with the
heuristics/aesthetics audit lenses and freshly fetched Web Interface Guidelines.

- Hierarchy: the grid is the focal work surface; secondary source controls fold
  away, while Day/Week and New event stay visible.
- Control/freedom: no create/write on pointer-down, picker opening or preview;
  keyboard/touch alternatives and explicit cancel paths exist; dirty event drafts
  are guarded. Error states retain the form/destination rather than pretending success.
- Consistency: date tiles, plum selection, neutral surfaces and existing A1/teal
  source distinction remain shared with the stage-1 shell.
- Focus: event detail has a clear entry/return target; nested picker Escape closes
  only that layer. New custom date buttons meet 44px targets in phone captures.
- Motion: existing finite feedback only; no new animation dependency or idle motion.

Overdesign verdict: restrained; the temporal editor is the densest surface and uses
one active endpoint and one primary Apply action. Do not add a clock-face animation
or additional control layers. Next priorities are mobile task continuity and inline
properties (stage 3), followed by uninterrupted note composition (stage 4).

Physical-device virtual keyboards, screen-reader output, 200% zoom and high-contrast
mode remain manual release checks; Chromium viewport/touch emulation is not proof of
those environments. No general accessibility certification is claimed.


## Inspected renders

Personally inspected fresh desktop/week and tablet/day grids, narrow light and
phone dark temporal controls, the final bounded desktop picker and the desktop event inspector. Saved examples:
[desktop calendar](../design/frontend-calendar-stage-2-desktop.png),
[tablet calendar](../design/frontend-calendar-stage-2-tablet.png),
[desktop temporal control](../design/frontend-calendar-stage-2-time-desktop.png),
[phone temporal control](../design/frontend-calendar-stage-2-time-mobile.png),
[desktop event inspector](../design/frontend-calendar-stage-2-inspector.png).
These are actual Chromium renders with synthetic data, not concept mockups.
