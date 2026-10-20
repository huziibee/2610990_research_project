# Five-seed ambiguity study: implemented execution path

The current user authorized Gemini 3.5 Flash-Lite, the lossless typed-argument codec,
main S0/S1 and all five ablations on seeds 17, 29, 43, 71 and 101. The actual quoted
approval is recorded in `protocol/five_seed/session_delegation_v1.json`. It is a
**delegation to bind the verified final release**, not a fabricated signature.
The old single-seed design and references are preserved, not silently rewritten.

## Scope

100 original author-reviewed cases; 74 initial execute references, 26 clarify
references, 26 approved answer branches. Main: 1,000 initial predictions. Five
ablations: 2,500 initial predictions. Nominal initial generation requests: 6,500,
plus clarification continuations; actual errors can reduce sent stages. Both S0
and S1 clarify. S0 permits 4096 output tokens; S1 uses 2048 per goal/ground stage.
The same model, wire codec, context and validation apply to matched conditions.
Capability prose remains model context and semantic evaluation evidence. A safety
catalog is NOT a prerequisite; schema/types/evidence and baseline dependency
checks remain. Unsupported or ambiguous questions stop without invented answers,
remain in denominators, and enter the manual-review inventory.

The structured-grounding intervention removes only the named grounding sentence;
other shared instructions and the codec remain. The dependency intervention
exposes invalid relationships for evaluation without disabling pointer/type
validation. Scene/dialogue masks apply at every stage and answer turn. Evaluators
see the original context plus only the actually released replies; generator
masking is independently audited.

## Commands

The default is read-only:

```
python tools/finish_five_seed.py
```

In an authorized environment with `GEMINI_API_KEY` and the original archive key
(standard local key file, `--key-file`, or native `AUTHOR_REVIEW_AES_KEY_BASE64`):

```
python tools/finish_five_seed.py --execute-all
```

This restores/verifies the original private release, runs the complete 1000/2500
mock cohorts, actual paired live two-answer qualification, actual five-fixture
judge calibration, all regression tests, and creates a new exact unsigned freeze.
It binds the recorded delegation to two distinct main/ablation scope records,
then executes, seals, judges and analyzes both real archives. No manuscript is
written. `--checkpoint-requests N` pauses cleanly before the N+1th new model
request; resuming reuses recorded goals/replies/responses, never resends failed
or unknown requests. The same command re-enters immutable known progress.
A missing/ambiguous provider receipt, failed qualification, changed code/runtime
or unmatched authorization stops execution; preserve its evidence, never delete
or reroll it. The final result verifier recomputes statistics from actual sealed
observations and verified judge receipts.

A model or judge error is not silently removed. Known failed judge packets remain
unresolved; subsequent re-entry can advance *unattempted* packets. Published
unknown-outcome bounds are not fabricated accuracy points or confidence intervals.

## Quota and runtime

One generation owner and shared project reservation ledger. Existing local RPM,
TPM and daily ceilings are retained. New reservations conservatively bound
**decoded text input bytes**, all tool/schema text and role overhead, avoiding
JSON transport double escaping and output allowances being counted as input.
An overlarge byte bound requires a durable same-model `countTokens` response plus
1024-token margin; an unsupported/missing/error response is not replaced by a
made-up estimate. Tokenizer RPCs are recorded separately and conservatively count
against local request ceilings; they do not generate predictions. Actual durable
response usage settles reservations, while failures and unknown sends retain
reservations. Missing token usage remains missing. Other clients in the same
provider project are outside this ledger's visibility. Provider rate limits are
not guaranteed by a local setting.

## Statistical outputs

The analysis uses **100 independent source-case units**, not 500 independent
replicates: branch means within case/seed, five seed means within each case, then
paired source-case bootstrap (10,000 resamples, seed 20261019, marginal 95%
percentile intervals). Per-seed scores and descriptive seed spread are separate.
Five ablation contrasts versus S1 are exploratory and not multiplicity-adjusted.
Every failure and unknown stays in the denominator. Initial routing and terminal
post-clarification correctness are different outcomes. Actual API revisions,
usage/latency, statements of unavailable cost data, errors, unknowns and evidence
hashes accompany the CSV/JSON/SVG outputs. Automated semantic judgments against
single-author-reviewed model-assisted references are not independent human truth
verification and do not certify physical robot safety.

## Secret and execution boundary

Use a native repository secret or the existing local key file. Do not commit keys,
private plaintext references, decrypted workspaces, or raw protected responses to
this public repository. Development workflows upload invented-only evidence.
Protected execution is not launch-ready merely because this code or CI exists.
All exact source/runtime/evidence checks must pass in the actual execution
workspace. Previous single-seed live evidence/freezes are historical only after
code changes. The original private reference bytes and original approval history
are never changed to satisfy a test.
