# Ablation engineering — guarded runner integration

**Status:** Implemented on a separate branch, awaiting local regression execution, independent code review and final evaluation freeze. No protected predictions or scientific results exist.

The existing experiment CLI now accepts `--phase ablations`. It shares the main runner's separate-process readiness preflight, generated-input integrity checks, fixed seed list, hosted settings, exclusive output paths, fail-closed malformed-response handling and per-call token/latency audit logging. `tools/run_ablations.py` does not import semantic references or scoring machinery.

## Test without Gemini or dataset evaluation

```powershell
git fetch origin
git switch research/ablation-engineering-20261019
git pull --ff-only origin research/ablation-engineering-20261019
py -m unittest discover -s tests -v
py tools/run_experiment.py --phase ablations
```

Dry-run plan prints 2,000 scheduled predictions and failed readiness gates. No model is called. Tests use synthetic cases and mocked responses only.

Create the candidate paired schedule **once**, only if it does not already exist:

```powershell
py tools/run_experiment.py --phase ablations --prepare-ablation-schedule
```

This writes `protocol/ablation_schedule_2000.jsonl` exclusively and outputs its SHA-256. Commit that candidate schedule when reviewed; do not regenerate it to alter case ordering or model results. The separate `protocol/ablation_plan_v1.json` remains disabled (`allow_ablation_predictions=false`).

## What is actually connected

| Ablation | Method | Important limit |
| --- | --- | --- |
| Goal-first | Reuse the existing S0 direct baseline | Not counted twice; S0 takes one call while other ablations take two |
| Structured grounding | Keep S1 goal stage and final schema; replace explicit grounding instruction with a weaker second-stage directive | Prompt intervention only, not removal of mandatory output structure |
| Scene | Remove substantive scene information from both stages | Different information conditions; scene-evidence claims need careful failure analysis |
| Dependency checking | Retain S1 generations, bypass deterministic relation validation only | This is a validation-layer intervention, not removal of model dependency reasoning |
| Dialogue | Remove dialogue turns from both stages | Meaningful subgroup requires independently verified dialogue relevance |

The 2,000 additional scheduled rows consist of 4 interventions × 100 cases × 5 fixed seeds (17,29,43,71,101). Each intervention is aligned with the existing S1 case/seed schedule. A single run contains exactly one result per (case, seed, intervention) with no retries or overwritten files.

## Explicit scientific and operational blockers

1. Execute and review the new synthetic test suite; correct any regressions before merging.
2. Confirm that the selected prompt-level and validator-level interventions measure the mechanism claimed by the paper; amend them before seeing held-out predictions if not.
3. Obtain independent semantic gold/reply coverage, verified model access and the primary freeze.
4. Separately freeze `protocol/ablation_plan_v1.json` with the SHA-256 of the final main protocol and 2,000-row schedule, set `status=FROZEN` and `allow_ablation_predictions=true` through an explicit reviewed amendment. Do not change the existing main protocol to bypass readiness.
5. Supply a fully verified readiness bundle and an exclusive output directory. Only then can `py tools/run_experiment.py --phase ablations --execute --bundle ... --output ...` run held-out predictions.
6. Score only after the immutable predictions are recorded, preserving unavailable model usage and errors; any results remain exploratory until semantic review.

**Nothing here authorizes evaluation early.** The main design remains `NOT_FROZEN`, and no benchmark model calls have occurred as part of this implementation.
