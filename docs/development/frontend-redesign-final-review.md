# Ukladen final frontend redesign review

Date: 2026-11-13. Branch: `frontend/ui`. Implementation baseline: `e2cdcbb` plus the existing working-tree changes present when this review started. Status: reviewed with remaining UX gaps; not a declaration that every concept acceptance criterion is complete.

Follow-up (2026-11-13, `workspace-deep-links`): object/date/layout restoration from
UX01/FR04 is now implemented in a separate [deep-link delivery](workspace-deep-links.md).
The original findings and verification below describe this review's baseline;
crash recovery, full filter/scroll restoration and manual release gates remain open.

## Decision

The redesign substantially improves working composition and everyday interactions: a joined calendar workspace, compact task properties, a document-first note canvas, editable database cells, focused chat and consistent utility screens. A1 branding, warm neutral surfaces, lavender actions and teal academic source distinctions remain recognizable in both themes. No functional removal was found in the exercised inventory below.

The initial passing suite missed real usability defects. This review reproduced clipped note menus on phone/tablet and accidental dismissal of an unsaved full database record. It fixed these small frontend defects and isolated nested menu Escape handling. All final checks pass, including **319 Playwright tests**. No backend/API/database changes, dependencies, deployment, merge or push were performed. Tests use intercepted fixtures and synthetic AI responses; no real AI/provider request was made.

Two significant original gaps remain: object-level URL restoration and browser-crash recovery for unsaved notes. Manual note saving remains deliberately safe but does not fulfill the proposed background-save lifecycle. These require their own implementation decisions and verification; green tests do not close them.

## Scope, method and evidence

Inputs: [original audit](frontend-ux-audit.md), [redesign plan](frontend-redesign-plan.md), [interaction specification](frontend-interaction-spec.md), [visual concept](frontend-visual-redesign.md), [DESIGN.md](../../DESIGN.md), architecture/workspace contracts, source, test fixtures and the dated stage reports linked from the [documentation map](../README.md). Applied the requested heuristics, aesthetics, information architecture and Web Interface Guidelines reviews. Used CodeGraph before locating relevant implementation paths; followed current source for dynamic behavior and fixtures for request contracts.

This is an expert review with browser automation and direct screenshot inspection, not participant research or a production acceptance trial. Source evidence and automated assertions are distinguished from visually inspected captures. Action counts are deterministic path counts, not timed usability results. Prior dated reports retain their original verification history.

The working tree already contained changes to shared dialog styling, time controls, error screens, AI settings/reviews and planning. They were retained and included in the tested state, but not authored or committed by this audit. In particular, the note-menu defect was reproduced with that existing animated dialog styling. A separate clean-HEAD reproduction was not performed; attribution is to the interaction of the redesigned menu positioning and the audited dialog styling, not to an independently verified clean deployment.

`docs/design/references/` is absent. Reference comparison uses official product descriptions and the requested interaction principles; no authenticated reference app or pixel-parity comparison was performed:

- [Notion Calendar event management](https://www.notion.com/en-gb/help/manage-your-calendars-and-events): time-first organization and event interactions.
- [Linear issue creation](https://linear.app/docs/creating-issues): fast capture and multiple entry paths, including a full creation dialog. A dialog is not automatically a defect.
- [Craft product update](https://www.craft.do/pt-BR/blog/craft-update-3-7-0): quick entry and mobile block interaction patterns; not a claim of editor feature parity.
- [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md): semantic links/buttons, keyboard/focus, feedback, forms, responsive behavior and reduced motion. Retrieved during this review.

## Original audit: before / after

“Resolved” means the concrete original problem has an implemented remedy with source/test evidence, not that every related future feature exists. P1 = major workflow gap, P2 = localized friction. No confirmed P0 issue was established.

| Original issue | Before | Reviewed implementation | Disposition |
| --- | --- | --- | --- |
| UX01 P1: location restoration | State-only section navigation loses location on reload/back | Section URLs/history work; selected task/database/view and calendar date/view are still local state | Partial; P1 remains |
| UX02 P1: mobile task detail | Details below the entire task list | Dedicated selected detail surface, Back retains list/filter context | Resolved in exercised mobile/tablet flows |
| UX03 P1: task hierarchy/noise | Editing, relations and planning compete with core task work | Compact rows; property actions; optional planning/relations; conditional pagination | Substantially resolved; long real datasets still need user validation |
| UX04 P1: one-property full form | Full editor required for priority/status/deadline | Direct property controls; full editor retained for multi-field changes | Resolved |
| UX05 P1: note save interruptions | Explicit Save and dirty-navigation guards | Serialized explicit saves, accurate dirty/error state, retained failed drafts | Partial; no background save or crash recovery |
| UX06 P1: misleading global sync | Calendar state labelled as workspace-wide synchronization | Calendar-scoped status; document save state beside the document | Resolved |
| UX07 P2: intermediate-width calendar | Compressed week columns and oversized controls | Compact toolbar/sidebar; day/week selection; default day at narrow widths | Mitigated; dense week titles still truncate by design, details/day remain available |
| UX08 P2: database findability | Desktop database entry buried in More | Persistent desktop destination; labelled mobile More and active destination | Desktop resolved; phone hierarchy remains a deliberate space tradeoff |
| UX09 P2: page/block modal overhead | Title-only creation dialog; confirmation for each block deletion | Inline page capture; contextual block tools; local structural Undo | Resolved; branch trash retains protection |
| UX10 P2: member picker cutoff | First 200 pages and loaded-week events only | Page membership paginates in batches of 50 beyond 200; event range is disclosed | Partial: event picker still uses loaded week, no server search added |
| UX11 P2: full-record single-value editing | Full record dialogs for small changes | Touched-field inline cell editing; full record editor retained | Partially resolved; schema/date controls and conflict recovery remain heavier |
| UX12 P2: unsafe form dismissal | Dirty task/event/record editors could dismiss | Task/event guards already implemented; this review adds full record discard confirmation | Main editors protected; smaller metadata/create dialogs need a separate close-policy pass |
| UX13 P2: small metadata | 11–12px information competes with primary reading | Clearer hierarchy and 18px document body; compact secondary metadata persists | Partial; no measured contrast violation asserted |
| UX14 P2: layered time picker | Native field plus separate modal selector | Anchored custom time controls for primary calendar/task flows with direct precision entry | Improved; database/auxiliary date controls not fully unified |
| UX15 P2: returning note empty selection | Large generic prompt even with an existing library | Library moves to bounded modal on narrower screens; document dominates after selection | Partial; no-selection prompt is still oversized for returning users |
| UX16 P2: button destinations | No native new-tab/copy-link semantics | Section destinations use URLs/links; object controls remain actions | Section issue resolved; complete object deep links depend on UX01 |

## Scenario costs and continuity

Count a click/tap/key activation that changes UI state as one action; typing is not counted as an extra click. Counts assume the same starting section and a visible target. They are not user-performance measurements. Full forms remain where they enable multiple changes or protect semantics.

| Scenario | Original path | Current path | Result / caveat |
| --- | --- | --- | --- |
| Change task priority | Select → Edit → choose → Save: 4 | Property → choose: 2 | No full form; versioned update and failure feedback |
| Quick task capture | Open form → focus/title → submit: approximately 3 | Focus quick add → type → submit: approximately 3 | Same basic action count, less form/context overhead |
| Complete task | Checkbox: 1 | Checkbox: 1, optional Undo | No extra confirmation; stale Undo does not overwrite newer work |
| Open task on phone | Select → scroll beyond list | Select → focused detail | Removes list-length-dependent travel; Back restores context |
| Create page | Create → title → submit, one modal | Inline create → title → submit, no creation modal | Roughly 3 actions; creation failure retains the title |
| Delete block | Menu/delete plus confirmation: 2–3 | Menu → delete: 2, optional Undo | Local restoration preserves stable IDs and later typing |
| Open databases from desktop | More → destination → target | Destination → target | 3 → 2; mobile More still adds an entry step |
| Edit one database value | Open record → value → Save | Cell → value → Save | Approximately 3 in both; avoids unrelated fields/full dialog |
| Add an old page to collection | Unreachable beyond first 200 | Next batch → choose → add | Reachable with supported pagination; not instant search |
| Create calendar event | Form-first start/end input | Select free range → name → save; full form alternative | Direct temporal intent; occupied target is not treated as blank grid |
| Move/resize calendar event | Full edit form | Pointer move/edge resize; touch preview/confirm; keyboard details | Versioned writes; official events remain read-only |
| Ask AI with context | Context/message/send | Sources/message/send | Similar action count, clearer scope and transcript; no automatic provider call |
| Switch away from a dirty note | Save/stay/discard | Save/stay/discard | Safety retained; proposed background-save reduction not delivered |
| Close dirty full record | Escape discarded edits | Escape → continue editing or explicit discard | Intentional safety action added, not a speed optimization |

## Final findings and fixes

Evidence: B = reproduced browser behavior, S = source-confirmed, V = direct screenshot inspection. “New regression” refers to redesign-introduced behavior in the audited tree; “old” refers to the original audit or earlier implementation. Severity is impact, not implementation size.

| ID / origin | Screen and file | Evidence | Problem and consequence | Resolution / next action | Priority |
| --- | --- | --- | --- | --- | --- |
| FR01 new regression, fixed | Note library / shared menus; `apps/web/src/app/workspace/panels/note-menu.ts` | B/V at 390/768; initial tests failed | Fixed menu coordinates assumed viewport origin inside an animated dialog; actions were clipped or below viewport | Clamp to dialog and viewport, measure actual containing-block origin, bound height with local scrolling; 390/768/1440 and reduced-motion tests pass | P1, fixed |
| FR02 new regression, fixed | Note page action menu; `apps/web/src/app/workspace/panels/notes.tsx` | S before fix; B after fix | Escape closed a menu and propagated to close its parent library, losing navigation context | Consume Escape only for the open menu, restore trigger focus; subsequent Escape can close library normally | P2, fixed |
| FR03 old UX12, fixed | Full database record editor; `apps/web/src/app/workspace/panels/databases.tsx` | B: dirty Escape test failed before fix | Unsaved full-record fields disappeared on dismissal | Explicit continue/discard guard for dirty full forms; busy saves cannot dismiss; inline Escape remains intentional cancel | P1 impact, fixed |
| FR04 old UX01 | Workspace location; `use-section-location.ts`, `tasks-panel.tsx`, `panels/databases.tsx`, `workspace.tsx` | S; section/back and page-link tests | Selected task/database/view/date cannot all be reconstructed by URL/reload | Specify canonical object/query URLs and return behavior, preserve ownership/dirty guards; implement separately | P1 Major |
| FR05 old UX05 / deferred spec | Notes `panels/notes.tsx` | S and save/retry tests | Unsaved drafts live in memory; browser crash can lose text; routine navigation still asks to save | Keep current guards; separately design durable local draft ownership/isolation and serialized background-save policy | P1 Major |
| FR06 old UX12 residual | Collection/property/view/material create or metadata dialogs | S only for remaining close policies | No universal dirty-close policy; smaller unsaved drafts can still require re-entry | Audit each caller's cancel semantics; add guards only where unintentional loss is established | P2 Minor |
| FR07 old UX10 | Collection membership `panels/organization.tsx` | S; pagination test | Page cutoff fixed; event choices still bounded to loaded week | Keep range disclosure; add supported range navigation/search as a separate frontend flow | P2 Minor |
| FR08 old UX11/14 / spec gap | Database `DateFields` in `panels/databases.tsx` | S/V | Native date and explicit-offset timed inputs differ from primary time controls; conflicts need copy/cancel/reopen | Extend shared temporal interaction only with offset/null/version semantics preserved; improve explicit conflict recovery | P2 Minor |
| FR09 old UX13 | Secondary save/version/source metadata across notes/tasks/AI | S/V | Some metadata remains 11–12px; longer labels are harder to scan | Prioritize important text at 13–14px; validate zoom before further density changes | P2 Minor |
| FR10 old UX15 | Notes without selected page `panels/notes.tsx` | V, menu-after-mobile capture | Large first-use-style prompt is shown even when pages exist | Compact returning-user selection prompt; retain full help for an actually empty library | P2 Minor |

FR01 geometry before correction: at 390px, menu bounds began approximately x201/y976 with a 110px height, while its dialog ended near y650. At 768px, menu began approximately x665/y972 while the dialog ended near y637. This was more than an aesthetic concern: the intended actions were outside the interactive surface. The initial focused run had **9 passing / 3 failing** cases: two menu bounds and one dirty-record dismissal. FR02 was identified from event propagation in source; the initial bounds failures occurred before its keyboard assertion, so no pre-fix browser reproduction of FR02 is claimed.

The menu helper is also used by block, material and database action menus. The fix is shared rather than duplicated; full-suite coverage checks callers. The record guard does not change inline-cell cancellation, PATCH shape, schema versions or successful-save closing behavior. No persistent data is deleted by either fix.

### Screenshot evidence

Saved final-review images are actual fixture-backed browser captures, not mockups:

- Menu [before phone](../design/frontend-final-menu-before-mobile.png) / [after phone](../design/frontend-final-menu-after-mobile.png); [before tablet](../design/frontend-final-menu-before-tablet.png) / [after tablet](../design/frontend-final-menu-after-tablet.png); [after desktop](../design/frontend-final-menu-after-desktop.png).
- 768px calendar [light](../design/frontend-final-calendar-768-light.png) / [dark](../design/frontend-final-calendar-768-dark.png).
- 768px tasks [light](../design/frontend-final-tasks-768-light.png) / [dark](../design/frontend-final-tasks-768-dark.png).
- 768px notes [light](../design/frontend-final-notes-768-light.png) / [dark](../design/frontend-final-notes-768-dark.png).
- 768px [database inline editor](../design/frontend-final-database-768-light.png), [AI transcript](../design/frontend-final-ai-768-dark.png), [settings](../design/frontend-final-settings-768-light.png).

Direct inspection during this review includes phone menu before/after, 768px calendar light, tasks dark, notes light, database light, AI dark, settings light, 1440px calendar dark and 390px note light; additional existing stage imagery informed the wider comparison. The final suite generates both-theme captures at all requested widths for the main sections. Capturing/asserting every screen is not equivalent to manually inspecting every pixel; uninspected captures are not presented as personal visual validation. Full-page screenshots can include content below a fixed mobile dock: that alone is not evidence of unreachable content; reachability is checked separately by scrolling/interaction tests.

## Heuristics review

| Nielsen heuristic | Current assessment and evidence |
| --- | --- |
| H1 Visibility of status | Scoped calendar status, local save/busy/error states, AI generation/recovery feedback; explicit Save is still required for notes |
| H2 Match to users' world | Time grid, task property vocabulary and document layout support student work; official academic facts remain distinguishable from personal choices |
| H3 User control | Back/detail continuity, task Undo, block structural Undo and guarded dirty editors; FR02/03 fixed; smaller dialog policies remain uneven |
| H4 Consistency | Shared palette, links and contextual actions; database temporal inputs remain a component inconsistency |
| H5 Error prevention | Occupied-grid creation boundaries, read-only official events, explicit touch confirmation, versioned updates; no inferred AI write permission |
| H6 Recognition | Visible task properties, source labels, calendar mini-map, page hierarchy; mobile More and icon rail need real-user findability testing |
| H7 Efficiency | Quick add, property editing, slash menu, keyboard shortcuts, drag alternatives; manual note saving and incomplete object URLs remain major gaps |
| H8 Minimalism | Focused working surfaces replace competing forms; note no-selection prompt and residual small metadata still need refinement |
| H9 Error recovery | Failed drafts retained in mounted editors, retry/conflict feedback, trash/restore and Undo; no crash/offline draft persistence or automatic merge claimed |
| H10 Help | Shortcut disclosures, source/range hints and empty-state guidance exist; no participant evidence for comprehension or screen-reader verification |

## Information architecture review

| Principle | Result |
| --- | --- |
| Organization scheme matches the job | Calendar/time, tasks/action, notes/knowledge are stable primary destinations; databases/materials/collections remain distinct choices |
| Labels have information scent | Desktop database access and active labels improve discovery; mobile More is explicit but still indirect |
| Hierarchy is not excessively deep | Core section changes are shallow; contextual panels preserve work; nested page paths can scroll locally |
| Labeling is consistent | Shared Russian destination vocabulary and breadcrumbs; no invented inactive commands or placeholder screens |
| Multiple routes support finding | Navigation, search, palette destinations, page hierarchy, related objects and copied page links work; object URL restoration remains incomplete |
| Context is retained on return | Mobile task detail/back and dirty-note navigation tested; full reload cannot restore every selected object |
| Structure supports growth | Page hierarchy/membership pagination exceeds 200 entries; loaded-only task filtering and event membership scope remain truthfully bounded |

The command palette supports destinations/search, not every creation command proposed in the specification. Database range dragging/mixed-view controls that were API-only before the redesign remain outside the implemented UI. Neither is counted as a removed feature. Tree testing with students has not been conducted.

## Visual aesthetics and reference fit

| Principle | Assessment |
| --- | --- |
| Hierarchy | Calendar grid, task rows and note text are the dominant working content; contextual controls are subordinate |
| Emphasis | Lavender primary actions/selection are consistent; teal indicates academic source; status is not communicated by color alone |
| Contrast | Light/dark roles and visible focus retained in exercised states; this review does not certify every color pair or WCAG conformance |
| Spacing | Shared working rhythm and document margins; mobile forms reflow; the returning note prompt still wastes vertical space |
| Alignment | Task property columns, joined calendar edges, document text and database cells have stable alignment; overlapping events intentionally use lanes |
| Grouping | Context details, optional settings and source controls replace repeated top-level cards; relation tools remain available |
| Consistency | A1, typography, borders, radii, feedback and controls align across sections; temporal inputs remain an explicit exception |
| Depth / restraint | Few working layers, bounded menus and contextual sheets; no new decorative dashboard cards or perpetual motion introduced |

**Notion Calendar:** the implemented desktop mini-calendar, compact source sidebar, joined week grid, day mode, range selection, move/resize and contextual editing match the intended time-first model. Dense overlaps truncate titles at 1440px, but lanes are distinct and selecting/day mode exposes the content. A narrow viewport defaults to day rather than forcing seven unreadable columns. Read-only official facts and hidden-source busy intervals are Ukladen-specific rules worth preserving, not reference mismatches.

**Linear:** rows expose status, priority and deadline, with quick capture, grouping/filtering, contextual details and shortcuts. The review found no reason to import team/sprint machinery. Filtering/grouping applies to loaded data and is labelled accordingly; it is not a newly implemented server-wide saved-view system.

**Craft:** reading typography, quiet document canvas, flat block types, slash tools, contextual formatting and block movement follow the requested direction. It is not a rich-text/collaborative editor: existing plain/Markdown blocks, stable IDs and manual save semantics remain. No unsupported nested rich-text schema, revision history or collaboration was invented.

## Feature preservation and acceptance evidence

The following exercised behaviors survived the redesign and final fixes. This is an inventory of test/source evidence, not proof of every possible production state.

| Section | Preserved or implemented acceptance behavior | Limits |
| --- | --- | --- |
| Shell/auth | Section links/history, search/palette, mobile dock/More, focus return, theme choice, private-editor removal on expired session, owner/cache isolation fixtures | Complete object deep links, real identity-provider round trips and assistive-technology audit not covered |
| Calendar | Day/week; free-range creation; pointer move/resize; overlap lanes; contextual edits; keyboard alternatives; touch preview/confirm; occupied-target/boundary checks; read-only official schedule | Real touch hardware and production IIS sync not used |
| Time semantics | Profile timezone independent of browser zone; DST gap rejection, ambiguous-fold explicit offset; original interval/duration precision; hidden sources affect display only | Fixture-backed verification; not a production timezone database/OS matrix |
| Tasks | Quick add; inline properties/title; grouping/sorting/filtering; shortcuts outside typing fields; details/back; hierarchy/relations/planning; trash/restore; versioned Undo rejects stale writes | Loaded-only views; no claim of server-wide filtering |
| Notes | Existing plain/Markdown text, H1–H6, list/check/link blocks; stable IDs; slash/plus menu; contextual tools; drag and touch reorder; local structural Undo preserving later typing; hierarchy/search/copy link | Flat existing block contract; no durable crash/offline draft recovery |
| Note persistence | Explicit saves serialized; typing during save remains dirty; requested follow-up save; metadata success/document failure advances retry version; conflicts/invalid drafts retained; guarded navigation/unload | Mounted in-memory recovery, not background autosave or revision history |
| Databases | Seven existing property types; null/hidden values; touched-only updates; stable option IDs; expected record/schema versions; inline/full forms; table and day/week/month calendars; saved filters/sorts/columns; trash/restore | Heavy schema setup and explicit conflict recovery remain; temporal controls not fully unified |
| Date projection | Date-only and timed fields retain semantics, exclusive midnight end; projection remains nonblocking; view changes do not change event ownership/busy rules | No new range-drag/mixed-view UI promised |
| Collections/materials | Typed reference membership; pages beyond 200; reference removal preserves members/bodies; raw-byte upload with reservation/retry/limits/CSRF; explicit upload confirmation | Event choices limited to loaded week; no real object-storage transfer |
| Search/inbox | Escaped snippets, opening owned result, unread/read updates, review destinations | Synthetic results and notifications only |
| AI | History/transcript, sources/citations, automatic context vs explicit empty selection, generation/error/recovery/cancel, immutable proposal/HITL confirmation and permission-bound diagnostics | Synthetic responses only; no real model quality, cost, streaming network or provider behavior validated |
| Settings/utilities | Profile/timezone, avatar validation/upload/delete contract, light/dark/system setting including storage failure, account/schedule/AI destinations, error/empty/retry surfaces | No live email/provider/IIS action |

Official facts are not rewritten by personal event interactions. Source filters do not remove busy intervals from availability. Intentional overlapping personal events remain available via explicit creation/editing; preventing accidental blank-grid creation inside an existing event does not prohibit deliberate overlaps. Database views/collections reference objects; their removal does not delete page bodies. No auth, ownership, CSRF, HITL or backend rule was changed by this audit.

## Responsive and input matrix

Final Playwright coverage runs in Chromium against the production build, with fixture APIs. “Both” means light and dark assertions/captures in the relevant responsive suites, not all possible interaction permutations.

| Surface | 390px | 768px | 1440px | Input / state checks |
| --- | --- | --- | --- | --- |
| Calendar | Both; narrow day grid | Both; day/week controls reachable | Both; sidebar/week/context | Pointer range/move/resize, keyboard details, touch preview/confirm at 390/768, errors, timezone/DST |
| Tasks | Both; focused detail | Both; compact rows/detail | Both; rows/context | Inline edits, quick add, shortcuts, touch at 390/768, stale Undo, retry |
| Notes | Both; library modal/document | Both; library modal/document | Both; tree/document | Slash/menu focus, drag/keyboard/touch block controls, dirty/save/failure/Undo; nested menu with normal and reduced motion |
| Databases/collections | Both; bounded cell editing | Both; inline Save fully visible | Both; table/detail | Record versions/null/options, page pagination, full-form dirty Escape/discard |
| AI | Both; transcript/history | Both; transcript/history | Both; history and transcript | Source controls, busy/error/recovery/cancel/HITL fixtures |
| Settings/secondary screens | Both | Both | Both | Theme, profile draft guard, upload validation, empty/error/loading and navigation fixtures |

Existing coverage also exercises 320, 834 and 1024px where relevant. The review adds exact 768px cases instead of treating 834px as equivalent. Touch tests emulate `hasTouch` and taps; they are not tests on physical iOS/Android devices. Reduced-motion tests cover navigation/menu and relevant editor flows, not every animated component in every state. Keyboard tests cover Tab/focus/Escape and feature shortcuts, not a full screen-reader session. Drag tests verify request semantics and safe alternatives; no claim of native touch drag parity is made.

## Verification ledger

Executed from `apps/web`, except Compose. Playwright serves the production build on local port 3001. No dependency installation or real provider activation.

| Phase | Executed check | Result |
| --- | --- | --- |
| Baseline before audit fixes | `npm run lint`, `npm run typecheck`, `npm run build`, `npm test -- --workers=4` | All pass; **304 tests**, approximately 2.2 minutes for tests |
| New regression probes before fixes | Focused content/calendar/tasks/AI/utilities tests with `--grep '768px\|final review'` | **9 pass / 3 fail**: phone/tablet menu bounds, dirty full-record Escape |
| After production fixes | Lint, typecheck, production build and focused regression run | All pass; **14 tests**, approximately 21.7 seconds |
| Final complete run after all source/test changes | `npm run lint`, `npm run typecheck`, `npm run build`, `npm test -- --workers=4` | All pass; **319 tests**, approximately 2.5 minutes for tests |
| Configuration / patch hygiene | `docker compose config --quiet`, `git diff --check` | Pass |

Next.js 16.3.8 production build completed. The final suite adds 15 cases relative to baseline through exact-width responsive tests, tablet touch coverage and targeted regressions. Passing tests validate fixture-backed behavior, not live persistence, provider quality, infrastructure health or population-level usability. Documentation-only completion does not imply another full run after the final run above.

## Follow-up order and release limits

1. P1: canonical selected-object/date URLs with reload/back restoration and dirty ownership-safe navigation.
2. P1: decide durable note draft recovery and background-save behavior; preserve explicit-save guarantees until replacement is reliable.
3. P2: remaining dialog close policies, collection event-range finding and common database temporal controls; then compact no-selection notes and important small metadata.
4. Validate with students on capture → schedule → retrieve jobs, dense calendars, 30+ tasks and 200+ pages. Measure completion/backtracking/accidental dismissal; do not infer success rates from automation.

Not performed: production backend/database migration tests, live AI or IIS requests, real object storage, deployment, Firefox/WebKit, physical phones/tablets, screen-reader audit, comprehensive 200% zoom/contrast certification, offline/crash recovery tests for an unimplemented recovery feature, or participant usability research. Broad source/test preservation is strong evidence of frontend contract continuity, not a guarantee against every data-loss scenario. Unsaved note text can still be lost on browser/process failure.
