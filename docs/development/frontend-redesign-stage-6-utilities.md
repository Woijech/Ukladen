# Frontend redesign stage 6: settings and utility surfaces

Date: 2026-11-13. Status: implemented locally on `frontend/ui`; not pushed, merged or deployed.
Completes the remaining UI scope after [databases/collections](frontend-redesign-stage-5.md)
and [AI conversation](frontend-redesign-stage-6-ai.md).

## Delivered

Settings uses compact section navigation to Profile, Appearance, Schedule and AI.
Profile fields align in two columns on desktop and stack on narrow screens. Explicit
light/dark/system choices show their actual selected state and small theme previews;
they use the same storage/event mechanism as the existing header theme button.
Storage failure still applies the live theme without writing profile settings or
calling a provider. The header cycle control remains available everywhere.

Profile edits now participate in workspace dirty-navigation and browser unload guards.
A failed save retains name/timezone, success establishes a new confirmed local baseline,
and pending writes disable fields/duplicate saves. A persistent Saved/Dirty/Error
status reflects the current draft even when a timezone change remounts the calendar
context and clears transient action notices. Timezone changes still only change
display/session state, never existing event instants. Avatar upload/delete, optional
group setup and the AI settings route retain their existing behavior. No new account,
password, Google-link or provider contract was invented; existing auth flows remain.

Home is a utility entry: real calendar/task/note shortcuts, the existing five-page
list and explicitly named Materials/Databases/Notifications links. The promotional
hero, oversized repeated A1 image and slogan were removed from this signed-in screen;
A1 remains in shared navigation/branding. No fake statistics or recency ordering was
introduced. All prior destinations remain available.

Materials keep Open/Download and failed-processing retry visible. Edit and recoverable
trash use a labelled viewport-bounded row menu with keyboard dismissal. Existing real
byte upload, reservation-safe retry, limits, safe downloads and reference semantics are
unchanged. Materials, Search and Inbox now share compact headings, neutral dividers,
quiet rectangular surfaces and phone reflow. Search still uses the real server full-text
contract and escaped snippets; inbox unread filtering, review opening and read marking
remain unchanged. Empty/loading/error states retain their existing retry/next actions.

## Findings and decisions

| Finding | Priority | Resolution |
| --- | --- | --- |
| Signed-in Home used a landing-page hero | P1 | Working shortcuts and content replace promotional composition |
| Theme selection required cycling unknown states | P2 | Explicit three-way choice; same persisted theme contract |
| Unsaved profile fields could be lost on section navigation | P1 | Dirty/unload guards, retained error draft, confirmed success baseline |
| Name/timezone could change during a pending profile write | P1 | Disable pending fields and submit once |
| Timezone context refresh cleared the transient save notice | P1 | Persistent status derived from loaded/saved baseline and draft state |
| Material Edit/Trash competed with primary Open/Download | P2 | Context menu, visible primary/failed-retry actions |
| Utility headings/cards lacked shared density | P2 | Scoped typography, dividers, responsive layouts using shared tokens |

The visual review favors content and clear action labels. There is no new navigation
level, animation, dependency or destructive shortcut. Keyboard actions retain visible
focus; mobile controls retain hit targets and local overflow handling. The guidelines
review used the current [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).

## Verification

Final verification: **304 Chromium tests passed (2.2m)** across the full frontend
suite. This includes 17 added scenarios across these remaining redesign slices, plus
existing auth/CSRF, identity/cache isolation, calendar timezone/DST, task/note saves,
material byte/reservation handling, database/schema versions, source scope, AI recovery
and HITL decisions. Final lint and typecheck passed; the production build passed for
the same production source before the final test-only fixture/await corrections.
Compose configuration, diff whitespace and changed-document file links passed.

Settings/Home run at 320/390/834/1440px in both themes; database/collection details
run at 390/834/1440px; AI conversation/history runs at 320/390/834/1440px. The exercised
surfaces include keyboard focus/return, reduced motion, emulated touch, visible-text
contrast and document overflow checks. The report does not claim real-device or full
assistive-technology certification.

The first full run exposed the genuine timezone-remount feedback issue described
above. Subsequent failures were isolated to test setup: the note queue assertion
checked a request counter before asynchronous CSRF/fetch admission reached its route,
and the new profile test navigated beyond its intentionally bounded fixture. The
queue test now awaits actual request admission; the profile test returns to the fully
mocked calendar and verifies navigation is unblocked. Production note saving was not
changed to accommodate the timing assertion. Capture resets page scroll before full
screenshots so fixed offscreen skip navigation is not retained in a stitched frame.
A temporary automatic approval-review quota failure prevented one test invocation;
that invocation did not execute. After the owner's continuation, the final run above
completed successfully.

Pre-existing owner working-tree edits were retained and excluded from the redesign
commits. Verification exercises that combined local working tree.

| Screen | Light | Dark |
| --- | --- | --- |
| Settings desktop | [Screenshot](../design/frontend-utilities-stage-6-settings-desktop-light.png) | [Screenshot](../design/frontend-utilities-stage-6-settings-desktop-dark.png) |
| Settings phone | [Screenshot](../design/frontend-utilities-stage-6-settings-mobile-light.png) | [Screenshot](../design/frontend-utilities-stage-6-settings-mobile-dark.png) |
| Home desktop | [Screenshot](../design/frontend-utilities-stage-6-home-desktop-light.png) | [Screenshot](../design/frontend-utilities-stage-6-home-desktop-dark.png) |

Additional inspected surfaces: [Materials phone](../design/frontend-utilities-stage-6-materials-mobile-light.png),
[Inbox phone](../design/frontend-utilities-stage-6-inbox-mobile-light.png),
[Search desktop](../design/frontend-utilities-stage-6-search-desktop-dark.png).
All browser requests use synthetic fixtures; no real backend, storage service or
AI/provider request was made. Prior dated verification in other guides is retained
and does not imply backend checks were rerun for this frontend-only slice.

## Remaining issues and limits

- Database schema/version conflicts need deliberate cancel/reopen after copying the
  draft; no automatic merge is claimed. Selection URLs and global database search
  remain outside this slice.
- Existing in-memory editor drafts do not provide crash/offline recovery. Explicit
  save remains the persistence boundary.
- Material reservation/raw-byte behavior, AI scopes and HITL are preserved, not replaced
  by new upload or model workflows. Provider activation is not part of this delivery.
- Chromium emulates touch and viewport sizes; real phone keyboards, screen readers,
  Safari and Firefox require separate manual checks. No participant usability study
  or production deployment has been performed.
