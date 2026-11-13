# Frontend redesign stage 5: databases and collections

Date: 2026-11-13. Status: implemented locally on `frontend/ui`; no merge, push or deploy.
Scope follows the [interaction specification](frontend-interaction-spec.md#9-databases-materials-and-account-surfaces).

## Delivered

Database definitions use compact rows instead of a three-card grid. Detail retains
all existing table/calendar views, saved query editing, property management,
record/page ownership and recoverable lifecycle actions. Row actions are in a labelled
keyboard-accessible context menu positioned within the viewport. The full-record
editor is still available there.

An editable table cell opens an inline single-field form; phones present that same
form in a viewport-bounded bottom panel above the navigation dock. It first fetches the complete
record, pins the initial schema version/definitions and uses the existing field
controls and validation for all seven kinds. Only touched field UUIDs are PATCHed;
unset/hidden fields are preserved. Save is explicit; Escape/Cancel discards the local
edit. Blur does not submit. Failed writes retain entered values. Network failures may
be retried; a real version/schema conflict requires copying the draft, cancelling and
reopening to deliberately fetch current values. No background refetch silently
advances a draft's authority. Pending forms disable inputs/closing and duplicate
submission. Local view/page switches are disabled while a cell is open; dirty forms
participate in workspace navigation and browser unload protection.

Collections/tags retain explicit typed memberships. The page picker now uses the
existing 50-item limit/offset contract and supports selection beyond the first 200
pages. Event options remain honestly scoped to the loaded calendar week. On narrow
screens selection opens the member surface immediately; Back reveals the existing
list and restores its selected-row focus. Collection and database surfaces share
neutral dividers, existing theme tokens, compact headings and 44px mobile controls.
Removing a reference still preserves its page/event; deleting a collection/view does
not delete members. No backend/API/schema/dependency or provider changes were made.

## Scenario changes and review

| Finding | Priority | Result |
| --- | --- | --- |
| Editing one value required opening every field | P1 | Cell → edit → Save in place; full editor remains available |
| Persistent Edit/Trash controls repeated per record | P2 | Labelled row menu; cell itself is the editing target |
| Pages after the first 200 were unreachable in membership picker | P1 | Existing paginated endpoint, reset selection on page change |
| Mobile collection list preceded detail | P1 | Focused detail with Back and focus restoration |
| Hidden/null record fields risk accidental replacement | P1 guard | Fetch complete record; PATCH touched values only; versions retained |

Visual review prioritizes the table/member content over enclosing cards. No new
ornament, statistics, board workflow, formula or unsupported search was introduced.
Keyboard cell entry, native field controls, explicit Save/Cancel and context menus
provide alternatives to pointer actions. Long/wide tables scroll locally.

## Verification

Final lint, typecheck, production build and Compose validation passed. The final
focused Chromium run passed **11 tests (25.3s)**, including light/dark database/collection
layouts at 390/834/1440px, touched-only writes, conflict retention, property option IDs,
date projection and membership selection after page 200. An initial screenshot exposed clipped phone save actions inside the wide table; the
phone panel and viewport assertions fix that. An initial fixture recognized
only the original page membership; it was expanded to model any owned fixture page.
The preceding content run passed 49 scenarios before that fixture mismatch.

[Desktop light](../design/frontend-data-stage-5-desktop-light.png),
[desktop dark](../design/frontend-data-stage-5-desktop-dark.png),
[phone light](../design/frontend-data-stage-5-mobile-light.png),
[phone dark](../design/frontend-data-stage-5-mobile-dark.png) show the rendered inline editor.
Browser tests use
synthetic API routes and credentials; no real backend/provider data is accessed.

## Remaining limits

A schema/version conflict requires deliberate cancel/reopen after copying the edit;
there is no draft merge or silent retry against newer data. Date controls retain the
existing date-only/explicit-offset contract. Global database search, persistent database
selection URLs, saved calendar date moves and automatic persistence are not introduced.
Hardware touch, screen readers, Safari and Firefox remain manual validation work.
