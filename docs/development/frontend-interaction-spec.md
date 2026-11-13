# Ukladen interaction specification

Date: 2026-11-11. Status: proposed design, not implemented or browser-validated.
Inputs: [UX audit](frontend-ux-audit.md), [redesign plan](frontend-redesign-plan.md).
Visual direction and wireframes: [visual redesign](frontend-visual-redesign.md).

## 1. Product decision

One workspace with four complementary work modes: time, tasks, writing and conversation. Shared navigation, object menus, dates, feedback and focus behavior make these modes feel like Ukladen. References inform interaction, not a requirement for feature parity. All API/session/ownership/version contracts remain authoritative.

The design addresses UX01–16 from the audit. It does not promise rich text, offline persistence, revision history, task boards, recurrence, collaboration or private IIS integration. A1 remains unchanged. Existing functions remain reachable even when secondary controls are collapsed.

## 2. Navigation and information architecture

Desktop navigation is a 216px column with these visible labels, in order:

- A1 Ukladen; Search with command shortcut hint.
- Calendar; Tasks.
- Notes; Databases; Materials.
- AI.
- Collections and tags; Inbox.
- Footer: Home, Settings, account. Home remains available without becoming a dashboard-first entry.

Spacing separates work modes; headings such as “Time” or “Knowledge” are optional accessible group names, not extra navigation levels. Calendar is the initial workspace destination. Schedule remains a Calendar source. Collections never become mandatory parents of notes/events/databases. AI reviews, usage, connections and permitted diagnostics remain under the existing AI/settings scope.

Tablet uses a 64px labelled-on-focus/tooltip rail, plus a navigation drawer with full labels. Phone retains Calendar, Notes, Tasks, AI and More in the labelled bottom dock. More opens a searchable destination sheet with Databases, Materials, Collections/tags, Inbox, Home and Settings, in that order. Search is always available from the top action. Active secondary destination is named in the header and More state. Do not depend on ambiguous icons alone.

### Location, links and return behavior

The canonical object/date/layout query contract is implemented in the 2026-11-13
[deep-link delivery](workspace-deep-links.md): tasks use `section=tasks&task=<uuid>`,
calendar uses `section=calendar&date=YYYY-MM-DD&view=day|week`, pages use
`section=notes&page=<uuid>`, and databases use `section=databases&database=<uuid>`
with optional saved `view=<uuid>` and calendar `date`. Legacy `/workspace?page=<uuid>`
links and dedicated AI routes remain valid. Filter/scroll and broader save-flow
acceptance below remain targets, not claims that those additional behaviors exist.

Navigation and object opening create history entries; transient popovers and typing do not. Filter changes replace the current entry; explicit selection of another date range may push it. Back from a task detail restores exact list filters, loaded rows, selection and scroll within the mounted session. Reload restores the URL's essential context; private drafts/scroll are not promised across reload. Validate URL values, use owned reads, and keep foreign/missing-object handling indistinguishable where required.

If a draft is dirty or saving, intercept internal navigation and show Stay / Save and go / Discard. A failed Save and go never navigates. Browser unload uses the existing browser prompt; do not promise arbitrary custom browser Back interception until implementation verifies it. Do not place private content in URLs or browser storage.

### Search and command palette

Cmd/Ctrl+K opens one 600px-wide surface (phone full-width sheet). Empty query shows explicit commands and current-session destinations; typed query separates Commands from Search results. Command list includes Open Calendar/Tasks/Notes/Databases/Materials, New task/page/event and shortcut help. These commands navigate or open drafts; they never send AI messages or execute destructive operations.

Content results use existing full-text search and owned object opens. No invented fuzzy semantic search, cross-device recents or global task search contract. If task title search is unavailable, do not display a fake global task-search category. Loading, no match, source error and disabled-command reason are distinct. Arrow keys select, Enter opens, Escape closes and returns focus. Visible Search button remains the non-shortcut path. Do not override browser search or composition input.

## 3. Shared interaction rules

| Component | Default / activation | Pending / success | Error / exit |
| --- | --- | --- | --- |
| Inline title | Text with edit affordance on hover/focus; click or explicit Edit enters | Enter commits single line; pending mark scoped to object; confirmed value on success | Escape restores draft snapshot; error retains editor; no blur-triggered irreversible action |
| Property control | Named value, icon and label; opens anchored picker | Choice previews; simple status/priority choice commits once | Version error retains chosen draft; Reload is explicit and warns if draft is replaced |
| Object menu | Visible ellipsis on touch, hover/focus on desktop | Keyboard menu, secondary actions grouped | Escape closes; focus returns to trigger; destructive action uses specific label |
| Context panel | Selected-object title and Close; no scrim on wide desktop | Object loading skeleton preserves width | Retry stays inside panel; closing dirty fields invokes guard |
| Toast | Resource-specific message in live region | “Task completed · Undo” after server confirmation | Failure is persistent inline; toast does not replace recovery UI |
| Confirmation | Only destructive/irreversible or dirty exits | Busy prevents duplicate submit | Cancel always available before mutation; no misleading completed state |
| Filter | Label/value, active count, Clear | Result loading preserves previous context with pending indication | Separate no records from no matches; Clear filters nearby |
| Date/time picker | Formatted value and calendar/clock glyph | Local preview until Apply; outer event Create remains separate | Escape/cancel discards picker edits only; invalid values explain recovery |

At most one anchored popover per surface; opening another closes the first without committing its draft. Nested date/time choices stay within one picker rather than stacking modals. Real modal dialogs retain focus containment and return. No tooltip contains essential instructions or the only label. Forms submit once and retain content on recoverable failure.

Undo is scoped, never universal: local block removal restores the exact draft block/ID/order; task property reversal is a new version-checked write; branch restore uses its supported API. Personal-event DELETE has no restore contract: retain explicit confirmation and do not advertise Undo by recreating a different event. If reversing a write conflicts, show “Could not undo; item changed” and reload options. Do not optimistically claim success before validation completes.

## 4. Calendar

### Working area

Desktop: one compact 52px toolbar, sidebar with collapsible mini-calendar and source list, full-height time grid. Mini-calendar replaces secondary sidebar content while Calendar is active; it does not add another permanent column. At 1440px the 216px sidebar plus optional 320px details leaves about 904px for the grid. If seven readable day columns cannot fit, details overlay the trailing edge or open a focused view rather than shrinking every column indefinitely.

Toolbar: month/year, Today, previous/next, Day/Week segmented switch, New event. Range lives in the toolbar, not in a second oversized heading. Timezone is a readable compact label beside the time axis. Sources include Personal/IIS and current task projection controls; hide/show affects display only. Freshness/coverage warnings stay near the relevant source, not in a global “everything synced” indicator.

Mini-calendar moves selected date and visible range. Arrow keys move one civil day, Home/End move within week, PageUp/PageDown move month; selection requires Enter/click. Today outline differs from selected-day fill. Month navigation alone does not create events. Day/week controls remain visible on every viewport.

### Create, move and resize

- Empty-grid click previews the existing default interval at that position. Drag selects a range in either direction, showing exact start/end and elapsed duration. Release opens a compact event draft anchored beside selection; title receives focus. No POST occurs until explicit Create.
- Drag an existing personal event: ghost remains under pointer, original position stays lightly indicated; destination label follows the real interval. Release commits via current update path; pending state is visible. Escape cancels before release; failure restores authoritative position and offers Retry.
- Resize through top/bottom edge with an expanded invisible pointer target and visible hover/focus handle. Keep original instants and interval identity. Tiny events open details with explicit Start/End; no precision-only handle is mandatory.
- Grid gestures may snap to 15-minute visual increments, but the picker offers every minute. Existing non-quarter-hour times do not round on open or save. Keyboard/form entry is the exact alternative; do not add undocumented modifier shortcuts over existing calendar keys.
- Official events display IIS source/lock text, omit move/resize affordances, and open read-only facts with supported relations/reminders. Do not silently implement official overrides or merge matching subjects.

Overlaps use side-by-side lanes computed from interval intersections. Touching end/start is not overlap. Connected overlap groups share available width; very narrow cards keep time and accessible full name, with full details on open. Cross-midnight/multi-day segments open the original interval. No all-day/recurrent personal-event creation control is introduced.

### Keyboard and touch

Retain current calendar keyboard selection/move/resize behavior and document its actual bindings in help; add no conflicting global single-letter shortcuts. Provide explicit Start, End, Move and Resize commands in personal-event details. On phone default to Day, tap empty space opens a timed draft, tap event opens its detail sheet. Vertical swipe scrolls time and never creates/moves an event. Drag on touch requires an explicit “Move on calendar” mode with Cancel/Apply; ordinary long press may open actions but is not the only path. Details supply equivalent exact fields. A 44px hit region may exceed the event's drawn height without obscuring adjacent event selection.

### Calendar states and acceptance

Empty day: show timeline and one short “Select a time to add an event” hint. No academic profile: personal calendar works, Connect schedule is optional. Stale IIS: label last-known schedule and warn; do not claim availability is verified. Loading preserves grid geometry; errors show retry without discarding drafts.

Acceptance: full 00:00–24:00 access; Day/Week usable at 320/390/834/1440px; selected date follows profile timezone; move/resize/create accessible without dragging; intersections/midnight/repeated-hour cases retain interval identity; official items read-only; hiding sources changes no busy calculations; no mutation before Create or intentional edit commit.

## 5. Ukladen date and time controls

### Recommended design: Time Strip

A custom-styled temporal editor, not an exposed browser `datetime-local` popup and not an analog clock face. The signature is a row of square date/time tiles related to A1: date tile, large tabular hour/minute segments, adjacent endpoint, and a thin interval strip. The geometry communicates a time range, not decoration. The text remains selectable/editable using semantic inputs; “custom” does not mean removing input semantics.

Desktop trigger: `Thu 12 Nov  [09:30 – 10:45]`. Opens one anchored 360–400px popover, flipping within viewport. Phone opens a bottom sheet with the same content and a visible Apply action above the keyboard. Range editing shows Start/End tabs; deadline editing shows a single exact date/time and “Does not reserve time”. Work-window fields use time only and do not inherit event/date requirements.

Within the picker:

1. Compact custom month calendar (Monday first, month/year selector) plus Today/Tomorrow actions. No natural-language parser is required.
2. Start/End segmented control when editing a range. Large `09 : 30` inputs with labelled hour/minute increment/decrement controls. Each segment is directly editable; paste `09:37` into the combined entry path must work.
3. Optional suggested minute chips `00 / 15 / 30 / 45`; selecting one is explicit, never automatic rounding. Smaller “−5 min / +5 min” actions adjust current endpoint, while segment steppers change hour or minute by one.
4. For events, an interval strip and duration chips `30 min / 1 h / 90 min` preview moving End relative to Start. No duration chips for a deadline. The strip is a visual preview, not the only input and not a promise of free-time/conflict coverage.
5. Civil date, timezone and resolved offset summary; Cancel / Apply. Apply updates the outer draft only. The event's Create/Save persists it. A standalone property picker can commit after its own Apply because its edit scope is that property.

An analog clock is not the recommended primary control: 24-hour ambiguity and minute precision add a second mode, and keyboard/screen-reader parity would require duplicate controls. An inert clock glyph can remain as recognition; no decorative ticking dial. A scroll wheel is also not the sole input, avoiding accidental changes while scrolling the page.

### Exact temporal behavior

| Case | Required behavior |
| --- | --- |
| Type `9:37` | Normalize to `09:37` at commit; accept colon-delimited 24-hour digits, not ambiguous prose; validate ranges before Apply |
| Incomplete hour/minute | Permit editing intermediate text; show field error on commit; do not send malformed values |
| Increment 23:59 minute | Wrap clock to 00:00 and show explicit next civil date for dated fields; time-only windows wrap clock but still validate outer window rules |
| Start moves | Default preserve End; if invalid, require explicit new End or “Keep duration” choice; never silently shift dates |
| End earlier than Start | Show full dates and “End must be after start”; an explicit Next day action resolves an intended overnight event |
| Keep duration / duration chip | Preserve elapsed duration across DST; display resulting local date/time/offset rather than assuming a 24-hour day |
| DST gap | Nonexistent wall time is rejected; explain timezone and let user select a valid time; no silent one-hour shift |
| DST fold | Show two labelled occurrence choices with actual UTC offsets; Apply blocked until chosen; existing unchanged occurrence remains selected |
| Existing timestamp with seconds | Opening/closing or saving an unchanged displayed minute preserves original instant/seconds; intentional changed-minute entry is explicit |
| Date-only database field | Date calendar only; never attach midnight or timezone implicitly |
| Invalid date / timezone | Keep draft and error; use profile timezone and existing conversion helpers; browser timezone never silently replaces it |

No provider/parser dependency is needed. Conversion must reuse `calendar-time.ts` and existing explicit-offset DTOs. New picker is a frontend proposal only. Its calendar must expose selected/current/disabled dates accessibly, announce full date and timezone, preserve focus on error, and support direct input as well as stepper selection.

Acceptance: `09:37`, `00:00`, `23:59`, overnight ranges, DST gap/fold, unchanged-second preservation and Cancel all pass; every interactive target is ≥44px on coarse pointers; wheel/scroll cannot alter a focused value unexpectedly; opening a picker never writes; mobile keyboard leaves Apply reachable; date-only values stay dates.

## 6. Tasks

Rows: completion/status affordance, title, priority, deadline and contextual menu. Desktop visual height 40–44px; touch minimum 48px. One line per task where possible, with hierarchy indentation and accessible full title. Statuses remain exactly To do/In progress/Done/Cancelled; no invented team workflow. Priority uses icon plus text in picker; deadline uses readable date/time, not color alone.

Quick add sits after current group/list, not beside a competing full-screen form. Enter creates from title; Escape cancels unsent text; “More details” opens the same draft without losing title. Subtask add works inline under selected parent. Plain task title does not imply parsed dates or AI extraction.

Click row opens a 360–400px nonmodal detail panel; list stays visible on wide desktop. At tablet/phone widths detail is a full working page with Back to tasks and retained list context. Description edits in place; deadline/status/priority use shared popovers. Dependencies, pages, planning and subtask sections appear compactly; empty relations are collapsed and have no pager. Move parent and Trash live in the object menu; branch semantics remain explicit.

### Filtering, sorting and grouping without a new API

Status and priority filters use the existing list endpoint. Presentation menu adds Created order, Deadline and Priority sorting and Status/Priority grouping, but current API is creation-ordered and paginated. Initially non-default sort/group applies only to fetched rows and **must say “Loaded tasks: N · Load more”**; groups show “N loaded”, not a global total. There is no global earliest-deadline promise. Keep this scope visible even inside the display menu; don't ship a misleading “all tasks” sorted view. Full-list global sort/group requires a separate contract decision. Collapsing a presentation group never changes task parents.

Session-only display choices may live in URL; no saved task-view API is assumed. “All active” continues to mean untrashed, including completed/cancelled when the server returns them; do not silently redefine existing filters.

Acceptance: title-only quick add ≤3 operations; completion one activation; row priority change two activations; version-conflict/hierarchy failure retains draft and no false success; successful completion offers guarded Undo; mobile selection immediately exposes title/properties without scrolling past list; filters/pagination and loaded-only display scope are truthful; branch trash/restore and confirmed planning remain intact.

## 7. Notes

Desktop has compact document tree and uninterrupted canvas, with a 64–72ch reading column. Page title is an editable heading; save state and page menu sit at the top, not a repeated tool ribbon. Parent breadcrumbs remain. Phone opens the canvas directly; Pages opens a sheet, never a tall tree permanently above the document. New page creates an inline title draft under the chosen parent and opens its canvas after successful creation; root creation stays available.

Supported contextual block menu: Text, Heading 1–6 (1–3 prominent, 4–6 under More), Bulleted/Numbered list, Checkbox, HTTP link, Move up/down, Delete. Slash and plus open the same searchable menu. Hover/focus reveals grip/plus; touch exposes a persistent block action trigger on the active block. Reorder with drag insertion line and preserved UUID, or explicit Move up/down. Do not change hierarchy by dragging a flat block into another block.

“Contextual formatting” here means supported block type/list style and link editing. No fabricated bold/italic/color toolbar for a schema that cannot store inline marks; no block embeds, subpages-as-blocks or nested lists. Existing Markdown wrappers remain verbatim and are labelled unobtrusively only when relevant to editing.

### Draft and save lifecycle

Mounted in-memory draft → dirty → serialized save → saved. Proposed autosave waits 700ms of idle typing; explicit Cmd/Ctrl+S flushes. At most one metadata/document operation in flight for a page. Subsequent edits queue against confirmed next version. If metadata saves but document fails, retain draft and the advanced version. A stale version stops saving with Retry/Review latest; never auto-overwrite. Loading latest explicitly warns before replacing local content. Dirty/unconfirmed navigation stays guarded.

Local draft undo is available for block deletion and reorder while the editor session remains mounted. It is not backend revision history. No promise of recovery after browser crash/reload, device sync or offline editing; private bodies remain out of persistent browser storage. Failed save retains the mounted draft and offers retry. A future durable-draft feature needs its own storage/privacy decision. Copying draft text for recovery is an explicit user action, not an automatic clipboard write.

Acceptance: all current block types preserve IDs/data; slash and plus keyboard behavior matches; local undo restores deleted content/order; existing Markdown never silently parses/flattens; failed/partial/conflicting save retains draft; phone page switching is guarded; ≥16px document text, readable long notes at zoom; no unsupported formatting controls.

## 8. AI conversation

History is a secondary left list; transcript and composer are the main plane. On narrow screens History opens separately. Header shows conversation title and compact immutable model/connection summary, with settings in a menu. Transcript uses readable 68–76ch text, citations grouped with the answer, and contextual message actions (copy and other already-supported actions only). Do not add speculative edit/resend branches or model-switch behavior unsupported by the chat lifecycle.

Composer: labelled message input, context button with count/scope, optional response settings, Send. Context summary explicitly distinguishes automatic search, explicit sources and no sources. An explicitly empty selection must not silently revert to automatic search. Source picker follows current combined source limits (up to 20 selected pages/materials/databases plus calendar); database selection is not permission to read all page bodies. Enabled full-document/source-only options remain visible in collapsed summary.

State sequence: ready → admitted → generating → completed, with real progress events only. Pending Send becomes Stop; no dancing dots implying tokens before events arrive. Streaming does not animate each token. On disconnect show Reconnecting and read stored state; do not create a new submission. Stop confirms actual stopped/cancelling state without promising provider billing rollback. Inactive/unconfigured AI explains availability without probing providers.

Proposal is a clearly bounded action preview, with affected objects, changes, uncertainty and Confirm/Cancel. Editing a proposal creates a fresh immutable preview under the current contract. Opening context or selecting a starter only edits drafts. No automatic confirmation, no dismissal-as-approval, no “Undo AI” promise for irreversible actions.

Acceptance: no provider call until intentional message submission; this design task and subsequent routine QA use fakes only; no duplicate on reconnect; selected source scope matches actual request; citations/recovery accessible; HITL previews retain explicit confirmation; phone keyboard does not hide composer/Stop; enabled settings and actual model remain identifiable.

## 9. Databases, materials and account surfaces

Databases: direct sidebar entry, compact list of definitions; selected database has table/calendar view tabs, named filter/sort/columns controls and one Add record action. Reuse saved-view contracts. Cell editing commits touched values only after validation; full record details remain available. Property settings use one panel; nulls and stable select-option IDs survive. Date-only/time controls follow section 5. Do not turn records into tasks or introduce formulas.

Materials: rows with file/link, processing state and contextual actions. Upload is one clear action with real bytes/status, reservation-safe retries and limits visible on failure. Attach/detach affects references as defined; no automatic remote fetch or AI run. Search results show type/title/snippet and open owned content. Inbox distinguishes unread/empty/error and preserves existing marking actions.

Account/settings: aligned field rows with contextual help, theme preview, explicit profile timezone and optional group connection. Security/password/Google linking retain their required verification steps. Home remains a utility entry, without new statistics/cards. All existing advanced AI/operator surfaces remain permission-bound and reachable.

Acceptance: hidden record fields not overwritten; selecting membership beyond first 200 uses supported pagination or honestly exposes boundary; deleting a reference does not delete content; upload reservation reused on retry; no settings change triggers AI activation; identity change clears all private drafts and query caches.

## 10. Shortcuts, feedback and responsive policy

| Binding | Proposed behavior / boundary |
| --- | --- |
| Cmd/Ctrl+K | Open palette outside IME composition; explicit Search button equivalent |
| Cmd/Ctrl+S | Save note/current supported editor; prevent browser save only when handled |
| Escape | Close innermost transient surface, cancel local draft/gesture; dirty guard where needed |
| Enter | Confirm single-line edit or selected command; never submit multiline text by accident |
| Shift+Enter | Newline in chat if Enter sends; respect composition; offer visible Send |
| Arrow keys | Move within active list/menu/calendar widget only; no global key capture |
| ? | Help outside editable controls, optional; visible menu entry always available |

Single-letter global create commands are excluded from the initial design to avoid Cyrillic-layout and typing conflicts. Existing calendar-specific bindings remain. Native Cmd/Ctrl+Z inside an input retains browser text undo; the app does not hijack it globally for unrelated server mutations.

Feedback: controls 120ms, pickers/menus 160ms, panels 200ms, local reorder settle 160ms, completion feedback 120ms. Ease-out on arrival; no spring bounce on productivity rows. Motion only opacity/transform, no layout-sized entrance animation. Input is never locked until an animation finishes. Reduced motion removes translation/reorder animation; state text and focus remain. Unknown-duration work uses a status label, not fabricated percentages.

Desktop ≥1280: full sidebar, optional inline inspector if content minimums fit. Tablet 768–1279: rail, secondary indexes collapsed, one primary plane plus temporary inspector. Phone <768: single work plane, dock safe area, details as page or explicit sheet, all popovers constrained to viewport. At 200% zoom apply the same available-width rules. Widths are prototype targets to validate, not implemented breakpoints.

## 11. Before / after scenario comparison

Same counting convention as audit: field entry is one operation; waiting/scroll excluded. New counts are design targets, not measured results.

| Scenario | Current | Proposed | Safety retained |
| --- | --- | --- | --- |
| Basic quick task | Focus, title, submit: 3 | Same 3 | No automatic date/AI parsing |
| Complete task | Checkbox: 1 | Same 1, Undo feedback | Version/hierarchy validation |
| Change priority from row | Select, Edit, choose, Save: 4; modal | Priority, choice: 2; popover | Expected version, failure draft |
| Open task on phone | Select then scroll below list | Select: detail appears; Back restores list | Filters/selection retained |
| Create page | Plus, title, submit: 3; modal | Plus, inline title, Enter: 3; no modal | Title validation, explicit parent |
| Switch page after text edit | Edit, select, guard, Save and go | Edit, select after confirmed autosave; guard still on failure | Partial-save/conflict protection |
| Exact event time | Browser datetime UI or separate picker | Date/time chip, edit `09:37`, Apply; Create separately | Any minute, timezone/DST |
| Delete block | Menu/Delete/confirm: 2–3 | Menu/Delete: 2; local Undo | Recover exact draft content |
| Open database from primary mode | More, Databases, database: 3 | Databases, database: 2 desktop; phone remains 3 | Same domain ownership |
| Ask AI | Focus, message, Send: 3 | Same 3, clearer context | Scoped source reads, HITL |

## 12. Design review and implementation gates

IA audit of proposed structure: no critical finding in desk review. Major risk: too many persistent desktop labels can compete with the mini-calendar; mitigate with spacing and a single contextual sidebar section, test 1280px. Minor: More still hides phone Databases; use stable ordered labels and test tree findability. Minor: loaded-only task groups may be misunderstood; keep scope prominent and evaluate before shipping. Working well: shallow destinations, real links, multiple paths through search/tree/context, no mandatory organization. Top three IA priorities: reliable deep-link/history, database findability, truthful task-list scope.

Aesthetics audit lives in the companion visual document. Neither desk review is usability validation. Before implementation approval, review the concept and key time-picker behavior; no new external/provider action is implied. During implementation test: 320/390/834/1024/1440px, both themes, 200% zoom, keyboard/screen reader, real phone keyboard, 30+ tasks, 200+ pages, long Cyrillic text, overlap and DST fixtures. Run relevant existing checks and focused new tests; this specification makes no claims that redesigned UI tests already pass.

### Cross-surface acceptance checklist

| Area | Review gate before release |
| --- | --- |
| Navigation/search/palette | Every existing destination reachable; deep links/back restore essential state; no private text in URL/storage; command execution never submits AI or deletes content; loading/no match/error differentiated |
| Shared controls | Mouse, keyboard and touch complete the same action; 44px coarse-pointer targets; semantic labels, focus return, live feedback, retained error drafts; reduced motion equivalent |
| Temporal controls | Every minute selectable; dates and exact timestamps remain distinct; DST/overnight/original-second cases verified; no writes from opening/cancelling a picker |
| Responsive shell | No document-level horizontal overflow at 320px/200% zoom; calendar/table overflow stays local; keyboard does not hide Apply/Send; no list-before-detail on narrow screens |
| Theme/identity | Light/dark/system remain complete; A1 unchanged; text/control/focus contrast verified on actual rendering, not only tokens |
| Security and lifecycle | Session change unmounts private state; all writes use existing application/API protections; real provider activation remains outside scope |
