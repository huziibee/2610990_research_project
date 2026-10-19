# Guarded initial ablation runner and efficiency reports

**Integration branch:** `research/runner-efficiency-20261019`, based on the annotation/research branch (not a parallel replacement for its ablation implementations). This work contributes an experimental runner, schedule, logging, independent tests and an efficiency reporter. All existing protected-case/semantic reference preparation remains on the annotation branch.

## Run the engineering checks on Windows

```powershell
git fetch origin
git worktree add ..\research-runner-check origin/research/runner-efficiency-20261019
cd ..\research-runner-check
py -m unittest discover -s tests -v
py tools/run_experiment.py --phase ablations
```

The dry run reports readiness gates and the proposed 2,500 initial ablation predictions (normally two model calls each), but performs no model inference. Full semantic evaluation remains `NOT_COMPUTED`. Keep this worktree separate from the active annotation checkout.

Create the deterministic, candidate 2,500-row schedule exactly once:

```powershell
py tools/run_experiment.py --phase ablations --prepare-ablation-schedule
```

The command generates `protocol/ablation_schedule_2500.jsonl` exclusively, records its SHA-256, and never reads protected cases. An existing schedule cannot be overwritten. This schedule must be reviewed, archived, and its hash copied to the separately frozen ablation plan before any real experiments.

## Five interventions from the annotation branch

| ID | Runner dispatch | Research limitation |
| --- | --- | --- |
| `goal_first` | `predict_without_explicit_goal_stage` | Two-call context-summary control; may still encode implied goals in the summary |
| `structured_grounding` | `predict_without_explicit_grounding_prompt` | Explicit grounding-prompt removal **only**; the structured schema remains |
| `scene` | `predict_context_ablation(..., removal='scene')` | Scene withheld from both stages; citation of withheld evidence fails |
| `dependency_checking` | `predict_dependency_consistency_ablation` | Removes only deterministic relation consistency, not prompt reasoning |
| `dialogue` | `predict_context_ablation(..., removal='dialogue')` | Dialogue removed from both stages; requires verified dialogue-relevance subgroup |

The runner matches each intervention to the existing S1 case/seed grid: 5 interventions × 100 cases × 5 fixed seeds = 2,500 initial predictions. All five use two model calls with matched stage budgets. Inference counts, per-call records, provider model versions, failed attempts, latency and tokens are logged to a fresh exclusive directory. Outputs remain initial predictions; the 0–5 turn simulation is **not** executed here.

## Freeze boundaries

The current `protocol/ablation_plan_v1.json` has `status=CANDIDATE_NOT_FROZEN` and `allow_ablation_predictions=false`. Runtime execution requires BOTH the existing main readiness bundle and a separately reviewed, frozen ablation plan, bound to SHA-256 of the final primary protocol and 2,500-row schedule. Ordinary runs of `py tools/run_experiment.py --phase ablations` are read-only preflight; `--execute` remains blocked until the real gates pass.

After that separate freeze, the future invocation is:

```powershell
py tools/run_experiment.py --phase ablations --bundle protocol/your-reviewed-bundle.json --output runs/evaluation/ablation_run_001 --execute
```

This command is a **future** invocation only; do not enable it by editing one flag in isolation. No held-out predictions have been executed during this integration work.

## Efficiency summary from completed sealed runs

```powershell
py tools/report_efficiency.py runs/evaluation/ablation_run_001
```

The reporter reads sealed run logs only; it checks digests, rejects partial schedules, separately reports P50/P95 latency for all attempts and successful attempts, inference calls, token usage and missing token counts, and leaves unavailable hardware/pricing fields null. Synthetic mock outputs remain labelled `MOCK_ENGINEERING_ONLY`. **It neither loads gold nor reports task correctness.**

## Outstanding work

Run regression tests on a full checkout and independently review the code. Finish complete human semantic gold/replies, confirm live Gemini connectivity, freeze both protocols and generated schedules, then run and score the experiments. Structured representation removal and goal-first causal interpretation still need the separate scientific decisions documented on the annotation branch.
