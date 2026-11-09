# Frontend visual redesign review

Date: 2026-11-09. Branch: `codex/ukladen-visual-system`.
Scope: the existing frontend only. Direction: [DESIGN.md](../../DESIGN.md).
Anti-Slop mode: DURING, explicitly selected by the owner.

## Delivered system

The warm neutral workspace, ink typography and restrained plum accent reuse A1.
The shell has four primary destinations and an icon rail at intermediate widths.
Phones have labelled bottom navigation, safe-area spacing and a day-first calendar.
Wide calendars place the day agenda/source beside the time grid; narrower layouts
move that context below. Notes use a continuous document/index layout, with readable
mobile titles and block controls revealed by focus/tap. Tasks use a joined queue
and detail sheet. AI has a transcript, visibly labelled composer, separated source
options and a collapsible history. Settings, resources, databases, public and auth
surfaces consume the same tokens. No new runtime dependency was added.

## Executed checks

| Check | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS, Next.js standalone output |
| `npm test -- --workers=4` | PASS, 206 Chromium tests |
| `docker compose config --quiet` | PASS |
| `git diff --check` | PASS |

Eleven added browser scenarios cover public/auth themes at 320/390/834/1440px,
secondary workspace sections at 390/1024/1440px, AI at 390/1440px, dirty-note
protection through the mobile dock, and keyboard skip/menu dismissal. Existing
captures also cover the calendar, task dialogs, block picker, notes and event
details at 390/834/1440px. Both light and dark states were captured and inspected.
The new visual sweeps collect uncaught browser exceptions and require none.

`tests/design-checks.ts` computes foreground/background contrast for visible text
in the captured fixture states and checks document overflow. Native disabled
controls and visually hidden content are excluded. Text uses the AA 4.5:1/3:1
thresholds. The supplied Anti-Slop contrast checker additionally measured field
boundaries: light `#8b8493` on white = 3.61:1; dark `#807988` on `#222225` = 3.78:1.
These are non-text boundaries, whose threshold is 3:1. Secondary text on selection
surfaces measured 4.60:1 light and 5.57:1 dark. This is scoped evidence, not a full
WCAG conformance certification.

## Recorded interaction evidence

All rows below passed in the browser suite; data and external responses are mocked.

| Control/scenario | Observed behavior |
| --- | --- |
| Home calendar link | Opens the actual workspace sign-in route |
| Email/password login and registration | Submit existing CSRF-protected contracts; registration continues to completion |
| Password reset and email verification | Validate input, submit once, recover from failures and clear URL proof fragments |
| Google sign-in/linking | Validate destinations, retain password/CSRF guards and discard secrets on close/expiry |
| Calendar/Notes/Tasks/AI navigation | Opens the selected existing section |
| More | Reveals secondary destinations; Escape closes and restores focus |
| Mobile dock | Opens notes/tasks; dirty-note navigation presents the existing guard and retains text |
| Mobile More dialog | Opens all sections; Escape restores its trigger |
| Theme control | Cycles system/light/dark and preserves the selected theme on reload |
| Sidebar collapse | Changes to the 76px rail without losing named controls |
| Skip link | Keyboard activation focuses the workspace content |
| Account and calendar view menus | Enter opens; Escape closes and restores the trigger |
| Calendar day/week selector and arrows | Change displayed dates/view; phone initial view is one day |
| Personal/official filters | Change display without a write or availability mutation |
| Calendar help | Native disclosure opens keyboard/pointer instructions |
| Calendar pointer/touch/keyboard selection | Previews an interval; only explicit form submission writes |
| Event detail/edit/delete and resize | Preserve original intervals/versions; official events stay read-only |
| DST/repeated hours | Retain explicit offset choices, elapsed geometry and original instants |
| Notes tree/breadcrumbs/creation | Select, nest and navigate the existing pages |
| Block slash/plus, reorder and link controls | Preserve IDs/content; keyboard/native menu operations work |
| Note save/conflict/trash/restore | Preserve drafts, advanced versions and recoverable branches |
| Task quick add/completion/detail/filter/subtasks | Use the existing versioned task endpoints |
| Task planning/dependencies/sessions | Retain previews, partial confirmation and conflict handling |
| Material upload/download/bookmarks/attachments | Retain byte contracts, validation and explicit removal |
| Collections/tags | Add/remove references without deleting content |
| Database records/schema/table/calendar views | Preserve stable options, hidden/null values and date-only semantics |
| Search | Renders snippets as text and opens the selected note |
| Inbox/reminders | Mark reads and create/cancel through existing protected APIs |
| Profile/timezone/avatar | Preserve raw upload limits, confirmation and calendar refresh |
| AI history/new chat/source picker | Retain model/connection selection and selected-source contracts |
| AI send/cancel/recovery/citations | Use mocked streaming, recover stored runs and inspect safe sources |
| AI proposal confirmations | Apply only exact confirmed digests; reject stale/expired proposals |
| AI instructions/reviews/usage/diagnostics | Retain draft conflict handling, access guards and unknown usage values |
| Session expiry/account change | Remove private editors, dialogs, drafts and query caches |
| Reduced motion | The dock test verifies zero transition duration under the preference |

## Visual corrections from browser inspection

- The original phone week crop hid the selected day; phone startup now selects day view.
- A general mobile input rule reduced note titles to body size; low-specificity field
  defaults now preserve the document type scale.
- The original persistent hints competed with the calendar; a native help disclosure
  keeps the grid primary and retains accessible descriptions.
- AI history pagination wrapped a short range; spacing and label widths now fit.
- Phone AI history consumed excessive height; its native disclosure can collapse.
- Source checkboxes ran together; composer options now have separate labelled rows.
- Lazy brand loading left early captures blank; above-fold branding loads with priority.
- Settings claimed AI was unavailable despite its implemented UI; it now links to
  actual settings and explains configuration-dependent model availability.

## Anti-Slop Delivery Gate

PASS statuses refer to the changed frontend and the recorded verification scope.
The untouched domain/API behavior is guarded by the existing regression suite.

### Hard gate

| Rule | Status and evidence |
| --- | --- |
| R-02 | PASS: newly authored product copy contains no em dash; existing source/data placeholders were not bulk rewritten |
| R-03 | PASS: document overflow checks and inspected phone/intermediate/desktop captures; labelled dock and coarse-pointer control sizing |
| R-17 | PASS: no invented production metrics or activity; synthetic values live only in test fixtures |
| R-18 | PASS: no invented people, testimonials or profile images |
| R-23 | PASS: owner-authorized navigation redesign; only approved A1 assets reused |
| R-24 | PASS: existing destinations retained; the settings AI link targets its actual route |
| R-25 | PASS: rendered text checks across captured themes; field/focus token contrast computed separately |
| R-26 | PASS: native controls retain handlers/hrefs; interaction evidence above records actual browser actions |
| R-27 | PASS: existing empty/error/retry flows retained; shared loading now includes visible text |
| R-28 | PASS: no FAQ introduced |
| R-32 | PASS: skip-link, menu Escape/focus return, native dialogs and existing keyboard editor/calendar tests |
| R-33 | PASS: edits made directly in source; no source-rewriting patch scripts |
| R-34 | PASS: both themes captured, checked for contrast and inspected |
| R-35 | PASS: production build, 206 browser tests and recorded control evidence |
| R-36 | PASS: no fabricated security, performance or customer claims |
| R-37 | PASS: design read and dials declared before implementation and recorded in DESIGN.md |
| R-38 | PASS: production surfaces still consume existing APIs; no decorative fixture data shipped |
| R-39 | PASS: native labelled controls, focus/disabled/pressed states, pointer affordances, reduced-motion override and sized approved imagery |
| R-40 | PASS: Next Image dimensions retained, branding prioritized, no new third-party scripts or fonts; field performance not claimed |

### Purpose gate

| Rule | Status and evidence |
| --- | --- |
| R-01 | PASS: A1 plum identifies action/selection; teal identifies official sources; no new gradients/glows |
| R-04 | PASS: existing concrete object glyphs reused; AI now uses a conversation glyph |
| R-06 | PASS: native Cyrillic-friendly sans and tabular time numerals; rationale in DESIGN.md |
| R-07 | PASS: grid lines express actual calendar time; no patterned backgrounds |
| R-08 | PASS: authored CTAs avoid decorative arrows; existing time/navigation arrows retain direction |
| R-09 | PASS: task/material states describe actual data; no decorative novelty badges |
| R-10 | PASS: no new glass layers; modal backdrop blur removed |
| R-12 | PASS: transient menus/dialogs carry elevation; document/list surfaces remain flat |
| R-13 | PASS: no glow added |
| R-14 | PASS: calendar canvas, note document, task queue and settings rows have different content-driven structures |
| R-19 | PASS: 120ms control transitions only; perpetual decorative loading pulses removed; reduced motion disables transitions |
| R-22 | PASS: no stock or generated illustrations |

### Liveliness and craftsmanship

| Item | Status and evidence |
| --- | --- |
| Dials | PASS: ENERGY 1 / RHYTHM 2 / MOTION 1, consistent across the inspected screens |
| Focal point | PASS: calendar time grid, note body, task work sheet or AI transcript leads each screen |
| Whitespace | PASS: reading width, contextual column and separated settings rows define structure |
| Accent/motif | PASS: A1-derived plum and square date/selection tiles repeat in meaningful states |
| C-1 / R-31 | PASS: palette, fonts, spacing, layout, elevation and motion have written reasons |
| C-2 | PASS: protected interactions retained and exercised; no dead new controls |
| C-3 / R-05 | PASS: compositions follow calendar, writing, task and chat work; no new metric grid or filler feed |
| C-4 | PASS: both themes, viewport sweeps, failure/recovery and keyboard regressions pass |
| C-5 | PASS: all verification statements above correspond to executed checks |
| R-11 | PASS: control, tile and dialog radii have distinct roles rather than universal pills |
| R-15 / R-16 | PASS: authored action labels name their actual operations; no marketing superlatives |
| R-20 / R-30 | PASS: A1 ink/paper/date-tile direction, with references used as quality guidance rather than copied screens |
| R-21 / R-29 | PASS: system/light/dark remain available; neutral surfaces, plum action and teal official-source semantics |

## Boundaries

No backend, database, API client, CSRF, session-isolation or timezone conversion code
changed. No AI/provider requests, secret reads, deployment, migration or push occurred.
Playwright uses mocked HTTP responses; live backend/email/IIS/provider integration,
physical mobile keyboards, other browser engines and field Web Vitals were not
tested. Backend Ruff/Pyright/pytest were not rerun for this frontend-only change.
The screenshots are test fixtures, not a record of a real user's workspace.

Local before/after captures are retained under `.local/design-review/` (ignored by
Git); regular Playwright artifacts remain under `apps/web/test-results/`.
