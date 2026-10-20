# Gemma seed-17 pre-evaluation engineering, 20 October 2026

This work continues commit `410fe44` on draft PR #13 using the latest local files. The selected reference methodology remains **AUTHOR_APPROVED_AGENT_ASSISTED**. No protected predictions, protected judging or ablations have been executed. No launch authorization, reviewer identity, semantic guarantee or signature has been manufactured.

## Implementation

- The judge tool schema requires prediction/reference evidence pointers, including existing empty arrays when a feature is absent. The operative rubric is included in the Live request. All local pointer checks remain strict. The original configurations are preserved under `protocol/amendments/pre_final_engineering_410fe44/` and in Git history.
- Separate registered synthetic sessions now have separate request identities in the shared quota ledger. Reopening an attempt inside a session replays a valid receipt or blocks an ambiguous send; it never rerolls. Judge receipt loading verifies both durable files before replay and cannot manufacture a request when either is missing.
- The live generator smoke uses separate model and synthetic-oracle child processes. The synthetic oracle delegates to the production author-approved matching implementation, accepts only the canonical question at the next turn, and releases one approved invented reply. No protected reference is used for calibration. Request journals, initial predictions, trajectories, stop reasons, oracle events and raw usage remain local and immutable.
- Generic generation instructions specify typed values, capability/argument identifiers, one missing field per question, no invented planning actions, and use of the latest dialogue reply as evidence. These changes were developed only with invented examples. The second fixture removes a persistent claim that both values are unspecified after replies arrive. Neither the provider schema nor local task validator was relaxed.
- The separate version-5 gate supports an immutable **PREPARED_UNSIGNED** technical freeze with exact code, prompts, runtime, protocol, schedule, reference and scoring bindings. Explicit launch authorization remains a separate hash-bound artifact. Version-4 checks and the historical independent-review implementation remain available. The candidate protocol's execution flag stays false and the original freeze stays unsigned.

## Scientific scope

The 100 author-reviewed references (74 execute, 26 clarify), 26 approved branches, exact author receipt, source bindings, annotation ledger, encrypted archive and matching/eligibility rules are preserved. Mechanical validation does not prove semantic truth. No independent human verification is claimed. Author-review bias, automated judge bias, shared model errors, self-reported confidence, exact-question coverage, simulated replies and single-seed uncertainty remain limitations. The judge's requested model ID is pinned; a provider revision unavailable from Live is recorded as unavailable.

## Authorization and eventual commands

**Do not execute these launch commands until the author explicitly authorizes this exact technical release.** Preparation does not authorize execution. Do not edit the pinned source protocol or unsigned root freeze to record permission: that changes the validated release.

After actual authorization, a separate local evidence document must contain the actual author, the verbatim authorization, timezone-aware authorization date, study `gemma4-seed17-v1`, scope `seed17_main_with_approved_clarification_only`, and exact technical-freeze, base-artifact and root-freeze hashes. Its status must be `EXPLICIT_USER_LAUNCH_AUTHORIZATION`. Only then may it be hash-bound as `authorization_evidence` in a copy of the prepared bundle. This is documentary attestation, not identity authentication. No such document has been created by this work.

```powershell
# Read-only preflight; exit 2 is expected before explicit authorization.
py tools/check_seed17_readiness.py --bundle runs/readiness/gemma_seed17_prelaunch_freeze_20261020_01/candidate_bundle.json

# Future launch, only with separately authorized_bundle.json and a green preflight:
py tools/run_single_seed.py --execute --bundle runs/readiness/gemma_seed17_prelaunch_freeze_20261020_01/authorized_bundle.json

# Future explicit resume: immutable receipts replay; ambiguous requests never rerun.
py tools/run_single_seed.py --execute --resume --bundle runs/readiness/gemma_seed17_prelaunch_freeze_20261020_01/authorized_bundle.json

# Future scoring, only for the authorized sealed main run:
py tools/score_single_seed.py runs/evaluation/seed17/gemma4-seed17-v1 --automated --run-judge --bundle runs/readiness/gemma_seed17_prelaunch_freeze_20261020_01/authorized_bundle.json --judge-directory runs/judgments/gemma4_seed17_main_v1 --output runs/readiness/gemma_seed17_prelaunch_freeze_20261020_01/main_scores.json
```

The fixed main execution directory prevents alternate reroll runs. The separate 500-prediction ablation schedule is prepared only; these commands do not launch ablations. Failed attempts and earlier evidence must remain preserved.

## Verified completion and exact blockers

The final local safe package passed **316 tests**, frozen-data verification, synthetic S0/S1 and clarification checks, all five mock judge fixtures, and the complete **200-initial-prediction / 528-call mock**. The 500-prediction ablation schedule was prepared only. Exact release validation accepted all **100 references / 26 branches**, source and ledger bindings, matching rules and eligibility labels without changing their provenance. Evidence is under `runs/readiness/gemma_seed17_final_safe_20261020_03/`; the current bundle is `runs/readiness/gemma_seed17_prelaunch_diagnostics_20261020_01/candidate_bundle.json`.

The exact current gate is **30 passed / 6 blocked**, `ready=false`, `ready_for_authorization=false`, `protected_execution_authorized=false`. This is not a scientific result. Earlier initial smoke evidence is not substituted for a changed prompt. No final technical freeze directory was created: its preparer correctly refused incomplete live evidence.

Remaining live validation:

1. `live_synthetic_smoke_S1`: latest initial S1 goal call returned HTTP 500. Current S0 initial prediction passed.
2. `live_multi_turn`: latest S0 initial clarification passed, but its first post-answer direct call returned HTTP 500; S1 failed at its initial goal call. Both failures have durable claims and receipts, no Retry-After value, and no retry. After an explicit resume advanced only to the previously unattempted S1 request, the second HTTP 500 stopped further live calls. Failed requests must not be silently rerun.
3. `automated_judge_calibration`: all evidence-path checks passed in the last live five-fixture session, but the inconsistent-reference fixture returned a decisive incorrect verdict rather than abstaining (four fixture outcomes passed, one failed). The final separately versioned rubric strengthens reference/source-conflict priority and local nonempty evidence checks. It passed mock/scoring tests; its new live calibration was deferred after repeated provider errors. Earlier successful calibrations do not qualify for this final code/configuration.

Conditional release steps:

4. `automated_evaluator_frozen` and 5. `frozen_protocol`: prepare the immutable unsigned technical release only after the required current-code live checks pass. The implemented preparer refuses the present bundle. Its refusal is archived locally; no freeze or signoff was fabricated.
6. `signed_off_release`: explicit author launch authorization remains absent and must remain a separate final step.

The generic dialogue-grounding adjustment has not yet been verified through successful post-answer provider responses; no claim that it fixes model behavior is made. HTTP 500 establishes a provider-side failure response, not its underlying cause, invalid credentials or a proven quota problem. No provider errors were converted to successful predictions or removed from the denominator.

## Preserved diagnostic evidence

- `runs/judgments/seed17_gemini38_evidence_contract_v3_live_20261020_01/`: earlier five-fixture pass before the final session/replay and abstention-contract changes; retained, not reused as final calibration.
- `runs/judgments/seed17_gemini38_final_authorization_guard_20261020_01/`: local quota request-identity collision before sending; subsequent registered sessions use distinct synthetic identities.
- `runs/judgments/seed17_gemini38_final_authorization_guard_20261020_02/`: five live fixture outcomes passed under an earlier implementation; later receipt-replay regression was fixed, so this is historical evidence only.
- `runs/judgments/seed17_gemini38_final_replay_verified_20261020_03/`: four passes and the preserved failed abstention fixture. The final rubric was strengthened afterwards, without changing any fixture or accepting the failed outcome.
- `runs/development/gemma_seed17_isolated_oracle_live_20261020_01/`: paused by the source fingerprint guard during concurrent engineering edits.
- `runs/development/gemma_seed17_isolated_oracle_final_live_20261020_02/`: S0 repeated its answered question and the strict oracle stopped; S1 produced an invalid task after its first reply.
- `runs/development/gemma_seed17_dialogue_v2_final_live_20261020_03/`: latest current-code HTTP 500 failures. Its explicit resume did not rerun the failed S0 request. Three request receipts preserve one successful initial S0 response and both provider errors.

Earlier quota pauses, invalid source-pointer responses and historical 19 October diagnostics also remain unchanged. None of these local logs, private reference exports or keys is committed.

## Manuscript and files

The current manuscript was recompiled with verified Tectonic 0.17.0 (compiler exit 0) into `output/pdf/Cooccurring_Ambiguity_Paper_Gemma_Seed17_Working.pdf`. All four pages were rendered for visual inspection. It describes the actual methodology and remaining live blockers, contains no protected findings, and preserves the earlier manuscripts and PDFs.

Changed implementation groups: `research/seed17_judge.py`, `research/automated_semantics.py`, `research/seed17_gate.py`, new `research/seed17_freeze.py`, the RPC client and synthetic oracle/fixture, generic system instructions, calibration/coordinator/safe-validation tools, new freeze-preparation tool and synthetic prelaunch tests. Updated protocol/rubric files have raw historical copies and a versioned amendment. Attributes preserve historical configuration bytes. The pre-existing untracked `README_PRIVATE_REFERENCE_RECOVERY.md` is preserved and excluded from the commit.
