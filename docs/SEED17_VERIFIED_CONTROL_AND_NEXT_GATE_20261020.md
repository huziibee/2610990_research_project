# Verified live control and next release gate - 20 October 2026

This is an engineering evidence record, NOT protected benchmark results or a model-adoption authorization. No manuscript work was done.

## Complete real S0/S1 control

[Run 39476606184](https://github.com/huziibee/2610990_research_project/actions/runs/39476606184), job 118814083436, completed successfully. Actual model: **gemini-3.5-flash-lite**, not Gemma. Source: `research/seed17-matched-control-20261020` at `ee255427575e62ab424d9929ed175345f0f71a71`; candidate [PR #25](https://github.com/huziibee/2610990_research_project/pull/25).

| Measured item | S0 | S1 |
|---|---|---|
| Initial prediction plus two approved invented answers | CLARIFY -> CLARIFY -> ACTION_READY | CLARIFY -> CLARIFY -> ACTION_READY |
| Model calls | 3 | 6 |
| Per-stage output cap | 4096 | 2048 + 2048 |
| First-attempt requests successful | 3/3 | 6/6 |
| HTTP failures, model failures, retries | 0 | 0 |

The independent auditor verified the actual wire payload hashes, response IDs, true model identity, task fields/types, exact source/dialogue/goal context, question eligibility, oracle events, request claims, response receipts, first-attempt status and full archive inventory. The cloud report records `current_code_snapshot_matches=true` against that executing candidate. The archive seal SHA-256 is `cffce8f1b6b4a0958418f123311eef463709371059dbd8f0e310ba431f619259`; artifact `seed17-matched-control-39476606184`, ID 12289404336. Downloaded evidence was independently checked again with the updated auditor; later audit-code changes do not turn this historical candidate into final current-release evidence.

This matches **output-token caps**, not identical total compute. Minimal-thinking behavior is model-specific; missing reasoning-token metadata remains unavailable, never asserted to be zero. The successful control uses a lossless typed-argument wire codec, not the original dynamic-key Gemma transport. One invented fixture is an end-to-end engineering check, not 100-case accuracy or a reliability guarantee.

## Other verified work

- [Run 39474482983](https://github.com/huziibee/2610990_research_project/actions/runs/39474482983): full safe validation passed 449 tests, the complete 200-initial-prediction main mock, 500-initial-prediction ablation mock and synthetic analysis. The main mock recorded 528 calls. These are simulations, not study findings.
- Current cloud judge calibration from [run 39459246588](https://github.com/huziibee/2610990_research_project/actions/runs/39459246588) independently reverified with `verify_calibration(require_live=True)`: 5/5 fixtures, correct raw-record hashes and relevant current judge-code fingerprints. Calibration SHA-256 `76358ce62574717a7eb4189c0f8741354ba323e35b456f2e4910b447819a12b1`. No repeat judge calls were made for that audit.
- Lossless codec/document stress check: 2,000 invented encode/decode round trips, zero source mutation or type/value changes, malformed documents rejected. No protected cases or model calls.
- [PR #24](https://github.com/huziibee/2610990_research_project/pull/24): raw-evidence auditor and nine adversarial tests. It rejects model relabelling, changed outputs even after resealing, missing claims, altered dialogue, incomplete trajectories and false success summaries. A bug reconstructing dialogue with canonical rather than the actual approved question spelling was reproduced and fixed; [latest CI passed](https://github.com/huziibee/2610990_research_project/actions/runs/39477768549).

## Original Gemma remains unqualified as a paired run

Do not combine successful S0 and S1 trajectories from different prompts/runs:
- Run 39474482983: S1 completed both answers but needed three preserved HTTP-error retries; S0 failed because an unknown argument had a null value and empty evidence.
- Run 39475956784: a generic omission example shared by S0/S1 allowed S0 to complete in three first-attempt calls; S1 initial grounding asserted an unknown time value with empty evidence and was rejected. No complete paired Gemma qualification.

The fastest supported next direction is to explicitly register and integrate the tested Gemini/codec profile, rather than keep rerunning the failing Gemma transport without a new hypothesis. This document does NOT make that model decision on the author's behalf.

## Reference-integrity bug fixed on main

Merged [PR #23](https://github.com/huziibee/2610990_research_project/pull/23) at `72d2f71a3b35215f1fb615f9b5bda47b3144da82` restores the exact original CRLF bytes of `protected_reference_archive/author_review_v1.manifest.json`. Its digest is now the already-approved `c215c0bf41ffba7b99858d622e4ec7acfe7c48beef7e48878bd24a273391ea4c`. Ciphertext remains `4290647c43bb69f0caf36c32601f9c6b2693eb399d8f42cf33fcf6ac151d48d0`. No reference, metadata value, receipt, policy hash or approval was changed. Added `protected_reference_archive/** -text` and four regression tests. Do not normalize pinned data to get a passing hash.

The private cloud job also showed **AUTHOR_REVIEW_AES_KEY_BASE64 absent**. The functioning `GEMINI_API_KEY` is not the decryption key. Supply the original 32-byte AES key through that repository secret, or use the original authorized local workspace. Never generate a replacement, expose the key, or commit private reference files. The usual original local key path is `~/.ambiguity-research/author_review_v1.aeskey`. The tested helper is `python tools/stage_seed17_private_release.py`; it verifies an existing approved workspace or restores the exact registered ciphertext without overwriting it.

## Remaining path to actual results

1. Author decides whether to adopt the tested alternative model/codec/thinking profile. Stage a versioned amendment and update generator, matching budgets, wire-record audits and ablation contracts consistently; retain the original Gemma contract as history. A candidate success is not automatically an active release.
2. Restore and validate original private 100-reference / 26-branch release using the original key. No second human review required.
3. Integrate all code, then qualify the final exact implementation (full main and all five ablation mocks, current live S0/S1, judge evidence, source/prompt/runtime hashes). Existing historical evidence can be audited, but must not be relabelled as a new code snapshot.
4. Generate a genuinely complete unsigned technical freeze and present its hashes. Obtain real exact-hash main authorization via the existing helper. Never invent approval.
5. Run and seal the protected 200-main-initial-prediction schedule, then obtain separate ablation authorization and run all five 100-case conditions (500 initial predictions plus approved clarification trajectories).
6. Isolated judging and real paired-case analysis. Preserve errors, unknowns and abstentions; publish actual scores only when supported. No paper writing.

Protected main predictions, protected ablations, real semantic judging and final statistical results remain **NOT COMPUTED**.
