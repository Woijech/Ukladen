# Ukladen visual redesign

Date: 2026-11-11. Status: proposed concepts and wireframes, not production UI.
Companion: [interaction specification](frontend-interaction-spec.md).
Basis: [audit](frontend-ux-audit.md), [plan](frontend-redesign-plan.md), [current visual system](../../DESIGN.md).

## 1. Two concepts

### A. Quiet Rhythm — recommended

A study workspace built around the rhythm of date tiles, task rows and paragraphs. Compact plum navigation frames an open calendar or document. Lavender selection connects the A1 tiles to dates and active objects; teal labels identify official facts. The memorable element is the custom Time Strip: a square date tile and large tabular time segments joined by an interval preview. It turns a common student action into a clear, recognisable Ukladen interaction.

Light base: desk `#F6F5F2`, paper `#FFFFFF`, ink `#29262E`, muted `#64616B`, plum `#70558E`, official teal `#246566`. Dark base: desk `#171719`, paper `#222225`, ink `#F0EDF2`, muted `#B5B0BC`, lavender `#BCA5D8`, official teal `#A4D4CE`.

Typography: native humanist sans for navigation, tasks and documents; 18px document body, strong 36px page title, tabular time. Layout: one stable navigation edge, one dominant work plane, a contextual inspector only when needed. Text left-aligned; reading column centred within the available document plane, not every title centred on screen.

Why this fits: retains the approved identity and existing palette while materially changing working-area density and object interaction. Notion Calendar contributes temporal geometry, Linear contributes row operations, Craft contributes the uninterrupted writing canvas. These are one shared system, not three branded skins.

### B. Graphite Studio — alternative

A more instrumental workspace with cooler surfaces, stronger section boundaries and sharper density. A1 remains lavender/plum, but selection uses a narrow structural edge and neutral filled row instead of a large lavender wash. Calendar data and task columns feel like a precise planner; notes have a slightly narrower editorial column with stronger heading spacing. The Time Strip remains the shared interaction signature.

Light base: workspace `#EDF0F3`, sheet `#FAFBFC`, ink `#202630`, secondary `#566171`, plum `#654D86`, official teal `#20615F`. Dark base: workspace `#14181E`, sheet `#1D232B`, ink `#EDF1F5`, secondary `#A9B5C3`, lavender `#C5ACE5`, official teal `#A3D8D0`.

Typography: same available system sans, 14px task rows and 17px document text, more pronounced 600-weight section labels. Layout: 64px rail by default, 240px contextual index, stronger table separators and 4–6px control corners. No new font package, logo or dependency.

Trade-off: more simultaneous structure suits intensive planning but creates extra borders and a colder reading experience. Narrow selection edges are structural indicators, not decorative stripes. On mobile they must not replace visible labels.

| Decision | Quiet Rhythm | Graphite Studio |
| --- | --- | --- |
| Primary feeling | Calm personal workspace | Precise work instrument |
| A1 continuity | Strong, tiled selection surfaces | Logo preserved, quieter brand in content |
| Long writing | Open 18px text and generous paragraph rhythm | Denser 17px editorial column |
| Task/calendar density | Compact work, quiet surrounding chrome | Stronger separators, more visible structure |
| Risk | Whitespace can grow if headings are not constrained | Extra structure can recreate audit clutter |
| Recommendation | Adopt as the direction for prototype | Keep as an alternative, not a second runtime theme |

Recommend A. Borrow B's disciplined alignment and task columns, not its additional boundary lines. Light/dark are modes of A; they are not A/B concept selection. No A/B preference is recorded as owner approval by this recommendation.

## 2. Shared design language for concept A

### Color roles

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| workspace | `#F6F5F2` | `#171719` | Quiet surrounding plane |
| navigation | `#EEEDEA` | `#1C1C1F` | Recessed shell |
| surface | `#FFFFFF` | `#222225` | Working canvas, menus |
| surface-subtle | `#F0EEEB` | `#2A292E` | Hover, inset property groups |
| text | `#29262E` | `#F0EDF2` | Main text |
| muted | `#64616B` | `#B5B0BC` | Labels and secondary content |
| accent | `#70558E` | `#BCA5D8` | Focus, selected date, primary action |
| accent-on | `#FFFFFF` | `#211A29` | Text on filled accent |
| accent-soft | `#EDE7F3` | `#342C3E` | Selected rows and personal events |
| official | `#246566` | `#A4D4CE` | IIS source text and event label |
| official-soft | `#E5F0ED` | `#243B39` | Official event fill |
| ai-action | `#246858` | `#9EDBC8` | Existing jade Send/source controls only |
| ai-on | `#FFFFFF` | `#152D25` | Text on filled AI action |
| border | `#D8D4DC` | `#49444F` | Separators, calendar geometry |
| control-border | `#857C90` | `#8C8198` | Essential control boundary |
| danger | `#AD2945` | `#FF9AAF` | Errors/destructive text with label |
| success | `#286347` | `#9BD7B0` | Confirmed success with text |

These are proposed sRGB starting tokens, not proof of rendered contrast. Every actual pairing, focus ring and translucent composite needs implementation contrast checks. Color is never the sole status/source indicator. No decorative color assigned to every task priority: use labelled symbols/weight; urgent/overdue may use danger with text.

### Type and rhythm

| Role | Size / line height / weight | Behavior |
| --- | --- | --- |
| Document title | 36 / 44 / 600; phone 30 / 38 | Natural wrapping, no decorative accent word |
| Screen label | 20 / 28 / 600 | Calendar/tasks toolbar, replaces large repeated hero heading |
| Document body | 18 / 30 / 400; phone 17 / 28 | 64–72ch width, paragraph gap 16px |
| Block heading 1/2/3 | 30/38, 24/32, 20/28; 600 | Larger space before than after; levels 4–6 still supported |
| General body | 16 / 24 / 400 | Help and settings prose |
| Task row / control | 14 / 20 / 400–500 | Intentional dense productivity UI, not document body |
| Metadata | 13 / 18 / 400 | Deadline, source, save state; no critical 11px labels |
| Time | 14 / 20 in grid, 32 / 40 in picker | Tabular numerals; no ornamental monospace |

Native stack starts with Segoe UI/system-ui and platform sans fallbacks. Its Cyrillic clarity and lack of font downloads are intentional. No serif imitation of Craft. Use size and weight for hierarchy; avoid stacked uppercase/color/italic emphasis.

Spacing tokens: 4, 8, 12, 16, 24, 32, 48px. Control padding 8×12, menus 8, panel padding 20–24, document gutters 32 desktop/20 phone. A 2px focus ring with 2px offset is distinct from selection. Controls 36px drawn height on fine-pointer desktop, ≥44px hit target for coarse pointer; rows 40–44 desktop/48 touch. Visual density never reduces touch targets.

Corners: 6px buttons/inputs, 8px date/event tiles and selection, 12px floating popovers/dialogs, 16px upper phone-sheet corners. No pill shape for every control. Tables/notes have no enclosing rounded card. Inline inspector uses a divider; only floating surfaces receive shadow. Elevation: base none; popover `0 8px 24px rgba(28,20,36,.14)`; modal `0 16px 48px rgba(28,20,36,.22)` with a neutral scrim. Dark shadows remain subtle and pair with surface boundaries.

Icons reuse existing object-specific SVG style, 18–20px at consistent stroke. A1 export is reused without recoloring or redrawing; retain its light padded background in dark mode. Symbol-only on compact rail, symbol + wordmark on full sidebar; full exported logo only where space makes it useful. No new generated logo or mascot.

### Composition and motion

Use a 216px full sidebar, 64px rail, 52px toolbar and 320–400px inspector depending on screen/task. Calendar uses available width, notes use reading width, tasks use aligned row columns, AI uses conversation width. No shared card grid imposed across those different content structures.

Control feedback 120ms; popovers 160ms; inspectors/sheets 200ms; reorder 160ms. Use opacity and up to 6–12px translation, ease-out, interruptible. No page-load choreography, hover scaling, idle pulsing or glass effects. Reduced motion removes translation; text/selection communicates the same result. Detailed event/state semantics are in the interaction specification.

## 3. Wireframes

These are annotated design proposals with illustrative student content, not screenshots or implemented features. The accompanying [design board](../design/frontend-redesign-board.png) shows concept comparisons, primary screens and custom time entry. Content in that board is synthetic.

### Calendar / desktop, 1440px

```text
┌──────────────────────┬──────────────────────────────────────────┬────────────────────┐
│ A1 Ukladen     Search│ November 2026  Today  ‹ ›  Day [Week]  +  │ Event detail     × │
│ Calendar             ├──────┬─────┬─────┬─────┬─────┬─────┬──────┤                    │
│ Tasks                │Minsk │ Mon │ Tue │ Wed │ Thu │ Fri │ …    │ Prepare report     │
│ Notes / Databases    │08:00 │     │     │ IIS │     │     │      │ [12 Nov]           │
│ Materials / AI       │      │     │     │event│     │     │      │ [09:30 – 10:45]   │
│                      │09:00 │     │ A B │     │▒ new range ▒    │ Personal           │
│ ‹ November       ›   │      │     │ A B │     │▒ 09:30–10:45    │                    │
│ M T W T F S S        │10:00 │     │     │     │     │     │      │ Notes / materials  │
│ … selected day …     │      │     │     │     │     │     │      │ Reminder           │
│ Sources              │11:00 │     │     │     │     │     │      │                    │
│ ☑ Personal  ☑ IIS    │      │     │     │     │     │     │      │ More actions       │
│ ☑ Task sessions      │      │     │     │     │     │     │      │                    │
│ Settings / account   │ … scroll to all hours …                  │                    │
└──────────────────────┴──────────────────────────────────────────┴────────────────────┘
```

A/B denote overlapping interval lanes, not merged events. At constrained width the inspector overlays/replaces context; it must not reduce week columns to unreadable slivers. No permanent agenda below the grid competing with the timeline.

### Tasks / desktop

```text
┌──────────────────────┬──────────────────────────────────────────┬────────────────────┐
│ Shared navigation    │ Tasks  [Status ▾] [Priority ▾] [View ▾] │ Task title       ⋯ │
│                      ├──────────────────────────────────────────┤                    │
│                      │ Loaded: 30 · Load more    + Quick add   │ [In progress ▾]    │
│                      │ To do · 12 loaded                      │ [High ▾] [Due ▾]   │
│                      │ ○ Prepare report       High   Thu 18:00 │                    │
│                      │ ○ Review lecture       Normal Fri 12:00 │ Description        │
│                      │ ▾ Project                               │ editable in place  │
│                      │   ○ Check measurements Low    —        │                    │
│                      │ + Add task…                             │ Subtasks       +   │
│                      │ In progress · 4 loaded                  │                    │
│                      │ ◐ Read paper           Normal Sat 09:00 │ ▸ Related content  │
│                      │                                        │ Plan work…         │
│                      │                                        │ Saved              │
└──────────────────────┴──────────────────────────────────────────┴────────────────────┘
```

Loaded-scope label appears only when non-default presentation needs it; all numbers are illustrative. Clicking a property opens that property; clicking title opens details. Trash/parent move use the menu. No empty relation pagers.

### Notes / desktop

```text
┌────────────┬─────────────────────┬───────────────────────────────────────────────────┐
│ Shared nav │ Pages           +   │ Project / Measurements          Saved        ⋯   │
│            │ ▾ Project           ├───────────────────────────────────────────────────┤
│            │   Measurements      │                                                   │
│            │   Reading notes     │       Measurements                                │
│            │ Personal plans      │                                                   │
│            │                     │       What changed in the experiment              │
│            │                     │       Readable paragraph with a natural line      │
│            │                     │       length. No enclosing form or card.           │
│            │                     │    ⋮⋮ + [active block]                            │
│            │                     │       / Text · Heading · List · Checkbox · Link   │
│            │                     │                                                   │
│            │ Trash               │       ▸ Related events and materials              │
└────────────┴─────────────────────┴───────────────────────────────────────────────────┘
```

Menu offers supported block operations, not a fictitious rich-text toolbar. Document body is the primary focal plane; save state is calm until an error needs attention.

### AI / desktop

```text
┌────────────┬─────────────────────┬───────────────────────────────────────────────────┐
│ Shared nav │ Conversations   +   │ Exam preparation     Model / connection       ⋯   │
│            │ Exam preparation    ├───────────────────────────────────────────────────┤
│            │ Reading plan        │             User question                         │
│            │                     │                                                   │
│            │                     │       Answer, readable prose                      │
│            │                     │       [Sources 2 ▾]                               │
│            │                     │                                                   │
│            │                     │       Proposed tasks [review changes]             │
│            │                     │       [Cancel]               [Confirm]            │
│            │                     │                                                   │
│            │                     │       [Context: 2 sources ▾] [Options ▾]           │
│            │                     │       Ask about your material…                    │
│            │                     │                               [Send / Stop]       │
└────────────┴─────────────────────┴───────────────────────────────────────────────────┘
```

Source-only/no-source/full-document modes are explicit when enabled. No animated AI mascot or fake activity feed. A proposal is visually separated because it changes real content; normal messages are not individually card-framed.

### Custom date/time control

```text
            [Thu 12 Nov] [09:30 – 10:45]     ← two clear editing targets
           ┌───────────────────────────────────┐
           │ ‹ November 2026                 › │
           │ M  T  W  T  F  S  S               │
           │ 9 10 11 [12] 13 14 15             │
           │ Today             Tomorrow         │
           │                                   │
           │ [Start]      End                  │
           │        ↑             ↑            │
           │       09      :      30           │
           │        ↓             ↓            │
           │        hours         minutes      │
           │ [00] [15] [30] [45]   −5 / +5 min │
           │                                   │
           │ 09:30 ━━━━━━━━━━━━━ 10:45   75 min │
           │ Duration   [30m] [1h] [90m]        │
           │ 12 Nov · Europe/Minsk · UTC+03:00  │
           │ Cancel                   Apply    │
           └───────────────────────────────────┘
```

This is a range example; a deadline has no End/duration controls, and time-only work settings have no date calendar. Direct typing of any minute remains the fastest expert path. Date selection/steppers/chips preview only; Apply updates draft, Create/Save persists the event. Full calendar grid has 42 date positions as needed; this wireframe shows a single row for space. Phone uses a full-width sheet with 44px targets and fewer chips per row, not a shrunk desktop popup.

### Tablet, 834px

```text
┌──────┬─────────────────────────────────────────────┐
│ A1   │ November 12   Today  ‹ ›   [Day] Week     + │
│ nav  ├───────┬─────────────────────────────────────┤
│ rail │ time  │ Single readable day                 │
│      │       │                                     │
│      │       │ Event tile, title visible            │
│      │       │                                     │
└──────┴───────┴─────────────────────────────────────┘
```

Day is the recommended first visit at this width; explicit Week remains. Once the user selects Week it is not overridden on every resize. Mini-calendar opens as a popover; detail is a temporary side surface or focused page. Tasks switch to focused detail, Notes collapse the tree, AI collapses history. No three permanent columns.

### Phone, 390px: task and note detail

```text
┌─────────────────────────┐      ┌─────────────────────────┐
│ ‹ Tasks             ⋯   │      │ ‹ Pages    Saved    ⋯   │
├─────────────────────────┤      ├─────────────────────────┤
│ Prepare report          │      │ Measurements            │
│ [To do ▾] [High ▾]      │      │                         │
│ [Thu 18:00 ▾]           │      │ Readable writing body   │
│                         │      │ with a useful width.    │
│ Description…            │      │                         │
│                         │      │ Active block         ⋯  │
│ Subtasks             +  │      │                         │
│ ▸ Related content       │      │ + Continue writing…     │
│ Plan work…              │      │                         │
├─────────────────────────┤      ├─────────────────────────┤
│ Cal Notes Tasks AI More │      │ Cal Notes Tasks AI More │
└─────────────────────────┘      └─────────────────────────┘
```

The list/tree is one Back action away with preserved context. No list stacked above these details. Dock reserves safe area; with keyboard open, primary editing/composer controls remain visible and dock may be hidden to reclaim space without becoming the only exit.

## 4. Component family

- Date tile: A1-derived 8px square corner language; current day outlined, selected day filled; full date in accessible name.
- Object row: common title/meta/menu alignment across tasks, files, search and databases; meaning of each domain still distinct.
- Property chip: compact value + affordance with keyboard focus; no border until interaction unless needed to identify editable input.
- Inspector: title/close, object properties, body, optional related content. Same close/draft rules, different domain fields.
- Time Strip: custom date calendar, tabular segments, labelled steppers and elapsed interval preview. Shared across events, deadlines, sessions and time-only settings through appropriate variants, not one overloaded form.
- Context menu: neutral surface, 6px items, separator before dangerous actions, visible text and shortcut hints.
- Feedback: resource-specific inline state, reversible-action toast only where supported, retained draft on failure.
- Composer/document: flat reading plane, clear editable focus and readable line length; AI's existing jade action does not recolor the entire workspace.

## 5. Explicit changes to the current DESIGN.md direction

Do not overwrite DESIGN.md during concept work: it documents implemented behavior and already contains owner edits. After implementation approval, update only the affected sections with status/date, preserving verification history.

| Current direction | Proposed refinement | Reason |
| --- | --- | --- |
| 60px bar plus large page title | 52px working toolbar, 20px screen label | Recover calendar/task workspace |
| 224px sidebar, secondary tools in More | 216px desktop sidebar with direct knowledge destinations | Findability without extra navigation levels |
| Task list and detail stack below 1100px | Focused detail page at narrow widths | Fix selected-object distance |
| 16px note body | 18 desktop / 17 phone, limited line length | Support long reading and clear paragraph rhythm |
| Native date/time plus separate clock modal | Styled date/time chip and unified anchored Time Strip | Polished controls with precise input and fewer modal layers |
| Manual save with guards | Serialized autosave proposal, guarded pending/error states | Reduce interruption without losing drafts |

These changes are design intent, not statements that implementation already changed.

## 6. Design validation using the requested audits

### Information architecture desk audit

Context: student productivity workspace with paginated tasks, nested notes, databases and optional academic sources.

Critical: none established at the wireframe level. Major risk: desktop sidebar overload when mini-calendar is expanded; use only one contextual sidebar section and test at 1280px. Minor risks: phone More hides databases; loaded-only task grouping needs conspicuous scope. Fixes: stable More order and active destination labels; explicit loaded counts and Load more. Working well: shallow destinations, consistent nouns, owned deep links, search plus browse, optional relations. Top three: restore navigation context; make databases findable; prevent global-sort misunderstandings. Tree testing and short student retrieval tasks are still required.

### Visual aesthetics desk audit

Critical: none established from schematic review. Major risk: the time picker can become an overloaded control if date, range, chips and steppers all receive equal emphasis. Fix: one dominant active time value; compact date grid; muted optional duration row; single accent Apply. Minor risk: a 216px mini-calendar may be too small for touch; move it into the larger picker on coarse pointers. Working well: one primary work plane, aligned rows, readable document scale, limited elevation and restrained A1 accent.

Hierarchy: content precedes tools. Emphasis: primary work action gets fill; menus and rare actions recede. Spacing: related properties share a group, not independent cards. Alignment: row columns and toolbar baseline persist. Proximity: inspector belongs beside selected object. Consistency: one menu/date/feedback language across all four modes. Typography: size/weight carry hierarchy. Depth: only transient layers cast shadows.

Overdesign verdict: **restrained, with the temporal picker as the main density risk**. Do not add a dial, decorative timeline, gradient or additional preview card. Top three visual priorities: protect readable grid width; keep task rows compact; make custom time entry look composed without hiding exact values.

### Acceptance of the concept package

Two distinct concepts and a recommendation are present; desktop/tablet/phone wireframes cover Calendar, Tasks, Notes, AI and custom temporal input; both theme token sets are defined; interaction states and contract limits are specified in the companion. The design board is a static illustration, not a tested prototype. No user study, redesigned browser rendering, keyboard/screen-reader test or measured speed gain is claimed.

Implementation remains stopped. Next authorized stage would be a focused prototype of Calendar + Time Strip and mobile task detail, followed by review before wider production work.

## 7. Verification of this design package

Personally inspected the generated 2000×2410 PNG board and corrected missing-symbol glyphs and the illustrative week-range label. The board uses the installed Noto Sans font for portable Cyrillic rendering; the proposed product font remains the native system stack. Compact boards intentionally omit some navigation utilities and calendar rows; the wireframes/specification define the complete behavior. They are not pixel-perfect implementation measurements.

A local sRGB calculation checked 18 opaque text-token pairings (nine per theme: text/surface, muted/surface, muted/workspace, accent-on/accent, accent/accent-soft, official/official-soft, ai-on/ai-action, danger/surface, success/surface). All were ≥4.5:1; minimum **5.13:1**. This does not validate rendered controls, transparency, focus, icons or the full interface. Local Markdown links and whitespace were checked; `docker compose config --quiet` passed. No frontend/backend tests or build were rerun for these design-only artifacts. The earlier audit's nine browser passes remain historical evidence, not redesigned-interface verification.
