# Freeze review and decisions

Status: design decisions locked 2026-10-19; full scientific protocol remains NOT_FROZEN pending evidence gates. See `FREEZE_STATUS.md`. No evaluated model predictions were made by this protocol workstream.

| Decision | Candidate choice | Evidence or remaining gate |
|---|---|---|
| Dataset | source_records=100 current-release cases, 74 execute / 26 clarify; historical origins tracked separately | Current Data release metadata; old paper figures are stale |
| Human review scope | Routes/strategy sequences and named auxiliary approvals | Full semantic-field verification still needed |
| Main model | Gemini 2.5 Flash-Lite | User choice; Google docs checked; project access unverified |
| Hosted revision | Log requested ID and returned modelVersion | No fabricated immutable checkpoint/GPU/precision |
| S0/S1 | Essential: S0 one call 8192/2048; S1 two calls 4096/1024 each; thinking on | Implementation/prompt hashes and non-test smoke required |
| S2 | Optional independent interpretation + adjudication on exact dictionary inequality | User decision complete: optional; activation requires a pre-experiment amendment |
| Primary endpoint | Fully correct resolved task by turn five | Verified semantic references and hypothetical-answer coverage absent/unverified |
| Initial question | Separate policy/question score | Never counted as a completed task |
| Five runs | Seeds 17,29,43,71,101 | Seed is logged; provider determinism not promised |
| Confidence intervals | 10,000 paired case bootstrap samples, seed 20261019 | Case-mean across seeds, branch-mean first |
| Ablations | Five independently specified removals | Verify each removal in code and preserve matched controls |
| Subgroups | Relevant dialogue / explicit linked dependencies | Independently verified eligible-ID manifests needed |
| Second model | Unselected | Revise efficiency scope or justify/pin second hosted model before prediction |
| Budget | S0 2048/8192; S1 two calls 1024/4096 each | Candidate settings need non-test length/schema smoke; S2 cost explicit |
| Semantic scoring | Independent blinded adjudication of rubric cases | No route-to-semantic substitution or synonym-only certification |

## Already complete in the supplied release

Dataset naming/version, source_records=100 current-release count, separate historical origin counts, 100 sequential current IDs, 100 approved routes/strategy sequences, resolution of the three historical route disputes, crosswalk, separate source and label files, manifest hashes and synthetic provenance disclosure are already present. Do not redo or reopen these as annotation work. The gates below concern safe inference construction and scientific endpoints beyond approved routing.

## Required before initial evaluation predictions

- [x] Current data integrity and derived split/hash checks pass; negative leakage tests reject reference fields and unexpected intermediate-context keys. Final freeze archive remains a separate open gate.
- [ ] Record development examples, audit exposures and overlap screening; never tune on held-out cases or manuscript worked examples derived from them.
- [ ] Obtain live non-test smoke success using the requested model and explicit candidate settings; preserve modelVersion and token metadata.
- [x] Record S2 as optional: user confirmed main comparison is S0/S1, 10 total runs.
- [ ] Decide single-model versus second-model efficiency scope before activating efficiency comparisons.
- [ ] Freeze implementation, exact prompts, schema, validation, error/retry policy and request schedule; verify no silent reference loading.
- [ ] Freeze independently verified semantic-reference eligibility and scoring rubric before examining predictions. If unavailable, authorize only a separately labelled routing feasibility study; primary task correctness stays NOT_COMPUTED.
- [ ] Freeze verified hypothetical answer branches, matching rules, branch references and coverage; multi-turn results remain gated otherwise.
- [ ] Freeze dialogue, dependency and provenance subgroup manifests; do not infer eligibility from post-result effects.
- [ ] Archive config/code/data/prompt hashes, runtime inventory and a dated freeze record. Candidate files alone do not satisfy this step.

## Required before any claim of semantic results

- [ ] Lock every scheduled prediction/attempt and all five runs; document deviations without rerolling unfavorable outputs.
- [ ] Validate scoring on deliberately correct/wrong developer fixtures and retain independent review evidence.
- [ ] Complete independent semantic judgments with system identity hidden and resolve borderline disagreements.
- [ ] Report eligible denominators, infrastructure failures, missing coverage, paired intervals and run variability.
- [ ] Separate observed API outputs from simulated replies and hypothetical completion; no human-conversation claim.
- [ ] Review changed predictions before attributing mechanism to an ablation.

## Review performed on this candidate

Checked current release counts and human-approval limits against Data documentation; removed the stale 99-only assumption; separated initial routing, justified questioning and full task completion; prevented route-only semantic scoring; specified paired-case rather than flattened seed confidence intervals; retained thinking for direct generation; exposed S2's extra budget; treated hosted version/hardware as provider information; retained clarification and semantic coverage gates. Independent read-only review ran unittest discovery: 24 tests passed at review time, including data integrity, leakage boundaries, staged budgets, malformed output and paired-denominator checks. Candidate JSON syntax and cap consistency checks also passed locally. Candidate settings now match implementation: thought summaries off, timeout 90 seconds and no automatic retries. The runner distinguishes response-JSON parse success from prediction task-validation errors. Remaining gates are deliberately open and are not completed experiments.


## Review alignment amendment ? 2026-10-19

The independent code review found candidate/runtime mismatches in thought-summary requests, timeout, retries and the optional S2 disagreement trigger. These candidate files now record actual development behavior: `includeThoughts=false`, 90-second timeout, zero automatic retries/no retry waits, and exact structured dictionary inequality for S2 adjudication. Thinking itself remains enabled with the explicit token budgets. These documentation corrections do not freeze the evaluated policy or authorize held-out predictions. Existing release completion and user confirmation of optional S2 are recorded as completed decisions; semantic-reference coverage, simulation eligibility and final immutable protocol/code/prompt archive remain open.


## Source-count clarification

The current release has 100 source/model-input records. Historical provenance is 99 prior-subset records plus one assistant-authored synthetic record, already included in that 100. All 100 remain the primary protected evaluation set. The 1.0.1 metadata clarification changes no model-input rows or approved routing labels. A historical-origin sensitivity analysis is optional descriptive work and does not establish a mandatory 99-case evaluation.
