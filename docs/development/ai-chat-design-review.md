# AI chat interface review

Date: 2026-11-09. Follow-up to the [workspace redesign](frontend-design-review.md).
Branch: `codex/ukladen-visual-system`. Anti-Slop mode: DURING (owner selection).
Direction and decision reasons: [DESIGN.md](../../DESIGN.md).

## Delivered behavior

The existing AI area has a jade action palette, a distinct composer, labelled
source selection, concrete send/stop/trash glyphs and a response-options disclosure.
Enabled modes stay named when the disclosure closes. Starter topics prepare an
editable question and never submit it. Enter inserts a newline; Ctrl/Cmd+Enter
uses the existing guarded send function. History and new-chat creation share a
compact phone row. Long phone content reflows naturally; the transcript retains
its own scroll area. Both themes retain the approved A1 branding.

Message arrival, disclosure opening, status changes and dialogs use finite
200–320ms transitions; controls respond over 160ms. Streaming text does not
restart its message animation. Reduced motion disables animation and transitions.
No dependency, backend, API, permission, session or database change was introduced.

## Executed verification

| Check | Result |
| --- | --- |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| `npm test -- --workers=4` | PASS, 214 Chromium tests, including 39 AI scenarios |
| `docker compose config --quiet` | PASS |
| `git diff --check` | PASS |

Light/dark chat, expanded options, settings and usage were captured at
320/390/834/1440px. Phone height was 844px. Welcome, new-chat dialog and empty chat
were captured at 390/1440px. Source validation, progress and cancellation were
checked on a phone. Captures were visually inspected; rendered-text contrast and
document overflow checks passed. The suite also requires no uncaught page errors
in the chat/settings/usage sweeps. Contrast evidence is limited to captured states,
not a complete accessibility certification.

The supplied Anti-Slop contrast checker measured white on jade `#246858` at
**6.57:1**, and dark ink `#153b30` on mint `#9edbc8` at **7.89:1**.
Both exceed the normal-text AA threshold. Focus/field tokens retain the previous
workspace checks, and the browser checks composite text against its actual surface.

## Recorded control evidence

| Control | Observed result |
| --- | --- |
| Three welcome topics | Open creation; cancelling writes nothing; selected question appears as an editable draft after explicit creation |
| Start conversation / New chat | Create through the existing model/connection form; blank creation has an empty message field |
| Empty-chat topic | Fills and focuses the message field; typing disables shortcuts that would replace the draft |
| Enter / Ctrl+Enter | Newline stays in the draft; explicit command sends the exact edited message once |
| Send / sources | Double-click guard, source scope and CSRF contracts remain covered |
| Response options | Enter opens the disclosure; source-only state survives closing and sends the existing `source_only` flag |
| Full-document mode | Invalid scope gives a visible error; explicit sources allow background progress, recovery and cancellation |
| Details of response | Opens the stored run, reports unknown tariff honestly, Escape closes and returns focus |
| Trash icon | Opens explicit deletion confirmation; Escape preserves the chat; confirming sends one protected DELETE |
| Citations | Open current safe source content, including changed/missing sources; HTML remains text |
| Cancel / recover / proposals | Existing no-resubmission, exact-digest and expired/stale guards pass |
| Theme / history / settings / usage | Existing destinations, native disclosure, source viewer and editable settings remain operable |
| Reduced motion | Computed message animation exists normally and becomes `none` when the preference changes |

## Visual corrections

Repeated phone headings and stacked history controls consumed too much space;
the open chat retains its accessible heading and uses a compact history row.
A fixed-height phone trial clipped content at 320px, so phones now use natural
page flow and a bounded transcript. The composer stays inside the panel, and its
Send button remains above the dock when the composer is scrolled into view.
The full-source note, errors and success feedback can expand the desktop panel.
Full-page captures of fixed navigation can show its viewport position inside a
tall image; actual composer/dock rectangles are checked independently.

## Anti-Slop Delivery Gate

Statuses apply to this AI refinement and the recorded verification scope.

### Hard gate

| Item | Status and evidence |
| --- | --- |
| R-02 | PASS: newly authored UI copy has no em dash; existing data placeholders were retained |
| R-03 | PASS: 320–1440px overflow checks, inspected phone reflow and composer/dock geometry |
| R-17 | PASS: no invented production statistics; usage still reads existing APIs |
| R-18 | PASS: no testimonials or invented people added |
| R-23 | PASS: approved A1 reused; owner-requested chat redesign, no generated brand assets |
| R-24 | PASS: existing real navigation destinations retained |
| R-25 | PASS: captured-state text contrast checks and computed primary-button ratios above |
| R-26 | PASS: native controls retain real handlers; new topic, disclosure, details and trash actions exercised above |
| R-27 | PASS: explicit welcome/empty states, named loading, validation errors, interrupted-stream recovery and cancellation |
| R-28 | PASS: no FAQ introduced |
| R-32 | PASS: keyboard disclosure, multiline/send commands, native modal Escape and focus return exercised |
| R-33 | PASS: source and CSS edited directly, no source-rewriting script |
| R-34 | PASS: light/dark captures and rendered contrast checks pass |
| R-35 | PASS: production build, 214 browser tests and recorded control interactions |
| R-36 | PASS: no new security, performance or customer claims |
| R-37 | PASS: owner direction and 2/2/2 dials declared before implementation |
| R-38 | PASS: no fictional workspace data shipped; synthetic content is confined to tests |
| R-39 | PASS: labelled native controls, focus/disabled states, touch sizing and measured reduced-motion override |
| R-40 | PASS: existing sized branding, no third-party scripts/fonts or unmeasured performance claims |

### Purpose gate

| Item | Status and evidence |
| --- | --- |
| R-01 | PASS: jade identifies chat action/selection; no new gradients or glows |
| R-04 | PASS: document, chat, send, stop and trash glyphs describe their real actions |
| R-06 | PASS: existing Cyrillic-friendly sans and distinct title/body/metadata scale, with reasons in DESIGN.md |
| R-07 | PASS: no background grid or pattern introduced |
| R-08 | PASS: one send arrow communicates submission direction; no decorative arrow proliferation |
| R-09 | PASS: no novelty/marketing badges added; source chips open real source content |
| R-10 | PASS: no glass layers introduced |
| R-12 | PASS: subtle composer elevation identifies the editable area; transcript remains flat |
| R-13 | PASS: no glow introduced |
| R-14 | PASS: equal starter tiles are peer actions with actual draft preparation, rationale recorded |
| R-19 | PASS: finite arrival/expansion/press feedback follows MOTION 2; no idle animation loop |
| R-22 | PASS: no stock or generated illustration added |

### Liveliness

| Item | Status and evidence |
| --- | --- |
| Dials explicit | PASS: AI uses ENERGY 2 / RHYTHM 2 / MOTION 2 in DESIGN.md |
| Dial consistency | PASS: expressive jade actions, distinct transcript/composer rhythm and finite transitions |
| Focal point | PASS: composer leads conversation work; welcome has one primary creation action |
| Whitespace | PASS: bounded reading width separates conversation, sources and response controls |
| Accent | PASS: jade highlights meaningful actions and selected states |
| Identity motif | PASS: A1, warm paper surfaces and document/conversation shapes retain the workspace identity |
| Design read | PASS: direction declared before edits and recorded in DESIGN.md |

### Craftsmanship and quality locks

| Item | Status and evidence |
| --- | --- |
| C-1 | PASS: color, reading width, hierarchy and motion have written reasons |
| C-2 | PASS: new controls have exercised behavior, with no automatic message submission |
| C-3 | PASS: history, transcript, source access and response controls serve existing chat work |
| C-4 | PASS: both themes, narrow/desktop layouts, keyboard, empty/error/progress and recovery states checked |
| C-5 | PASS: verification claims correspond to executed checks; real-provider limits stated below |
| R-05 | PASS: no landing-page filler, metric grid or decorative feed introduced |
| R-11 | PASS: control, composer, source-chip and message shapes have distinct roles |
| R-15 | PASS: labels name concrete operations rather than generic marketing CTAs |
| R-16 | PASS: no AI marketing buzzwords added |
| R-20 | PASS: approved A1 and warm workspace language remain present alongside scoped jade actions |
| R-21 | PASS: existing system/light/dark selection retained and verified |
| R-29 | PASS: neutrals, scoped jade action and existing plum navigation; no extra decorative palette |
| R-30 | PASS: no reference-product screen copied |
| R-31 | PASS: major visual decisions and peer starter-tile purpose documented in DESIGN.md |

## Boundaries

All browser APIs were mocked. No real provider traffic, secret reads, deployment,
push or application migration occurred. Live backend/provider behavior, physical
mobile keyboards, other browser engines and screen-reader operation were not
tested. Backend checks were not rerun for this frontend-only refinement.
Screenshots use synthetic fixture content and are not real user conversations.

## Floating assistant (2026-11-22)

A branded launcher in the workspace's bottom-right corner opens a non-modal assistant
above the current section. The full AI section keeps its own layout. The floating
surface lazy-loads the existing ChatArea and shares its conversation API, source
picker, response options, streaming, run details and exact action confirmations.
Opening the launcher does not create a conversation or dispatch a model request.
Minimizing keeps the component mounted, preserving the draft and active request.
Switching conversations protects a draft; page unload also warns about unsent text.
The composer has a separate ID so a hidden floating chat cannot steal the full
AI page's label or starter-topic focus.

Design: ENERGY 1 / RHYTHM 1 / MOTION 1. The existing A1 avatar and theme tokens
provide identity. A shadow marks only the launcher and floating surface as elevated;
there is no new palette, illustration, animation or decorative background. Desktop
width is bounded at 440px. On phones the surface expands above the navigation dock
and replaces the launcher until minimized, leaving more room for the transcript.

Verification for this change:

- Production build, ESLint and TypeScript checks passed.
- The existing AI and AI redesign browser suites passed: 51 tests using mock APIs.
- CLI browser checks covered launcher, new conversation, history selection, sending,
  draft persistence after minimize/reopen, and staying on the calendar URL.
- Rendered text contrast and viewport bounds passed at 320/390/834/1440px in both
  themes, measured after theme transitions settled. No horizontal page overflow.
- Screenshots inspected at desktop and phone sizes. All new controls have native
  buttons, accessible labels, visible focus, and 44px-or-larger targets. Nested
  source/history dialogs retain the existing native dialog behavior.

Anti-slop delivery gate, scoped to this addition:

- Hard gate PASS: bounded layouts and AA contrast in eight viewport/theme states;
  the existing chat supplies loading/error/empty states, verified by the reused
  browser suites. No new claims, testimonials, links or fictional product data.
- Purpose gate PASS: A1 is reused for brand identity; elevation separates the panel
  from the calendar; tokens follow the selected theme. No gradient, glow or blur.
- Liveliness PASS: declared 1/1/1 dials, branded launcher as the entry point and
  a compact header/transcript/composer hierarchy with restrained existing accents.
- Craftsmanship PASS: existing chat behavior is reused rather than duplicated;
  creation, history, submission and minimize were exercised on the running build.

The browser checks use synthetic content, not live model output. This change does
not deploy the website or alter backend permissions, prompts or provider settings.

## Markdown answers and assistant marks (2026-11-22)

AI transcripts and streaming drafts now share a react-markdown/remark-gfm renderer:
headings, emphasis, lists, block quotes, tables, inline code and fenced code blocks.
Known `[source:id]` markers become source buttons through a text-node remark
transform; code blocks and inline code retain the literal marker. Unknown references
stay text. Raw HTML is escaped, executable URLs are rejected, external links use
noopener/noreferrer, and Markdown images render their alt text without network loads.
Tables and code blocks have bounded horizontal scrolling in the floating panel.

The floating assistant's existing A1 avatar is clipped to a circle, including in its
header. The navigation uses a compact AI wordmark with the existing accent tokens.
The launcher is placed after workspace content in DOM order to preserve the skip
link as the first keyboard stop.

Synthetic browser checks verified rendered headings/emphasis/list/table/code,
clickable known citations, literal citations inside code, and no script execution,
unsafe anchor or remote image. Calendar removal checks verified cancel, stale-version
conflict, preservation of existing local overrides and removal of only one occurrence.
The new-version-zero override preserves null inherited fields. Existing official
schedule rows are never deleted. UI checks do not spend provider quotas.

Dependency audit: production findings were limited to the already locked Next.js
package; no Markdown-package finding was reported. Framework updates are outside
this change. This is not a clean audit of the entire dependency tree.

Verification result: 64 AI/deep-link browser scenarios passed; the final calendar
recheck passed all 17 scenarios after restoring skip-link order. Calendar domain,
service and availability tests passed 47/47. Production build, lint and typecheck
passed. The Markdown panel passed viewport bounds and rendered-text AA contrast at
320/390/834/1440px in light and dark themes.

Delivery gate for these changes:

- Hard gate PASS: Markdown/XSS and occurrence-removal assertions ran in the browser;
  eight theme/width states had no horizontal overflow or text contrast failures.
- Purpose gate PASS: the AI lettermark identifies the existing assistant destination;
  the circular crop reuses A1, and monospace is limited to code content.
- Liveliness PASS: the established 1/1/1 design direction and theme accents remain;
  semantic headings/lists/tables provide hierarchy inside answers.
- Craftsmanship PASS: shared rendering covers full and floating chats; tested
  confirmation, cancellation, version conflict and unchanged unrelated occurrences.

## Calendar action review (2026-11-22)

Design Read: retain A1 and the established ENERGY 1 / RHYTHM 1 / MOTION 1 direction.
The calendar grid is the decision surface. Dashed themed blocks mean proposed data,
while separate previous/proposed lanes explain movement. The complete batch stays
in a bounded detail scroller with visible confirmation controls. The calendar itself
scrolls to the proposal without scrolling the page. Existing task/filter panels are
temporarily omitted to leave room for the review. No new branding assets were added.

Entry uses one 240ms transition; applied cards have one 700ms outline transition.
Approval or rejection restores the originating full chat or the still-mounted floating
chat. Reduced motion disables these animations and the return delay. Escape returns
without deciding; a visible button allows reopening a pending proposal manually.

Executed synthetic browser checks covered preview without writes, mixed batch details,
before/after movement, explicit date links, cancellation/Escape, rejection, exact-once
approval, conflict, expired receipts, navigation protection during saving, reduced
motion and restoration of the floating chat and original calendar URL. Bounds and
visible decision controls passed at 320/390/834/1440px in both themes. Captured phone
and desktop screens were visually inspected. Measured ghost text contrast was 6.72:1
in light mode and 7.98:1 in dark mode. These are scoped checks, not a full accessibility
certification. No provider API or quota was used; this change is not deployed.

Delivery gate, scoped to this change:

- Hard gate PASS: both themes fit the tested widths; native named controls, keyboard,
  loading/error states, bounded animation and reduced motion are supported. Synthetic
  proposal content is test evidence, not shipped product data or marketing claims.
- Purpose gate PASS: dashed borders distinguish projected data; the real time grid
  locates the proposed change. Accent and motion explain preview and commit states.
  Existing brand/type/radius tokens remain; no decorative gradients, glow or blur.
- Liveliness PASS: the existing 1/1/1 direction remains; the proposal on the time grid
  is the focal point, with structured space for details and explicit decisions.
- Craftsmanship PASS: the existing batch approval component and digest contract are
  reused, including partial plans and conflicts; source chat state is preserved.

Review state is deliberately transient. Reloading the calendar does not restore the
review panel; the pending proposal remains available from its conversation.

Final verification: production build, ESLint, TypeScript and `git diff --check`
passed. All 81 AI, calendar and deep-link Chromium scenarios passed on the final
build, in addition to the targeted browser CLI assertions above.
