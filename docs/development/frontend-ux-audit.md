# Ukladen frontend UX/UI audit

Date: 2026-11-11. Status: evaluation complete; recommendations are not implemented.
Scope: productivity application, not the public landing page. Companion: [redesign plan](frontend-redesign-plan.md).

## Executive assessment

The largest opportunity is to reduce the distance between choosing an object and working on it. Ukladen already has useful direct manipulation and a coherent A1 visual identity. A palette replacement would have much less value than fixing mobile task selection, navigation history, repetitive editing dialogs and the density of secondary controls.

No P0 blocker was established in this bounded audit. P1 denotes recurring friction in a core workflow; P2 denotes secondary friction or a hypothesis requiring validation. Priority is separate from Nielsen severity: Critical means blocked completion/data loss, Major means recurring substantial friction, Minor means recoverable friction. No population-level usability or time-to-completion claims are made.

## Evidence and limits

Reviewed the working tree, including pre-existing uncommitted frontend changes. Read AGENTS.md, DESIGN.md, SYSTEM_ARCHITECTURE.md, frontend architecture, documentation map, product overview/workspace/open decisions and roadmap excerpts. Used CodeGraph first to locate implementation and call relationships, then targeted source/CSS/tests for details. Applied the heuristics, information architecture, aesthetics and Web Interface Guidelines skills.

`docs/design/references/` does not exist. Reference comparisons below use official documentation, not supplied screenshots or authenticated reference-app sessions.

Fresh production build and existing mocked Playwright scenarios ran against Chromium. No dependency installation, backend changes, real AI calls or real user-data mutations were required. Mock mutations occur only in test memory. Generated screenshots are under `apps/web/test-results/`, ignored and replaceable by the next test run.

Browser coverage: responsive workspace scenarios at 1440×1000, 834×1112 and 390×844; secondary-section scenarios at 390/1024/1440px in light/dark. These are desktop Chromium viewports, not evidence of real iOS/Android behavior. Personally inspected seven fresh captures: desktop light task details and note editor; phone light task details; tablet dark calendar; desktop dark notes index; desktop light database index; phone dark notes index. Other generated captures were not individually visually inspected. AI is source-reviewed here, not visually validated. Screen reader, 200% zoom, virtual keyboard and physical touch-device checks remain open.

### Reproducible verification

- `npm run build`: passed, current working-tree source.
- `npm run lint`: passed.
- `npm run typecheck`: passed.
- `npm test -- --grep 'responsive navigation, theme and modal fit|design system covers secondary|quick task creation|calendar click creates|slash and plus' --workers=2`: **9 passed (37.3s)**.
- `docker compose config --quiet`: passed.
- Backend checks and the full frontend suite were not run: this task changes documentation only.

The selected scenarios test layout bounds, theme behavior and mocked interactions; passing them is not WCAG certification. `tests/design-checks.ts` checks rendered direct text-node contrast and page overflow, but does not cover all icon/border/focus contrast, accessible names or screen-reader announcements. Historical checks in existing design reviews were not rerun by implication.

## Screen and navigation map

| Entry/surface | Current destinations and work | Key implementation |
| --- | --- | --- |
| `/` | Public entry to workspace | `src/app/page.tsx` |
| `/workspace` signed out | Login/register, Google, password recovery | `workspace/workspace.tsx`, shared auth |
| `/auth/*` | Completion, verification, reset, Google linking/error | App Router auth pages |
| Workspace shell | Calendar, Notes, Tasks, AI; More → Home, Materials, Databases, Collections/tags, Search, Notifications; Settings/account footer | `workspace/navigation.tsx`, `workspace.tsx` |
| Calendar | Day/week, sources, selected-day context, event detail/form, reminders, linked content, task projections | `workspace.tsx`, `calendar-selection.tsx`, `calendar-card.tsx`, `event-detail.tsx` |
| Tasks | Active/trash, status/priority, quick add, row completion, detail, full editor, parent picker, relations, planning | `tasks-panel.tsx`, `task-relations.tsx`, `task-planning.tsx` |
| Notes | Tree/trash, page canvas, blocks, page menu, relations/materials, guarded navigation | `panels/notes.tsx`, `note-blocks.tsx` |
| Databases | Index/trash, records, properties, saved table/calendar views, view/record/settings dialogs | `panels/databases.tsx` |
| Resources | Materials/upload/bookmarks, search/snippets, notifications | `panels/resources.tsx`, `attachments.tsx` |
| Organization | Collections/tags, explicit page/event references | `panels/organization.tsx` |
| AI | Chat/history, sources, proposals, settings, usage, reviews, diagnostics when permitted | `panels/ai*.tsx`; dedicated `/workspace/ai` and `/workspace/ai/usage` entries |
| Settings | Profile, avatar, timezone, academic connection, account actions | `views.tsx` |

Most section/object selection is mounted React state inside `/workspace`, with a page-link query exception. The AI route exceptions do not provide general task/database deep linking. Schedule is a source within Calendar, not a missing standalone screen.

## Flow inventory and interaction cost

Counts below are source-derived minimum operations for a named starting state, not observed user averages. One field entry/selection counts as one operation regardless of keystrokes. Scrolling and waiting are excluded and identified separately. A transition means a section/object change, not necessarily a URL change. Optional fields increase counts.

| Scenario and start | Current minimum operations | Transitions / forms / dialogs | Proposed target |
| --- | --- | --- | --- |
| Add basic task from Tasks | Focus quick input, enter title, submit: 3 | 0 / 1 / 0 | Keep 3; focus shortcut may reduce to 2 |
| Complete visible task | Checkbox: 1 | 0 / 0 / 0 | Keep 1; preserve failure recovery |
| Change priority from task list | Select task, Edit, choose priority, Save: 4 | 1 / 1 / 1 | Row property → choice: 2, no modal |
| Create subtask from selected detail | Add subtask, title, submit: 3 | 0 / 1 / 1 | Inline title/submit: 2–3, no modal |
| Add event from visible grid | Select slot, title, submit: 3 | 0 / 1 / 1 | Keep prefilled interval; optional anchored editor |
| Move/resize personal event | Drag and release: one gesture; keyboard alternative exists | 0 / 0 / 0 | Preserve, do not rebuild |
| Create page from Notes tree | Plus, title, submit: 3 | 1 / 1 / 1 | Inline title then canvas: 2–3, no modal |
| Edit text then switch page | Select page, edit, select another, Save and go: 4 | 2 / canvas + guard / 1 guard | Save queue could remove guard on successful persistence |
| Delete block, already located | Open block actions if needed, Delete, confirm: 2–3 | 0 / 0 / 1 | Delete + local undo; retain safe fallback |
| Open database from primary section | More, Databases, database: 3 | 2 / 0 / 0 desktop; navigation dialog on phone | Direct desktop library entry: 2 |
| Edit record, database already open | Open record, edit value, Save: 3 | 1 / 1 / 1 | Cell edit and commit: 2–3, full editor retained |
| Add collection page reference | More, organization, collection, member controls, page choice, submit: at least 6 | 2+ / membership controls / conditional | Searchable contextual picker; confirm exact path in prototype |
| Ask AI in an existing ready chat | Focus, enter text, Send: 3; source/options extra | 0 / composer / 0 | Preserve; no automatic provider submission |
| Manual task planning | Open planning, configure scope/time, preview, inspect/select, apply | Conditional; multiple fields, planning dialog | Keep preview/apply boundary; do not invent a fixed count |

Auth, upload and planning have conditional recovery/verification branches, so a single exact click total would be misleading. Upload remains choose file → upload/reservation → completion; retries must retain reservation identity. Google/mail verification steps protect identity and are not removable cosmetic friction.

## Prioritized findings

Paths below are relative to `apps/web/src/`. **S** = source-confirmed behavior; **V** = personally inspected fresh capture; **H** = research hypothesis. Consequences are expected user costs, not measured outcomes.

| ID / priority / severity | Screen and file evidence | Problem and consequence | Concrete solution / principle |
| --- | --- | --- | --- |
| UX01 P1 Major | Shell, `app/workspace/workspace.tsx:999–1019`; S | `navigate` changes section state without browser history. Reload/back cannot reliably restore task/list context; users must reconstruct their location. | Encode section and selected object in URL, preserve dirty guards and ownership checks. Nielsen H3/H4; IA every page a front door. |
| UX02 P1 Major | Tasks, `tasks-panel.css` max-width 1100 rule; `tasks-panel.tsx:310`; V phone tasks-light | Detail stacks after the entire list. With one fixture row its title is already near the bottom; longer lists increase distance. | Phone/tablet selection opens a dedicated detail surface with Back and restored list position. H7; proximity and task continuity. |
| UX03 P1 Major | Tasks, `tasks-panel.tsx:198–209`, `task-relations.tsx`; V desktop tasks-light | Edit, hierarchy, trash, work estimates, planning, dependency and page sections compete before core work is clear. Empty relation pagers occupy space. | Inline status/priority/deadline; fold empty relations; show pagers only when useful; move trash/parent move to object menu. H8; hierarchy/grouping. |
| UX04 P1 Major | Task editor, `tasks-panel.tsx:116–143`; S | Changing one property requires full modal containing description, status, priority, deadline, estimate and remainder. Repeated context switching. | Property popovers/inline fields with versioned PATCH; retain full form for multi-field edits. H7; direct manipulation. |
| UX05 P1 Major | Notes, `panels/notes.tsx:110–129,619–627,871–920`; S | Manual saving and save/stay/discard guards recur during normal navigation. Safety works, but writing is interrupted. | Prototype serialized background saves using existing versions; show Saving/Saved/Failed and retain drafts/conflict recovery. Until reliable, preserve manual save and guards. H1/H3/H7. |
| UX06 P1 Major | Shell, `workspace.tsx:1623–1634`; V desktop note editor | Global “Синхронизировано” derives from calendar query, while note saving has its own state. The broad label can imply that all work is safe. | Scope label to “Расписание обновлено”; show document persistence next to document. H1/H2; status precision. |
| UX07 P2 Minor | Tablet calendar, `workspace.tsx`, `workspace.css`; V 834px calendar-dark | Weekly columns compress event titles into clipped multi-line fragments; large heading/filter region reduces grid exposure. | Prototype compact date toolbar and day/3-day alternative at intermediate widths; retain week and full event detail. H6/H7; content-driven density. |
| UX08 P2 Minor | Navigation, `navigation.tsx:119–145`; V dark notes and database index | Databases, a confirmed core capability, is behind generic More among unrelated tools. Destination exists but has low scent. | Desktop persistent knowledge group with Notes, Databases, Materials; keep labelled phone More and expose active destination. Validate with tree testing. IA scheme/labeling. |
| UX09 P2 Minor | Notes creation `panels/notes.tsx:351–406`; block delete `note-blocks.tsx:636–658`; S | A title-only creation dialog and confirmation per block interrupt composition. | Inline page creation; block-local undo before replacing confirmation. Keep branch-trash protection and stable block IDs. H3/H7. |
| UX10 P2 Minor | Organization, `panels/organization.tsx:73,409`; S | Member picker exposes only first 200 pages and current-week event choices. A valid object outside the subset is unfindable there. | Paginated/searchable picker using existing reads where sufficient; disclose range. Any missing server search contract is a separate scope. IA growth/findability; H6. |
| UX11 P2 Minor | Database `panels/databases.tsx`, RecordForm and PropertyManager; S | Single-value edits and schema management rely on full dialogs; large record maintenance repeats form opening. | Inline cell editing first, property configuration in one side panel. Preserve touched-field PATCH, nulls, option IDs, schema versions. H7/H5. |
| UX12 P2 Minor | Shared `shared/ui.tsx:24–66`; task form close at `tasks-panel.tsx:116`; S | Escape/backdrop closes task editor without a dirty check when not busy. Typed, unsaved edits can be discarded. This is distinct from protected note navigation. | Dirty-aware task/event/record close policy, shared only after checking each caller. Confirm only when changes exist; test Escape/backdrop. H3/H5. |
| UX13 P2 Minor | Notes/AI CSS; `tasks-panel.css:30,46`, `panels/ai.css`; S | Important metadata often uses 11–12px. Not automatically a WCAG failure, but harder to scan at compact widths. | Prioritize deadline/source/save-state text at 13–14px; reserve smaller text for secondary metadata; test zoom. Typographic hierarchy. |
| UX14 P2 Minor | Time control, `shared/time-field.tsx:45–70`; S | Native time field has an additional modal picker with hour/minute columns and confirmation. Optional alternate input adds another interaction layer. | Keep direct typing; test whether users benefit from optional picker. Prefer anchored disclosure if it preserves keyboard semantics. Do not remove all-minute precision. H7/H8. |
| UX15 P2 Minor | Notes index; V phone notes-dark | Tree area and large unselected-page prompt both take substantial vertical space despite an existing page. Multiple creation entry points compete with opening content. | Compact “Select a page” state when pages exist; full first-use guidance only for an empty library. H8/H10; spacing/hierarchy. |
| UX16 P2 Minor | Navigation `navigation.tsx:97–108`; S | Section destinations are buttons. Native open-in-new-tab/copy-link behavior is unavailable. | After URL contract is defined, use links for destinations, buttons for disclosure/actions. Web Interface Guidelines semantics; H4. |

UX12 establishes draft-loss behavior from source, not a reproduced production incident. Raise priority if exploratory testing shows frequent accidental dismissal. No unsupported contrast-failure or security claims are included.

## Nielsen heuristic coverage

| Heuristic | Assessment |
| --- | --- |
| H1 Visibility | Good loading/retry and save feedback; UX06 scopes global status incorrectly. |
| H2 Real-world match | Russian task labels and explicit timezone are useful; generic sync promise needs narrowing. |
| H3 Control/freedom | Branch trash, restore, dirty-note guard are strong; URL/history and editor dismissal need work. |
| H4 Consistency | Shared tokens/dialogs and labelled navigation are strong; destination-button semantics need improvement. |
| H5 Prevention | Versions, DST disambiguation, hierarchy validation protect users; preserve them during inline editing. |
| H6 Recognition | Trees, breadcrumbs and selected rows help; bounded organization picker limits findability. |
| H7 Efficiency | Existing quick add, completion, grid manipulation, slash picker and Cmd/Ctrl+S are assets; full property forms remain costly. |
| H8 Minimalism | Main excess is secondary task controls, empty pagers and duplicate entry surfaces, not decorative gradients. |
| H9 Error recovery | Retry/conflict paths exist; no blanket finding that errors are absent. Test draft recovery after new editing patterns. |
| H10 Help | Useful nonblocking-deadline and optional-group explanations exist; keep contextual, reduce repeated empty-state teaching. |

## Information architecture assessment

The structure is shallow, not excessively deep. The weakness is a hybrid of work modes (Calendar/Tasks), content types (Notes/Materials/Databases) and a generic overflow bucket. Known-item retrieval has Search, trees and links, but browser-history re-finding is weak. Contextual links are valuable and should remain alongside browse/search.

Proposed desktop grouping is a hypothesis: Time (Calendar/Tasks), Knowledge (Notes/Databases/Materials), Assistant (AI), utilities (Search/Inbox/account). Collections/tags remain optional organization tools, not mandatory containers. Keep phone navigation to a small labelled set. Validate grouping with a tree test: find a lecture note, find a database, resume yesterday's task, locate an uploaded PDF. Use a small card sort if Notes versus Databases labels remain ambiguous. Do not merge those domain objects or automatically associate subjects.

## Visual aesthetics assessment

No critical hierarchy collapse established. Major: task detail has competing controls and mobile list/detail separation (UX02/03). Minor: tablet calendar content density, oversized returning-user note prompt, small metadata. The desktop document canvas, warm neutral light surfaces, dark reading planes, lavender selection and teal academic source distinction work well. Keep the A1 calendar/note symbol.

Overdesign verdict: **borderline in task details, generally restrained elsewhere**. The excess is simultaneous controls and empty sections; more shadows/cards/accents would worsen it. Top three visual priorities: mobile work surface, task-detail hierarchy, intermediate-width calendar density.

## Web Interface Guidelines review

Rules fetched on audit date from [Vercel Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). Relevant findings in file:line form:

- `navigation.tsx:97`: destinations use buttons; provide actual URLs and links (UX16).
- `tasks-panel.tsx:116`: form dismissal lacks unsaved-change protection (UX12).
- `task-relations.tsx`: unconditional empty pagers add navigation without useful destinations (UX03).

Positive evidence: native modal dialog, labelled close action, Escape/focus return, form labels, status/alert regions, skip link and reduced-motion styles. Existing time listboxes have arrow/Home/End handlers; do not label them keyboard-inaccessible merely because options are divs. No claim of full accessibility conformance: verify screen-reader output, focus after async errors, 200% zoom, mobile keyboard occlusion, coarse-pointer bounds and high-contrast mode in implementation QA.

## Reference comparison

- **Notion Calendar:** documented [slot selection and event manipulation](https://www.notion.com/en-gb/help/manage-your-calendars-and-events) and [discoverable shortcuts](https://www.notion.com/help/notion-calendar-keyboard-shortcuts) support a time-first workspace. Ukladen already has grid create/move/resize and keyboard alternatives. Borrow compact context and shortcut discovery, not automatic merging of academic occurrences. Database integration is documented [here](https://www.notion.com/help/use-notion-calendar-with-notion); mixed projection is a separate Ukladen capability scope, not a visual defect.
- **Linear:** [issue creation](https://linear.app/docs/creating-issues) offers shortcut C and multiple entry paths, including a modal. The lesson is efficient capture and consistent object operations, not “all modals are bad.” Ukladen quick add/completion already meet that direction; property edits and mobile task continuity are the gap. Do not copy teams/sprints into personal student tasks.
- **Craft:** official [3.7 update](https://www.craft.do/pt-BR/blog/craft-update-3-7-0) describes quick entry and mobile block actions. Ukladen already has a document canvas, slash/plus picker and reorder alternatives. Borrow uninterrupted composition and contextual actions; rich formatting, nested block schemas and collaboration are separate product work. This is a workflow comparison, not a pixel-level visual review of Craft.

Differences from references are not automatically defects. These sources establish patterns; their exact contemporary app appearance was not inspected.

## Disposition

- **Remove visually:** always-present empty relation pagers; duplicate generic explanatory subtitles where space is scarce; large selection prompt when a note library already exists. Keep functionality available.
- **Move into context actions:** task branch trash/parent move; page rename/move/link/trash; database schema/settings. Keep keyboard-accessible labelled menus and visible primary actions.
- **Combine:** task property summaries with their editors; calendar date navigation/title into one toolbar; related-content controls into one progressive section; knowledge destinations into a stable desktop group.
- **Redesign:** mobile task master/detail; URL/history behavior; note persistence feedback; record cell editing; bounded membership pickers; tablet calendar density.
- **Preserve:** A1, light/dark/system theme, standalone pages/events, optional academic profile, source distinctions, exact/DST-aware time, branch recovery, ownership/version checks, nonblocking deadlines, existing direct manipulation, explicit AI write confirmation, source citations and spending authorization boundaries.

## Research and release gates

Test prototypes with students on three jobs: capture coursework, schedule work, retrieve a note/material. Record success, backtracking, accidental dismissals and action counts using the definitions above; do not set unsupported baseline times. Include keyboard-only and a screen-reader session. Seed 30 tasks, 200+ pages, long Russian labels, dense overlaps and large database tables. AI scenarios use fixtures only. Findings UX01–06 are the first implementation candidates; no implementation is authorized by this report.

Top three overall priorities: **mobile task continuity; reliable navigation/history; direct property editing with truthful persistence feedback**.
