# Frontend redesign stage 3: tasks

Date: 2026-11-13. Status: implemented locally on `frontend/ui`; not pushed, merged or deployed.
Scope: task queue, properties, capture and contextual detail. This follows the owner-approved
[interaction specification](frontend-interaction-spec.md#6-tasks),
[visual direction](frontend-visual-redesign.md) and [UX audit](frontend-ux-audit.md).
Calendar verification remains in its [separate report](frontend-calendar-refinement.md).
Notes, databases and AI redesign iterations remain outside this delivery.

## Delivered interactions

The queue uses compact aligned rows rather than large two-line cards and an empty
half-width detail placeholder. Desktop rows have a 44px minimum height, completion,
title, status, priority, deadline and a contextual action trigger. Phone rows use two
levels with 44px property targets; priority retains its labelled picker and accessible
current-value description while its row representation uses a symbol. Long titles
use ellipsis and retain full accessible names/tooltips. Both themes reuse the existing
A1/system-font/plum identity and existing status colors.

- Completion remains one activation. Status and priority each use a compact anchored
  picker: activate the row property, choose an option. A successful write closes it;
  conflicts remain visible with an explicit current-version reload. No full edit form
  is required for these actions.
- F2 or the contextual Rename action edits the title inside the row. Enter saves,
  Escape cancels, and a failed save retains the draft. Inline text editors retain
  their starting task version until an explicit reload; background refetches cannot
  silently authorize an overwrite on retry. Explicit rename focuses the
  input after a menu closes. There is no implicit blur save.
- Deadline editing reuses `CalendarMonth` and existing calendar-time conversion helpers
  in a small temporal dialog, switching to a phone bottom sheet. The editable clock
  accepts `09:37`, `9:37` and numeric-keyboard `0937`. Every minute remains available;
  clearing a deadline sends explicit null. Opening/cancelling never writes. DST gaps
  are rejected, folds require an explicit offset, and unchanged seconds are preserved.
- Quick add creates from title with Enter, clears only after success and returns focus
  for repeated capture. Escape clears an unsent title. More details and New task carry
  the current title into the existing full form; dismissing that form retains quick
  text. Plain titles do not parse dates or invoke AI.
- If a newly created task falls beyond the loaded creation-ordered pages, its success
  notice offers Open created task. This avoids inventing a different list order or
  losing access to a capture while retaining loaded-only presentation semantics.
- Description edits in place through an explicit Save/Cancel path. Title-only subtask
  capture is inline in the selected parent's detail; it keeps the parent selected and
  posts the existing `parent_id`. The full subtask form remains available for effort,
  remaining work, description and other fields.
- Parent move and branch trash live in the detail's Actions disclosure. Branch-trash
  confirmation and batch-root restore rules remain. Restoring invalidates parent/child
  detail caches so an old trashed-parent snapshot cannot block a restored child.
- Empty dependency/page sections are collapsed. Their controls remain inside the
  disclosures; actual relations, warnings and errors expand them. Unused pagers in relationship lists and the parent picker are omitted. Sources/provenance, page links, deterministic planning, sessions
  and explicit remaining work remain available without activating an AI provider.

Native dialogs provide focus containment and return. Row actions use a top-layer
context dialog, so the menu is not clipped by the queue's scroll container. Full
forms and hierarchy pickers retain their existing API paths.

## Loaded data, filters and presentation

Status and priority filters use the existing server query. The queue loads 30 records
at a time through `useInfiniteQuery`; Load more retains earlier pages. Loaded count
is visible next to search; presentation controls explicitly say they apply only to
loaded tasks. Search is also explicitly labelled as searching loaded tasks.

Presentation supports no grouping, Status grouping and Priority grouping, plus the
existing creation order, Deadline and Priority sorting. The backend's default order
is ascending creation date/ID; this implementation preserves it rather than claiming
newest-first or global earliest-deadline order. Ties retain loaded order. A task can
appear in a different presentation group without changing its parent. Group counts
are loaded counts, not totals. Hidden/collapsed groups do not edit or remove tasks.

Requests use only existing `limit`, `offset`, `status`, `priority` and `trashed`
parameters. No saved-view, global task search/sort API, board workflow or task schema
is introduced. Active continues to mean untrashed, including done/cancelled tasks
unless a status filter excludes them.

## Detail, navigation and keyboard

At widths above 1100px, selection opens a 380px detail surface next to the queue.
At tablet/phone widths it immediately shows a focused detail surface with Back,
keeping the queue mounted. Back restores row focus, list position, filters and loaded
pages. A generic empty detail panel no longer consumes half the workspace.

Within a focused queue row: Up/Down move row focus, Enter opens details, F2 renames,
S opens Status, P opens Priority, D opens Deadline and N focuses quick add. These are
scoped task-list bindings; typing in inputs/textareas/selects and other sections is
not intercepted. Escape closes the relevant dialog/menu or returns from task detail.
A visible keyboard-help disclosure documents the bindings.

Inline titles/descriptions, quick titles and full-form drafts participate in the
existing workspace dirty-navigation guard and a native unload guard. Changing a
local filter/group/search or abandoning details asks before discarding edits.
Pending writes are guarded; failed writes do not claim success or discard local text.
The existing full form now guards dirty dismissal and blocks duplicate submissions.

## Writes and Undo

Row edits PATCH only the changed property and `expected_version`; description and
other fields are not copied from a summary response. Confirmed creation uses only
title (plus explicit parent for a child). Existing auth/CSRF/session/ownership behavior
is reused through `writeJson`.

One-step Undo applies the inverse property change against the version returned by the
successful write. A later external change causes a conflict rather than an overwrite.
Undo does not fabricate branch restore or recalculate completed task hierarchies;
normal backend validation applies. A subsequent mutation replaces the prior Undo.
Full-form saves, capture and trash/restore are not advertised as generic Undo actions.

## Scenario comparison

Activations below count button/keyboard commits and field focus, excluding the text
itself. These are implementation-path counts, not timings or results of a user study.

| Scenario | Before | Delivered |
| --- | --- | --- |
| Set priority/status | Open row, Edit, open select, choose, Save: about 5 | Property, choice: 2; no detail transition/full form |
| Complete | Existing checkbox: 1 | Checkbox: 1, plus guarded Undo |
| Rename from focused row | Open detail/Edit/focus/Save: about 4 | F2, Enter: 2, editing inside row |
| Title-only capture | Existing quick field + Enter | Preserved; focus retained, More details carries text |
| Add simple child | Open parent, child modal, fill, Create | Parent detail, inline title, Enter; no creation modal |
| Read selected task on phone | Select, scroll below the list | Select: focused detail immediately; Back restores queue |
| Move/trash | Permanently visible detail buttons | Actions disclosure; same picker/confirmation/contracts |
| Group/sort loaded tasks | Unavailable | Presentation menu; explicit loaded scope and Load more |

## Acceptance and verification

Final executed checks:

- `npm run lint`: passed, no warnings.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- `docker compose config --quiet`: passed.
- `npm test -- --workers=4`: **280 passed (1.8m)** on the final production build,
  including 23 new task scenarios. This includes description focus return and
  fixed edit-start versions across background refetch/conflict/retry.
- Changed-document local file links: **187 passed**; `git diff --check`: passed.

Final populated captures are from that passing run. No production-code changes
were made after it.

| Section | Acceptance evidence |
| --- | --- |
| Row properties | Minimal PATCH payloads, original expected version, picker conflict/reload, success-only close |
| Inline text | F2/Enter/Escape, failed-draft retention, pinned edit versions, explicit reload, scoped typing, description-only PATCH |
| Capture/hierarchy | Focus retention, title transfer, inline child POST, parent move and branch restore regressions |
| Data presentation | 30→34 loaded records, grouping/sort/search scope, no writes on presentation changes |
| Deadline | Arbitrary minutes, null, gap/fold choice, unchanged seconds, no implicit save |
| Feedback/Undo | Stale Undo conflict, pending single-flight and no mid-save dismissal, API error/retry paths |
| Responsive UI | 320/390/834/1440px, both themes, property Apply in viewport, phone date targets ≥44px |
| Navigation | Immediate compact detail, Back focus/filter/scroll restore, dirty filter and workspace guards |

The earlier targeted run passed 31 scenarios. Intermediate runs exposed selectors
that matched a new display control, the existing custom navigation-confirmation
surface, and an inherited stale parent-detail cache on restore. These were corrected;
failed/intermediate runs are not passing evidence. The first full run had 277
passes and one test assertion that read the PATCH counter before CSRF retrieval
finished; that assertion now waits for the actual request. Snapshot readiness was
also tightened so the queue captures show loaded rows rather than the lazy-loading skeleton. Production build/type errors and
lint findings were resolved before the final run.

Browser API traffic is fully mocked, including tests of AI screens. No real provider
call, dependency installation, backend/API/DB change, migration, push, merge or deploy.
Backend checks/live integration were not rerun because backend contracts are unchanged.
The working tree includes owner changes; only this stage's changes enter its commit.

## Heuristic and visual review

- Nielsen #5, error prevention: explicit versioned writes, local draft retention,
  dirty navigation and guarded pending saves. Existing branch confirmation remains.
- Nielsen #7, efficiency: row properties, inline text/capture and scoped accelerators
  remove the full-form path for frequent edits.
- Nielsen #1, status: pending/success/conflict feedback and visible loaded counts avoid
  implying persistence or global sort before it exists.
- Visual hierarchy: one queue with optional context. Selected rows use the existing
  plum surface; status/priority are compact metadata rather than large colored cards.
  Phone properties fit below the title without horizontal document overflow. The
  queue scrolls in its own flexible region and quick capture stays in the viewport.
- Web Interface Guidelines (reviewed files: `task-controls.tsx:25`,
  `task-controls.tsx:76`, `tasks-panel.tsx`, `tasks-panel.css:252`): semantic controls/labels, top-layer menu focus, explicit
  keyboard/touch paths, local overflow and native theme-aware selects. Existing global
  focus and reduced-motion rules remain; no new animation or dependency is introduced.

Overdesign verdict: restrained. Top three delivered priorities are direct property
editing, immediate compact-screen detail, and truthful loaded-data presentation.

## Remaining limits

Task selection and presentation preferences remain mounted UI state, not a newly
persistent task URL/saved view. Browser Back between workspace sections retains the
existing guard; no new task-object history contract is claimed. Loaded-only sort and
search are not global queries. Quick add beyond a loaded page offers the captured
object directly but does not silently change the server's creation ordering.

Testing uses Chromium and synthetic HTTP fixtures. Physical-device virtual keyboards,
screen readers, Safari/Firefox, high contrast and 200% zoom remain manual release checks.
No general accessibility certification or measured productivity gain is claimed.
Complex creation/effort edits retain the full form and its native exact deadline input;
the custom temporal surface is the default fast row/detail deadline path.

## Inspected renders

Actual Chromium renders with synthetic data are saved after final verification.

- [Desktop light queue](../design/frontend-tasks-stage-3-desktop-light.png)
- [Desktop dark queue](../design/frontend-tasks-stage-3-desktop-dark.png)
- [Desktop contextual detail](../design/frontend-tasks-stage-3-detail-desktop.png)
- [Phone queue](../design/frontend-tasks-stage-3-mobile-light.png)
- [Phone focused detail](../design/frontend-tasks-stage-3-detail-mobile.png)
- [Phone deadline editor](../design/frontend-tasks-stage-3-deadline-mobile.png)
- [Tablet dark queue](../design/frontend-tasks-stage-3-tablet-dark.png)
- [Loaded priority grouping](../design/frontend-tasks-stage-3-grouped.png)

Personally inspected populated queue/detail/deadline/group layouts. The final captures
wait for task rows after reload; loading-skeleton captures are not presented as the
finished queue. The final full run includes description focus return, pinned edit versions and capture readiness.
