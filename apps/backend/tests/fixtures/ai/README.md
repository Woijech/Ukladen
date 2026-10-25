# AI-00 Synthetic Acceptance Contracts

Status: specification data only; no AI runtime or behavioral test implementation.
All identities, source text, calendar data and requests are synthetic. No credentials,
private documents or live vendor responses are included.

[ai-00.json](ai-00.json) contains fixed context and 36 required/forbidden outcome cases.
Cases describe the target across stages; they are not current pytest tests or evidence
that any scenario works. Each implementation stage turns its relevant cases into
meaningful fake/service/HTTP/native/browser checks.

See [tool contracts](../../../../../docs/development/ai-tool-contracts.md) for
schemas, versions, bounds and expected execution guarantees. Preserve case IDs when
adding stage-specific fixtures or held-out evaluation data.

## AI-09 release acceptance

[ai-09.json](ai-09.json) is a separate 40-case bilingual suite for the delivered subset:
28 Russian/12 English, with 20 development and 20 held-out cases. It records synthetic
setups, expected/forbidden outcomes and critical safety cases. Original AI-00 IDs and
historical automatic-action scenarios remain unchanged; AI-08 is now deferred indefinitely.
The suite is acceptance data, not 40 executed real-model tests. See the
[review tool and quality gate](../../../../../docs/development/ai-09.md#synthetic-suite-and-review-tool).
