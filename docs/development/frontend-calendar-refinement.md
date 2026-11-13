# Calendar composition and safe range creation

Date: 2026-11-11. Status: implemented locally; not merged or deployed.
Scope: the owner's follow-up to [calendar stage 2](frontend-redesign-stage-2.md).
This iteration replaces that delivery's working-area composition. Tasks and later
redesign stages remain outside scope. The [interaction specification](frontend-interaction-spec.md)
and [visual direction](frontend-visual-redesign.md) remain the design basis.

## Design decision

The calendar is one working plane rather than a rounded card below a separate
page heading. A 64px application rail and a 200px calendar context column frame
the grid. The context column narrows to 180px while inspecting an event and contains the mini-month, Personal/IIS display toggles
and source connection. The shared sidebar collapse control also hides this column;
other sections retain their existing navigation. A1 and the native font stack,
plum personal events, teal official events and light/dark tokens are retained.

The toolbar groups month/year, timezone, Today, previous/next, Day/Week and New event.
The visible day headers supply dates; the date trigger's tooltip supplies the full
week range. The blank row that resembled all-day creation is removed. The timed
creation function remains available through the grid and New event. No all-day
capability is added or removed.

Larger day numbers, quieter grid lines, a source-colored event boundary and title-first
cards clarify temporal geometry. Short cards use ellipsis instead of cropped lines;
taller cards allow two title lines and location. Full names/intervals remain in
accessible labels, tooltips and event details. Existing intersecting intervals retain
separate lanes. The grid occupies the viewport; secondary daily agenda, task projections
and source setup remain accessible below it, without an additional permanent column.

At 1440px and above, event details occupy the trailing column. Narrower layouts retain
the focused detail/Back path and restore the grid's scroll and trigger focus. The
existing event form becomes a right-hand contextual dialog; on phones it becomes a
bottom sheet. Its custom date/time editor, exact-input alternative, dirty guard,
versioning and save boundary remain. Title focus is applied after native dialog open,
using the shared Modal's existing `initialFocus` support.

At up to 1100px, or with a coarse primary pointer, the calendar context panel is
initially hidden and opened through Calendars. Its date buttons have touch targets;
Escape/Close returns focus to the trigger. Day remains the initial compact view;
Week remains available with horizontal scrolling inside the grid. The application
navigation keeps its labelled mobile dock and drawer. Both themes share this layout.

```text
Desktop
[app rail][mini-month + sources][month / Today / arrows / Day Week / New]
         [calendar context   ][day headers and full-width time grid  ][details*]

Phone
[shared utility bar]
[Calendars][month + timezone]
[Today][arrows][Day Week][+]
[time axis | selected day]
[labelled application dock]
* Details only when an event is selected; contextual editing is a dialog.
```

## Bug reproduction and fix

Two browser regressions were added before changing selection logic. Both failed
against the previous build:

- Click at 10:15 before a 10:30 event produced a 10:15–11:15 draft.
- Drag from 10:00 through an 11:00 event produced a 10:00–11:30 draft underneath it.

`CalendarSelection` now receives the loaded event intervals and calculates the free
window around the actual pointer position. Only then does it snap to the 15-minute
grid. This order prevents a click at 11:08 from snapping into an event ending at
11:07. The one-hour click default ends at the next boundary. A drag in either direction
stays within its initial free window. A click in the narrow card gutter at an occupied
time creates no draft. Keyboard selection skips occupied times; extending a range
stops at the next event. If no time remains after the default 10:00 position,
initial keyboard selection searches back into the morning instead of becoming stuck. Hidden sources remain part of these boundaries: hiding a
source cannot make its interval behave as empty time.

These are gesture safeguards, not new availability or backend scheduling rules.
Personal-event overlaps remain supported through explicit date/time editing and
movement. No API rejects previously valid intersections. Moving/resizing preserves
its existing behavior and official events remain read-only. The UI does not claim
that this free window includes all backend planning constraints or verified IIS data.

An additional real touch issue appeared after moving the form: opening on pointer-up
could let the following click activate a newly positioned time-picker trigger. Range
completion now stores its draft until the originating click completes; that click
opens exactly one dialog. Pointer cancellation, Escape and native touch scrolling
still discard selection. No write occurs before explicit Create.

## Boundaries and preserved behavior

- No backend, API, DB, dependency, provider configuration or A1 asset changes.
- Existing CSRF/session/ownership boundaries and expected versions are retained.
- Mouse move/resize, Alt+arrows with Enter/Escape, keyboard range selection and
  explicit touch Move/Apply remain available. Native vertical touch scrolling stays native.
- Original event instants/seconds, midnight segments and elapsed-time DST behavior
  remain authoritative. The custom editor rejects gaps and requires fold occurrence selection.
- Official facts remain read-only; source warnings, notes/material links, reminders,
  confirmed deletion and source setup remain reachable.
- No real AI/provider call, install, migration, push, merge or deployment.

## Verification

Final executed checks:

- `npm run lint`: passed, no warnings.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `docker compose config --quiet`: passed.
- `npm test -- --workers=4`: **257 passed (1.8m)** on the final production build,
  including 13 new safe-selection/composition scenarios.
- Changed-document local links: **183 passed**; `git diff --check`: passed.

The restricted-shell retry could not start the local web server; it executed no
tests. The final run used the approved local-server execution path. All network
application/provider endpoints remained mocked.

Initial failures were used as evidence, not reported as passes. The first targeted
run passed the two original bug regressions and exposed the touch click-through.
The first full run found duplicate calendar headings and old week-title assertions;
the duplicate was removed and date-range tests now assert the trigger's full range.
The subsequent run uses the final production build.

New coverage includes click/forward/reverse boundary behavior, non-quarter-hour edges,
gutter clicks, hidden official intervals, keyboard creation, explicit intentional
overlap, compact panel Escape/focus and local mobile Week scrolling. Populated
1440/834/390/320px captures cover both themes, overlap lanes, contextual editing,
visible-text contrast and document overflow. Existing tests cover move/resize,
conflicts, cancellation, touch scrolling, timezone/DST, auth and other workspace flows.
All API traffic in tests uses synthetic fixtures, including AI tests.

## Review findings and acceptance

| Finding | Priority / principle | Result |
| --- | --- | --- |
| Default hour and drag crossed neighbouring events | P1, Nielsen #5 error prevention | Free-window boundaries; original failures have regression tests |
| Pointer-up could activate the newly opened phone picker | P1, Nielsen #3 control | Create draft after originating click; one tap opens one dialog |
| Calendar looked like a dashboard card with repeated headings | P1, hierarchy/grouping | Edge-to-edge temporal plane, local context, one toolbar |
| Cropped titles and times obscured card meaning | P2, typography | Title-first, ellipsis for short cards, full accessible label/detail |
| Context panel dismissal could lose keyboard focus | P2, consistency/control | Escape/Close and date selection return focus to Calendars |

Working well: the main focus is time geometry; sources and event details have explicit
boundaries; preview does not imply persistence; errors preserve the existing retry
paths. There is no decorative animation or additional UI package.

Web Interface Guidelines review: calendar-selection.tsx:190 — semantic button, keyboard
alternative, pointer cancel, described help; workspace.tsx:2195 — one calendar H1, labelled
icon action, post-open title focus and panel focus return; calendar-workspace.css:1 —
scoped layout, local overflow, existing focus/reduced-motion foundations retained.
The remaining guideline limitation is inherited mounted date/view/filter state rather
than URL-restorable calendar context; it is not claimed implemented by this iteration.

Overdesign verdict: restrained. Top three delivered priorities are safe range
selection, a coherent temporal working plane, and readable contextual event editing.

## Remaining limits

Browser tests use Chromium and synthetic HTTP fixtures. Physical-device virtual
keyboards, screen-reader output, high contrast, 200% zoom and Safari/Firefox remain
manual release checks. No live backend/provider integration was run. Gesture free
windows use loaded calendar events, not a new availability API. Whole-event drag
still targets rendered starting segments/columns; exact editing and explicit touch
placement cover other dates. Date/view/filter state is not newly persisted in the URL.

The existing task projection panel remains below the grid; redesigning task planning
or combining its data into the event canvas is not part of this iteration. Pre-existing
owner changes remain uncommitted and are excluded from this calendar commit.

## Actual renders

Screenshots are saved after the final passing run. They show Chromium with synthetic
student content, not mockups or production user data.

- [Desktop light](../design/calendar-refinement-desktop-light.png)
- [Desktop dark](../design/calendar-refinement-desktop-dark.png)
- [Tablet day](../design/calendar-refinement-tablet-light.png)
- [Phone dark](../design/calendar-refinement-mobile-dark.png)
- [Desktop contextual editor](../design/calendar-refinement-editor-desktop.png)
- [Phone event editor](../design/calendar-refinement-editor-mobile.png)
- [320px calendar context](../design/calendar-refinement-sources-mobile.png)

Personally inspected these layouts and the populated overlapping-card fixtures.
