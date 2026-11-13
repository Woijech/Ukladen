# Frontend redesign stage 4: notes

Date: 2026-11-13. Status: implemented locally on `frontend/ui`; not pushed, merged or deployed.
Scope: the notes document surface and page library. Follows the approved
[interaction specification](frontend-interaction-spec.md#7-notes),
[visual direction](frontend-visual-redesign.md), [UX audit](frontend-ux-audit.md) and
[redesign plan](frontend-redesign-plan.md). Database/collection and AI redesign work
remains outside this delivery.

## Delivered behavior

The page is the primary surface: a centered reading column, 18px body text on desktop,
17px on phones, a wrapping/growing document title, six preserved heading levels,
quiet breadcrumbs and compact save feedback. White/dark paper uses the existing
Ukladen tokens and A1 identity. No new typeface, decorative illustration or motion
was added. Context tools appear on hover/focus rather than becoming permanent forms.
The footer still contains the existing event backlinks, child links and materials.

Desktop has a 224px page library. At 1100px and below, Pages explicitly opens a modal
library, leaving the document the full available width. Selecting a page closes the
library after any required dirty-draft confirmation. Title filtering includes matching
pages and their ancestors even when those branches were collapsed; clearing the filter
preserves actual hierarchy/collapse choices. Search is local to all loaded page titles,
not document-body or global search. The existing full-summary pagination remains.

Root/child creation is inline in the library, using only the existing POST contract.
Title input remains after an error or closing/reopening the phone library. The capture
draft also participates in workspace/unload protection. Cancel explicitly discards the
unsent capture. Creating a child never implicitly saves or replaces its parent's dirty
body: the existing save/stay/discard navigation decision is retained.

Slash and plus share a searchable, keyboard-operated insertion menu, now portalled
and bounded to the viewport. Supported commands remain plain text, H1–H6, bulleted/
numbered lists, checkboxes and HTTP(S) links. Markdown remains editable source without
format conversion or rendering changes. There are no fake rich-text, AI, history,
sharing or unsupported-block controls. Existing safe type/list conversions retain UUIDs.
Block actions and page menus are positioned within the viewport. Phone block tools
use a separate trailing gutter; insertion-before is available in the contextual menu.
Checkbox labels provide a 44px touch target around the native checkbox.

Drag/drop indicates insertion before/after a block; labelled up/down actions remain
available for keyboard and touch. Removing a block no longer needs a confirmation
modal. Removal and movement offer one-level local structural undo. Its inverse is
applied to the latest block list rather than a whole-document snapshot, so undoing
structure preserves subsequent typing. A newer structural action replaces the undo
entry; adopting/reloading/changing the document clears it. Undoing removal at the
1000-block limit is disabled rather than exceeding the existing API limit. Page/branch
trash remains separately confirmed and recoverable.

## Saving and failure recovery

Save stays explicit: the button and Ctrl/Cmd+S. Automatic save was a proposed prototype
in the interaction spec and is not enabled by this iteration. Existing drafts remain
memory-only; there is no new local-storage, offline or crash-recovery subsystem.

The draft controller pins the confirmed version separately from query updates. It
updates that baseline after a successful metadata PATCH before sending the document
PUT. If PUT fails, the draft survives and retry uses the advanced version without
another unchanged PATCH. Conflicts retain local content; explicit Reload confirms
replacement. Requests use the existing shared API/CSRF/session handling.

Typing remains enabled during a save. An in-flight snapshot cannot overwrite later
local typing. Without another explicit request, later edits remain dirty. A repeated
shortcut after editing queues a serialized follow-up save; a repeated shortcut without
changes cannot duplicate a request. Pending page navigation completes only when the
current draft is fully saved. Lifecycle/navigation actions remain blocked during a
write, and unmounted editors cannot publish stale save results into another selection.
Discard after a partial save uses the last confirmed server baseline.

## Scenario comparison

Counts include explicit control activations, excluding typing and passive feedback;
these are implementation walkthroughs, not measured participant timings.

| Scenario | Previous | Current |
| --- | --- | --- |
| Create root/child page | Open modal, enter title, Create; 1 modal | Open inline capture, enter title, Create; no creation modal |
| Delete block | Open actions, Delete, confirm; 1 modal | Open actions, Delete; Undo available locally |
| Move block with keyboard/touch | Open actions, choose direction | Same actions, plus optional Undo and viewport-bounded tools |
| Insert supported block | Plus/slash, choose or search | Same short path, menu fits viewport and works with touch |
| Find nested page | Scan/collapse/expand the entire tree | Type title, choose matching page with ancestor context |
| Read on tablet/phone | Page tree consumes document space | Full-width document; Pages opens library on demand |
| Save while continuing to type | Editor disabled during request | Keep typing; later edits remain dirty until explicitly saved |
| Retry failed body after successful title save | Repeat metadata PATCH then PUT | Retry only PUT at confirmed version; retain draft |

## Design and usability review

Review basis: source inspection, mocked-API Chromium interactions, rendered light/dark
screenshots and the current [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).

| Finding | Principle / severity | Resolution |
| --- | --- | --- |
| Mobile library competed with document | Hierarchy / major | Explicit modal library at tablet/phone sizes |
| Fixed-width title could hide long text | Content handling / major | Growing wrapping title, preserving title validation |
| In-row insertion menu could exceed the visible canvas | User control / major | Viewport-bounded portal with keyboard search and touch selection |
| Block confirmation interrupted local composition | Nielsen H3/H7 / minor | Immediate local delete with inverse-operation Undo |
| Retry could repeat already-saved metadata | Nielsen H1/H9 / major | Confirmed version/baseline advanced after each successful write |
| Continued typing could be blocked or replaced by save response | Nielsen H3/H5 / major | Snapshot saves preserve newer draft; explicit serialized follow-up |
| Inline capture could be abandoned silently | Nielsen H5 / major | Included in navigation/unload dirty guard |
| Permanent tooling/strong Save competed with document | Emphasis / minor | Contextual gutter and quiet short Save button |

Overdesign verdict: clean. The document carries the strongest typography; surrounding
controls use existing neutral surfaces and one accent. Top priorities resolved: protect
newer text during saves, preserve version recovery, give the document mobile space.
No unresolved critical/major issue was observed in the exercised scenarios. This is
not a claim of exhaustive accessibility, performance or real-device certification.

## Verification

Executed on 2026-11-13 with local fake API routes and synthetic credentials:

- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm run build`: passed (production build, run outside the restricted process environment after its TypeScript configuration subprocess failed there).
- Full Chromium suite: **287 passed (2.0m)**, including 48 content/notes tests.
- Final animation-disabled notes capture rerun: **4 passed** (320/390/834/1440px, both themes).
- `docker compose config --quiet`: passed.
- `git diff --check` and changed-document file-link checks: passed.

The content suite exercises all existing block types, Markdown/UUID preservation,
keyboard slash search/conversion, drag reorder, hierarchy across paginated metadata,
branch trash/restore, attachments, private deep links, session expiry, conflict reload,
partial-save versions, pending duplicate prevention, newer typing during saves,
explicit follow-up saves, structural Undo preserving later typing, inline create
failure/retry, unsent capture navigation protection and touch insertion/reordering.
Light/dark canvas/menu layouts run at 320/390/834/1440px. Touch is Chromium emulation;
reduced motion, keyboard focus return, rendered text contrast and horizontal overflow
have automated checks in exercised surfaces. They do not replace assistive-technology
or hardware testing.

Reviewed rendered screenshots and retained evidence:

| Viewport | Light | Dark |
| --- | --- | --- |
| Desktop 1440px | [Screenshot](../design/frontend-notes-stage-4-desktop-light.png) | [Screenshot](../design/frontend-notes-stage-4-desktop-dark.png) |
| Tablet 834px | [Screenshot](../design/frontend-notes-stage-4-tablet-light.png) | [Screenshot](../design/frontend-notes-stage-4-tablet-dark.png) |
| Phone 390px | [Screenshot](../design/frontend-notes-stage-4-mobile-light.png) | [Screenshot](../design/frontend-notes-stage-4-mobile-dark.png) |

The initial content run found test flows still targeting the previous creation modal
and always-visible mobile page tree; those flows were updated and passed. A new guard
test initially inspected dialog body text instead of its accessible name; its selector
was corrected. No production workaround was introduced for these test expectations.
Notes screenshot capture disables animations to avoid retaining a transient color frame
during theme switching. The older 2026-10-28 notes/backend history remains separate
from this UI verification.

## Limits and next iteration

No backend/API/DB/dependency, auth/ownership, timezone/DST or provider configuration
changed. Tests use fake APIs; no real AI/provider requests or production data were used.
Large page libraries still load all summaries; lazy branch loading remains a separate
performance improvement. Undo is one-level structural undo, not revision history.
Manual saving and memory-only drafts require a successful save before a browser crash
or forced close. Hardware touch/IME/screen-reader behavior, Safari and Firefox need
separate manual checks. Database/collection redesign remains the next requested stage.
