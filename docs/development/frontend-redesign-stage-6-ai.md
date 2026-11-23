# Frontend redesign stage 6: AI conversation

Date: 2026-11-13. Status: implemented locally on `frontend/ui`; not pushed/merged/deployed.
Follows the [AI interaction specification](frontend-interaction-spec.md#8-ai-conversation).

## Delivered

AI now inherits the same plum action/focus palette, neutral paper surfaces and compact
heading/tab rhythm as calendar/tasks/notes/databases. Transcript and composer are the
main working plane. Desktop keeps a 224px secondary conversation list. At 900px and
below History explicitly opens a modal with focus return; selecting/creating/deleting
a conversation closes that history surface without bypassing the existing dirty guard.
A separate new-chat action remains available. Empty history pagination no longer
consumes space; existing 20-item offset pagination remains when required.

Messages use readable 16px type and constrained reading width. Copy is a local
contextual message action, revealed by hover/focus on desktop and always available
for touch. Clipboard failure gives manual-copy guidance. Source citations and their
safe preview/open actions remain associated with the original answer. An explicitly
empty scope now says “without sources” rather than an ambiguous zero; automatic
scope remains a distinct null selection. Context selection and response settings do
not send a request. Enabled source-only/full-document settings remain in the existing
collapsed summary. No new model switching, edit/resend, provider probe or fake tool
is introduced.

## Preserved execution contract

Submission IDs, streaming/reconnect recovery, stored runs, cancellation, background
full-source processing, exact scope payloads and immutable conversation model/connection
identity are unchanged. HITL proposal rendering, warnings, immutable digest preview,
confirm/reject/edit/re-preview, stale/expired outcomes and source provenance are not
replaced by a chat shortcut. Context/history/copy do not confirm proposals. Review,
usage, connection and permission-bound diagnostics screens remain reachable.

## Findings addressed

| Finding | Priority | Resolution |
| --- | --- | --- |
| AI used a separate green action/focus system | P2 | Inherits the shared brand tokens in both themes |
| In-flow history consumed narrow-screen conversation space | P1 | Explicit History modal, retained draft and focus return |
| Empty scope looked like an unexplained zero | P1 | Distinct explicit no-sources label; payload semantics unchanged |
| Copy required manual text selection | P2 | Labelled local copy with success/failure feedback |
| Disabled pagination competed with content | P2 | Show history pager only when a page boundary requires it |

## Verification

Lint, typecheck, production build and Compose validation passed. The final AI suite
passed **47 tests (1.3m)**; a subsequent focused run passed **6 tests (10.0s)**, including clipboard failure.
[Desktop light](../design/frontend-ai-stage-6-desktop-light.png),
[desktop dark](../design/frontend-ai-stage-6-desktop-dark.png),
[phone light](../design/frontend-ai-stage-6-mobile-light.png) and
[phone dark](../design/frontend-ai-stage-6-mobile-dark.png) retain rendered evidence.
All AI routes and streams are synthetic;
no real provider request, key inspection, activation or external spending is authorized
or performed. Tests cover source scope/citations, duplicate/recovery/cancel behavior,
explicit HITL decisions and permission-bound advanced screens, plus the new responsive
history/copy/context interactions at 320/390/834/1440px in both themes.

## Limits

History drafts and clipboard notices are local to the mounted conversation. Existing
memory-only dirty guards remain; no crash recovery or offline mode is claimed. Native
clipboard availability can differ by browser. Hardware phone keyboards, screen readers,
Safari/Firefox and real-provider compatibility have not been validated by this UI work.

## Collapsible conversation history — 2026-11-23

Implemented on `frontend-ui`. A desktop toolbar toggles the 224px conversation
column with a 240ms grid transition. The hidden history is inert and removed from
the accessibility tree; the active conversation remains mounted, preserving its
draft, source scope and running request. The toolbar retains new-chat access when
history is collapsed. Mobile and floating assistants keep the existing history
dialog and focus-return behavior. Reduced-motion preferences disable the transition.
The top-level tabs, theme tokens and API contracts are unchanged.

Verification before the history commit: all 53 AI browser cases passed, including
desktop collapse/draft preservation and mobile/reduced-motion behavior. All 77
selected native AI HTTP/streaming/agent/tool-selection tests passed against a
separate disposable PostgreSQL/Redis target. Frontend lint, typecheck and production
build, backend Ruff/format/Pyright, Compose validation and whitespace checks passed.
The first browser pass exposed duplicate visible new-chat actions; the final pass
includes the corrected single-action behavior. Browser screenshots were inspected.
Only synthetic providers were used; the running application was not redeployed.

## Compact AI composer — 2026-11-23

Implemented on `frontend-ui`. The composer uses one rounded input surface with a
compact circular send/stop control and source/response controls below the textarea.
The visible send label is replaced by an arrow; accessible names, disabled states
and the explicit Ctrl/Cmd+Enter shortcut are retained. Plain Enter still inserts a
newline and composition events cannot submit. The textarea grows with content in
browsers supporting `field-sizing`, with bounded height and a resizable fallback.

Response settings open from a labelled button in a viewport-bounded native popover.
Escape returns focus to its trigger; outside clicks dismiss it. Both source-only
and full-document settings, their help, running-request locks and full-document
validation are retained. Active modes remain visible below the closed composer
toolbar. The selected page/event context and source picker remain available in
both the full and floating assistants. No endpoint, request payload, model choice,
stream/recovery/cancellation behavior or action-confirmation contract was changed.

Final verification before the composer commit:

- All **363 frontend browser tests passed** on the final production build. The
  focused 14-case AI layout suite also passed separately. Coverage includes
  sending exact scoped payloads, CSRF, duplicate/recovery/cancel paths, full-source
  validation/progress, confirmation digests, settings and account isolation.
- New cases exercise keyboard/popover focus, active-mode persistence, IME safety,
  icon-only sending, desktop history, narrow layouts and floating draft retention.
  Floating Escape dismisses the popover before the assistant. Geometry assertions
  prevent source/response controls overlapping or escaping the input surface.
- All **206 selected backend/AI tests passed** against disposable PostgreSQL/Redis
  with synthetic providers, covering native HTTP/SSE/actions, grounding, tool
  discovery, mocked OpenRouter and deterministic evaluations. This is not a rerun
  of the complete backend suite or a live-model quality evaluation.
- Frontend lint/typecheck/build, backend Ruff/format/Pyright, quiet Compose
  validation, 30 local documentation targets and whitespace checks passed.
- Final light/dark desktop/mobile and floating screenshots were visually inspected.
  Earlier browser passes exposed ambiguous new test locators and a narrow floating
  control overlap; the final successful runs include their corrections.

The existing lockfile was installed without dependency-version changes because the
local modules were stale. No backend code, database schema, private configuration,
real-provider usage or running application containers were changed. Disposable
backend test containers and their synthetic data were removed after verification.
