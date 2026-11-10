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
