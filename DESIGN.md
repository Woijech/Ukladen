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

- Desktop: a 224px navigation column and a quiet 60px utility bar. The calendar
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

Calendar, Notes, Tasks and AI are primary destinations. More discloses all existing
tools; settings and the account stay at the foot of the sidebar. A compact icon
rail serves intermediate widths, with accessible names and tooltips retained.
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

## Verification

Use the existing mocked-API Playwright suite to exercise auth, CSRF, identity
changes, calendar DST, editing, conflicts, restore and AI confirmations. Inspect
light/dark captures at desktop, intermediate and phone widths. Verify keyboard,
focus, overflow, text contrast and safe-area spacing. Mock content belongs only in
tests. Provider calls, deployment and database changes are outside this redesign.
Record actual results and the Anti-Slop Delivery Gate in the frontend design review.
