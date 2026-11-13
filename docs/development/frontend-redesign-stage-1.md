# Frontend redesign stage 1: shared system and navigation

Date: 2026-11-11. Status: implemented locally; not deployed or merged.
Scope authorized: shared components, design system and navigation only.
Direction: Quiet Rhythm from [visual concept](frontend-visual-redesign.md) and
[interaction specification](frontend-interaction-spec.md), grounded in the
[UX audit](frontend-ux-audit.md) and [redesign plan](frontend-redesign-plan.md).

## Delivered

- Shared light/dark border, field-boundary and official-source tokens; 48px spacing
  and finite interaction-duration tokens. A1, system typography, semantic source
  colors and the existing theme startup/system behavior remain.
- A 216px desktop sidebar, 52px utility bar and 64px intermediate/collapsed rail.
  Plans, knowledge and utilities are grouped; Databases and Materials are direct
  destinations. All prior sections remain reachable. Phones keep the labelled dock
  and gain a searchable full navigation dialog with 44px links.
- Actual section links with native copy/new-tab behavior. Same-tab activation uses
  `/workspace?section=...`, preserves the session cache, and supports reload and
  Back/Forward. Existing page links and dedicated AI routes remain valid.
- Cmd/Ctrl+K and the Search button open a keyboard-operated palette. It filters
  destination names and hands a submitted content query to existing full-text
  results; it does not pretend to offer new global task/semantic search APIs.
- Shared modal initial focus, Escape handling even in populated search inputs,
  focus return and contained scrolling. Escape does not execute actions; dirty
  exits remain guarded. Navigation-dialog focus rings have space to render.
- Calendar status is explicitly scoped to the calendar. It no longer claims that
  every resource is synchronized or every note saved.
- AI route changes use the shared history helper, including continuing a review
  discussion from Inbox. This is navigation compatibility, not the AI redesign.

## Safety and implementation boundaries

Backend, API contracts, database, dependencies, provider flags and credentials are
unchanged. Tests use mocked API responses, including synthetic AI streams and
confirmations; no real provider requests or activation were performed. No push,
merge or deployment was performed.

For editors reporting unsaved text (notes and AI), internal section switches use
the existing custom confirmation. Browser
history uses a native confirmation and restores the previous history entry on
cancellation; native browser unload protection remains. History markers coexist
with Next.js through its supported native History API rather than copying its
internal router state. No private drafts or credentials enter browser storage.

This stage restores **sections**, not all selected objects, list filters or scroll
positions. Those contracts belong to later feature stages. The palette does not
create new tasks/pages/events yet: creation stays in each existing screen until
its own redesign. Search results remain in the dedicated existing screen rather
than being duplicated inside the palette. Mini-calendar, custom Time Strip,
new task details, note autosave and database cell editing are not implemented.

The working tree already contained owner changes. Only stage-related changes are
included in the local commit; unrelated owner edits are left in place. In shared
files, only the stage's token/focus/history/documentation hunks are staged.

## Verification

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `docker compose config --quiet`: passed.
- Existing/new relevant Playwright suite: **121 passed (1.5m)**, using
  `npm test -- workspace-shell-redesign.spec.ts workspace-content.spec.ts workspace-tasks.spec.ts workspace-calendar.spec.ts workspace-session.spec.ts workspace-ai.spec.ts design-auth.spec.ts --workers=4`.
- After the final dialog focus-ring CSS adjustment and capture stabilisation,
  `npm test -- workspace-shell-redesign.spec.ts --workers=4`: **8 passed (11.9s)**.

Coverage includes 320/390/834/1440px, both themes, keyboard focus and Escape,
reduced motion, simulated touch taps, loading/error/empty states, API-write
boundaries, reload/Back/Forward, dirty-note recovery, identity changes, timezone/DST,
upload retries and fake-AI/HITL behavior. Early runs caught and corrected initial
focus, mobile target size, Escape in search inputs and Next.js history compatibility;
those failed/interrupted runs are not counted as passing verification.

Browser captures use synthetic data. They exercise the current working tree,
including pre-existing owner changes, not an isolated clean checkout. Backend
checks were not rerun because no backend code changed. This is not a full frontend
suite or WCAG certification; real touch hardware, screen readers and 200% zoom
remain unverified.

## Design and usability review

Applied frontend-design and interaction-design to the implementation and reviewed
with ux-aesthetics-audit, ux-heuristics-audit and the fetched Web Interface Guidelines.

Heuristics: H1 improves through resource-specific status; H3/H5 through guarded
history and predictable Escape; H4 through real navigation links; H6/H7 through
direct knowledge destinations and searchable navigation. Existing calendar DST,
version-conflict, recovery, identity isolation and HITL checks remain required.

Aesthetics: hierarchy comes from quiet group spacing and a lavender selected row,
not extra cards. Navigation and toolbar recover working space; panels retain the
current feature layouts until their stages. Overdesign verdict: restrained. Top
three remaining design priorities are calendar space/time controls, mobile task
context and uninterrupted notes; all remain outside stage 1.

Web Interface Guidelines: new controls have names, real links, focus feedback and
keyboard alternatives; reduced motion suppresses finite transitions. No blanket
WCAG conformance is claimed. Physical-device keyboards, screen-reader output and
full zoom/high-contrast testing remain manual release gates.


## Inspected captures

Personally inspected final desktop light shell/palette, tablet dark palette,
320px light navigation search and 390px dark palette. Saved examples:
[desktop](../design/frontend-shell-stage-1-desktop.png),
[phone palette](../design/frontend-shell-stage-1-mobile.png),
[narrow navigation](../design/frontend-shell-stage-1-navigation.png).
Captures show existing task content layouts deliberately retained for stage 3;
they are actual mocked browser renders, not redesign concept drawings.
