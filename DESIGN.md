# Ukladen visual system

Status: implemented direction for the existing Next.js frontend. The A1 identity
and all existing API, session, ownership and calendar-time contracts are retained.

## Design read

A personal productivity workspace for people balancing study, plans and knowledge.
The visual language is an ink-and-paper desk: quiet navigation, precise calendar
tiles and an open writing surface. ENERGY 1 / RHYTHM 2 / MOTION 1.

The A1 logo supplies the signature: rounded square tiles, lavender and dark plum.
The repeated motif is a square date tile or selected destination, rather than a
decorative pattern. No new logo, avatar, illustration or product data is generated.

## Typography

Use the native humanist sans stack, starting with Segoe UI and system-ui. Its open
Cyrillic letterforms suit long Russian labels, and local fonts avoid network shifts.
Body text is 15px with 1.6 line height; controls are 13–14px. Page titles use a fluid
28–36px scale, medium weight and modest negative tracking. Note titles reach 40px;
the document body stays at 16px and a comfortable reading width. Calendar times
use tabular numerals. Metadata uses sentence case, never tracked uppercase.

## Colors and surfaces

| Role | Light | Dark | Purpose |
| --- | --- | --- | --- |
| Workspace | `#f6f5f2` | `#171719` | Warm desk around the work |
| Document | `#ffffff` | `#222225` | Main reading and editing plane |
| Navigation | `#eeedea` | `#1c1c1f` | Recessive, stable orientation |
| Text | `#29262e` | `#f0edf2` | Comfortable high contrast |
| Secondary text | `#64616b` | `#b5b0bc` | Readable labels and metadata |
| Accent | `#70558e` | `#bca5d8` | Primary action, selected date, focus |
| Accent surface | `#ede7f3` | `#342c3e` | Personal events and selection |
| Official source | `#246566` | `#a4d4ce` | Distinguish imported academic facts |

Use neutral separators for grouping and stronger field boundaries for controls.
Error and success colors always accompany text. Teal identifies an official source;
plum identifies personal content. These meanings do not change with theme. The
existing system/light/dark choice and startup theme script remain authoritative.

## Spacing and layout

Use 4, 8, 12, 16, 24, 32 and 48px spacing steps. Small gaps connect controls;
larger gaps separate contexts. There is one primary work surface per screen.

- Desktop: a 216px navigation column and a quiet 52px utility bar. The calendar
  gains a narrow day/source context column when there is room for seven readable
  days. At intermediate widths, context moves below the calendar.
- Notes: a compact page index beside an uninterrupted document; the document has
  a reading width, not a card inside another card. Secondary relations sit below it.
- Tasks: a scannable task queue beside a detailed work sheet. On smaller screens
  they stack, preserving every filter, hierarchy and planning control.
- AI: a conversation index and a centered transcript with a clearly bounded
  composer. Citations, proposals and their confirmation controls remain explicit.
- Settings: separated sections with aligned labels, rather than a grid of cards.
- Authentication: a typographic brand panel with the approved full logo, paired
  with one focused form. Phones show the form without an ornamental panel.

## Navigation

Desktop groups Calendar/Tasks, Notes/Databases/Materials and AI/utilities as direct
links; settings and the account stay at the foot of the sidebar. A compact 64px
icon rail serves intermediate widths, with accessible names and tooltips retained.
Phones gain a labelled bottom navigation for the four primary destinations and
More, opening the existing native navigation dialog. Safe-area and content padding
reserve its space. Dirty-document navigation still uses the existing save guard.
The calendar opens in day view on phones, preserving the week option and the
profile timezone. A full-width day makes times and real events immediately legible.

## Component language

Use 6px corners for controls, 8px for date/event tiles, 12px for dialogs. Most
content sits flat. Shadows identify only transient menus and dialogs. Lists use
row separators; selection uses a filled tile and heavier text. Existing inline
SVGs describe concrete objects; AI uses a conversation glyph rather than magic.
Cards are retained only where they define an independently actionable surface.
Calendar grid lines express time, never decoration. No gradients or glass layers.

Fields have visible labels, strong boundaries, text errors and native semantics.
Buttons have hover, pressed, disabled and focus states. Coarse-pointer targets are
at least 44px except direct calendar geometry, whose keyboard and explicit form
alternatives remain available. Block editing retains keyboard reorder controls.

## States and motion

Empty states explain what fills the view; filtered emptiness differs from first use.
Loading states identify the resource and reserve the working area. Errors retain
drafts and offer the existing recovery action. No fabricated activity or metrics.
Hover/pressed transitions take 120ms. Dialogs and menus need no entrance animation;
the work stays still. Reduced motion disables nonessential transitions and animation.

### AI conversation refinement, 2026-11-09

The owner requested a more expressive, understandable chat with visible motion.
For the AI area, use ENERGY 2 / RHYTHM 2 / MOTION 2. The rest of the workspace
retains its existing dials. A deep jade action color (`#246858`, dark `#9edbc8`)
distinguishes sending and source selection from the plum workspace navigation.
Warm reading surfaces and the approved A1 symbol retain the Ukladen identity.

The composer is the focal point: a clear message field, labelled source selection,
one prominent Send button and a secondary response-options disclosure. Source-only
and full-document modes have short explanations and remain visible in the closed
summary when enabled. Starter questions fill a draft and never submit automatically.
Concrete document, conversation, send, stop and trash glyphs clarify the actions.
Model/connection facts remain readable in the chat header without competing with
the title. Sources are grouped below their answer and retain their existing viewer.
Equal starter tiles represent three peer actions, not a feature-card showcase.
The 800px reading limit keeps long answers legible; the softer composer boundary
marks the editable area. Phone history and creation share a row, while the open
conversation omits the repeated visible page heading. Natural phone reflow keeps
long answers, expanded options and feedback inside the panel. The existing message
scroll area remains bounded, and page scrolling keeps the composer reachable.

Messages enter once over 260ms, controls respond over 160ms, and disclosures open
over 200ms. These movements explain arrival, selection and expansion; streaming
text does not restart the message animation. No idle loop or simulated progress is
used. Reduced-motion disables these effects. Native keyboard operation, focus and
44px touch targets remain required. No new motion or icon dependency is needed.

## Verification

Use the existing mocked-API Playwright suite to exercise auth, CSRF, identity
changes, calendar DST, editing, conflicts, restore and AI confirmations. Inspect
light/dark captures at desktop, intermediate and phone widths. Verify keyboard,
focus, overflow, text contrast and safe-area spacing. Mock content belongs only in
tests. Provider calls, deployment and database changes are outside this redesign.
Record actual results and the Anti-Slop Delivery Gate in the frontend design review.


### Shared shell redesign, stage 1, 2026-11-11

Implemented: Quiet Rhythm foundations with the existing A1 identity and native font
stack. Shared border/control/source tokens now follow the approved redesign;
spacing includes 48px and feedback/popover/panel timing tokens. Desktop navigation
is 216px with grouped direct links to plans, knowledge and utilities, plus a 52px
utility bar. Tablet/compact navigation uses a 64px rail. Phones retain the labelled
dock and gain a searchable full-destination dialog with 44px links.

Sections use real links and URL state with Back/Forward support. Cmd/Ctrl+K and the
Search button open a keyboard-operated transition/search palette; content searches
continue in the existing full-text results screen. Shared dialogs support explicit
initial focus and contained scrolling. Calendar status names its resource rather
than implying that every document is saved. Internal dirty exits retain the current
confirmation; history exits use a browser confirmation and restore the entry when
cancelled. No private drafts are persisted in browser storage.

This stage does not implement the proposed mini-calendar, Time Strip, task detail
layout, note autosave or database cell editors. Existing calendar/task/note/AI work
surfaces remain. Verification and remaining limits: [stage 1 delivery](docs/development/frontend-redesign-stage-1.md).


### Calendar redesign, stage 2, 2026-11-11

Implemented: compact calendar heading/date toolbar, direct Day/Week selection,
collapsible source controls and a desktop sidebar month calendar. The time grid
uses viewport space; event details share a contextual column at 1440px and above,
with a focused surface and Back on narrower screens. Day is the initial view up
to 1100px; explicit Week choice remains available. Selecting an event retains the
grid scroll and restores its trigger focus. Existing task projections, daily agenda
and source setup remain available below the grid.

Personal-event moving now supports mouse preview/commit, Alt+Up/Down with explicit
Enter, and touch placement with separate Apply/Cancel. Resize/range selection,
official read-only facts, original intervals and version/timezone/DST semantics
remain. Event forms use a custom Time Strip with a month grid, editable tabular
clock, minute/hour steppers, duration presets and timezone/offset selection.
It is anchored and viewport-bounded on desktop and a bottom sheet on phones.
All-minute/native exact input remains available in a secondary disclosure.
Picker Apply updates a draft; only event Create/Save writes. No animation or
provider dependency was added. See [stage-2 delivery](docs/development/frontend-redesign-stage-2.md).
