# Contextual help

Supplementary explanations use the shared `HelpTooltip` question-mark button next
to the relevant heading, option or field. This applies to calendar controls and
sources, tasks and planning, notes and relations, collections, databases, materials,
search, notifications, settings, AI chat options, reviews and diagnostics.

Keep validation errors, action warnings, privacy notices, file limits, runtime
status and actual user data visible. Help must not be the only place users can
learn that an action is destructive or that a result is incomplete.

The component uses the native automatic popover: Enter or Space opens it, outside
click dismisses it, and Escape returns focus to its trigger without dismissing a
parent editor. Content is focusable and scrollable for long explanations. Position
is clamped to the viewport and recalculated when the viewport resizes. No new
package or API contract is required.

`workspace-help.spec.ts` covers task-draft preservation, keyboard focus, outside
clicks, scrollable calendar instructions, viewport bounds, light/dark contrast and
the absence of data writes from help interactions. Other workspace tests exercise
the affected screens and forms.

Verification: ESLint, TypeScript, production build and `git diff --check` passed.
The full browser run passed 347 scenarios; after updating obsolete/ambiguous test
selectors, clarifying a help button name and awaiting keyboard scroll, all nine
remaining scenarios passed on the rebuilt application (356 distinct scenarios).
Backend code and provider integrations were not changed or exercised.
