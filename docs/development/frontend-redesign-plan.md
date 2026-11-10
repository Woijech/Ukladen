# Ukladen frontend redesign plan

Date: 2026-11-11. Status: proposed, not implemented. Implementation requires a separate request.
Evidence and issue IDs: [frontend UX audit](frontend-ux-audit.md). Product requirements remain authoritative in [workspace specification](../product/workspace.md); this plan does not replace them.

## Intended result

Make capture, editing and returning to work faster while retaining Ukladen's A1 identity and existing data contracts. Focus on object workflows and content density. Keep the current warm paper/plum visual language, official-source teal, system typography and both themes. Do not introduce a design dependency or change backend/API/database behavior as part of this plan.

## Sequence and acceptance gates

| Slice | Scope / files | Acceptance |
| --- | --- | --- |
| 1. Navigation and mobile task continuity | UX01/02/16; `workspace.tsx`, `navigation.tsx`, `tasks-panel.tsx/.css`, routing entry points | Reload restores section and selected task; Back restores list/filter/scroll; real links support new tabs; unsaved notes still block unsafe transitions; phone selection shows detail immediately with a clear Back action. |
| 2. Task editing and hierarchy | UX03/04/12; `tasks-panel.tsx`, `task-relations.tsx` | Change priority in at most two activations from row; deadline/status edits preserve versions and timezone; empty relations collapse; no empty pagers; parent move/trash remain accessible in object menu; accidental dismissal retains or guards drafts. |
| 3. Notes composition | UX05/06/09/15; `panels/notes.tsx`, `note-blocks.tsx`, shell status | Create a page inline; distinguish first-use and no-selection states; truthful resource-specific save status; background-save prototype passes partial failure/conflict tests before reducing guard frequency; undo exists before block-delete confirmation is removed. |
| 4. Calendar working area | UX07; calendar shell/card/layout CSS | Compact date toolbar; compare day/3-day/week at 834/1024px using dense fixtures; selected event exposes full title; pointer and keyboard manipulation remain equivalent; no hidden source changes availability. |
| 5. Knowledge organization and database editing | UX08/10/11; navigation, organization, database panels | Stable desktop knowledge group; discoverable mobile destinations; choose items beyond first 200 via current APIs where feasible; edit a cell without full record modal; unchanged hidden/null fields preserved. |
| 6. Cross-surface refinement | UX13/14; shared controls, AI CSS, resources/settings | Important metadata readable at zoom; menus and errors correctly announce; retain direct time entry; decide optional picker based on prototype task performance; check uploads/search/inbox and AI fixtures in both themes. |

Each slice is independently reviewable. Prefer one cohesive local commit per verified implementation slice. No later slice is authorized merely by completion of an earlier one.

## Interaction specifications

### Navigation

Define one URL convention for section, selected object and essential view context before coding. Reuse existing page-link and AI-route behavior; do not break private page links. Parse untrusted URL values and preserve ownership handling. Browser Back must pass through dirty-document protection. Do not persist private document content in localStorage. Search stays globally available and opens owned objects into their normal context.

Prototype desktop groups: Calendar/Tasks, Notes/Databases/Materials, AI; Search/Inbox and Settings/account as utilities. Keep Collections/tags discoverable without forcing organization. Phone keeps the labelled primary dock and More. Validate grouping with a tree test before replacing the existing navigation labels.

### Tasks

Use the existing quick-add field as the primary capture path. Full creation remains available for complex input. A desktop row exposes completion, title and compact status/priority/deadline; secondary actions appear in a focusable menu. On touch, provide an explicit menu trigger rather than hover-only affordances. Mobile selection opens a dedicated detail surface, not details after all rows.

Edit status/priority through small anchored controls. Title editing uses Enter to save and Escape to cancel; multiline description retains normal Enter behavior. One pending operation per edited object prevents stale writes. Failure retains the draft and states the next action. Hierarchy errors must not show a false completed state. Keep exact deadlines distinct from scheduled sessions.

### Notes

Inline page creation keeps parent choice explicit. Preserve slash/plus menu, stable block IDs, keyboard reorder and legacy Markdown bodies. Block actions should appear on hover **and focus**, with a touch trigger. Local undo must restore content and ordering before replacing per-block confirmation. Branch trash stays protected and recoverable.

Background saving is a proposed engineering change, not a CSS adjustment. Prototype a serialized save queue against current metadata/document endpoints. Handle metadata success followed by body failure; keep the advanced version on retry; never silently overwrite a conflict. Show Saving/Saved/Not saved adjacent to the document. Retain Cmd/Ctrl+S and navigation/unload guards until persistence succeeds. No rich-text schema migration or collaboration in this scope.

### Calendar

Keep slot selection, drag/resize previews, keyboard controls and explicit create submission. Prototype an anchored minimal title/time editor only if it improves capture without obscuring the chosen interval; retain full details. Compact tools should free vertical space rather than remove source warnings. Use labelled source controls and visible timezone. Official facts remain read-only in the current frontend scope. Saved mixed calendars and override editors require a separate feature request.

### Databases and organization

Cell editing uses the current full-record fetch and touched-field PATCH semantics. Commit text with Enter/blur only with a clear pending state; Escape restores draft. Do not convert nulls to empty strings or replace stable option IDs. Keep record detail for multi-field work. Group schema management in one surface instead of adding nested dialogs.

Membership pickers show title, object type and relevant date/source. Load additional authorized choices through existing pagination; investigate existing filtered reads before proposing search endpoints. If current API cannot express selection efficiently, document the gap and stop that feature boundary; do not modify the backend under a UI slice. Removing membership must never delete the referenced object.

### AI and utilities

Preserve source scope, citations, stop/recovery, immutable proposal previews and explicit confirmation. Hide advanced configuration through labelled progressive disclosure while leaving enabled modes visible in the summary. Settings/diagnostics must not steal focus from chat composition. Starter prompts fill drafts only. All implementation verification uses fakes/synthetic credentials; no activation, real model requests or provider probes are authorized.

Materials retain upload reservation/retry and trash recovery. Search retains plain-text snippet rendering. Inbox actions retain CSRF/session isolation. No new dashboard or landing-page treatment is needed.

### Keyboard and motion

Keep current calendar keys, slash navigation and Cmd/Ctrl+S. Prototype a discoverable shortcut help surface and quick-create/search commands, avoiding browser/system bindings and text-entry contexts. Do not copy Linear's single-letter C globally without input/IME checks. Every drag action retains a non-drag alternative. Menus support Escape and focus return; shortcuts are accelerators, not the only path.

Use the existing finite feedback transitions. No animation is required for a static work surface; reduced motion remains supported. Do not add ornamental cards or motion to imply progress.

## Validation required during implementation

For each slice run relevant existing mocked Playwright cases plus frontend lint/typecheck/build and Compose configuration validation. Add focused checks only for new behavior. Preserve calendar DST, original intervals, conflict handling, dirty navigation, branch restore, identity isolation and AI confirmation coverage.

Capture desktop 1440, tablet 834/1024 and phone 390; include narrow 320 and 200% zoom for targeted checks. Test both themes, system theme changes, keyboard focus, reduced motion, long Cyrillic titles and content-heavy data. Inspect captures rather than equating screenshot generation with visual approval. Physical phone keyboard and screen-reader checks remain separate gates.

Measure before/after using identical starting states: quick task creation (already 3 operations), completion (already 1), priority change (4 → target 2), page creation (3 → target 2–3 without modal). These are prototype targets, not measured speed gains. Track errors and recovery alongside counts; reducing clicks is not sufficient if it increases accidental writes.

## Explicit boundaries

No backend/API/schema changes, new dependencies, formulas, collaboration, private IIS integration, automatic subject grouping, AI activation or functional deletion. A1 and standalone content remain. Accessibility checks are required before release; the audit's nine passing browser scenarios do not establish complete conformance.

Stop here for design review. The current task delivers documentation only.
