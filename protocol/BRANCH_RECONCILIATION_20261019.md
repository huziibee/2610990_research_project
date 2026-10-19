# Branch reconciliation and evaluation implementation decisions — 2026-10-19

This document records an engineering reconciliation, **not** a completed scientific freeze.

## Branch graph and choice

Connector comparison found:
- `main` → `research/annotation-triage-20261019`: 43 commits (annotation, review bundle, workbench, guarded ablation prototypes).
- `research/annotation-triage-20261019` → `research/runner-efficiency-20261019`: 9 additional commits (guarded runner, schedule plan, efficiency reporting, synthetic runner tests).
- `research/ablation-engineering-20261019` diverged from main and has a competing 13-commit implementation. **Do not merge its competing `research/ablations.py`, tests or scheduler.**
- This branch, `research/reconciled-evaluation-20261019`, starts at the runner-efficiency head and is the **single proposed integration branch**.

The divergent branch uses S0 direct generation as a goal-first-removal condition, while the chosen branch uses a two-call context-summary control. Both are informative comparisons, but counting S0 twice as a separate ablation confounds call count and budget with the representation. The chosen control keeps the same requested S1 two-stage caps, although stage text and actual token usage can still differ.

The divergent branch also schedules **2,000** initial predictions (four interventions, excluding goal-first as a separate condition); the chosen runner schedules **2,500** (five conditions × 100 cases × five seeds). The 2,500-row schedule is **a candidate, not frozen**, and is not a promise of equivalent causal identification across all five interventions. These schedules must not be combined.

The competing ablation engineering documentation is historical, not the live run plan. See `docs/RUNNER_INTEGRATION.md`, `protocol/ABLATION_IMPLEMENTATION_STATUS.md` and `protocol/ablation_plan_v1.json` for the chosen candidate design.

## Five candidate ablations and exactly what they test

| Registered ID | Selected implementation | Inference supported | Interpretation limit |
| --- | --- | --- | --- |
| `goal_first` | Two-call context-summary control | Contribution of **explicit intermediate goal representation** relative to an alternative two-stage decomposition | Does not fully remove latent model goal reasoning; text and intermediate content differ |
| `structured_grounding` | Two-stage grounding-prompt control | Contribution of **explicit grounding instructions** | Typed JSON schema and postprocessor remain; cannot claim removal of structured grounding |
| `scene` | Mask scene in both calls, disallow scene citations | Sensitivity to **available scene evidence** | A sentinel is used, not an absent field, because schema requires nonempty scene |
| `dependency_checking` | Remove selected deterministic same-value/order consistency checks | Contribution of **post-generation consistency filters** | Model still reasons about dependencies; contradicted outputs must be scored as wrong |
| `dialogue` | Replace dialogue with [] in both stages | Sensitivity to prior dialogue | Main mechanism claim should be restricted to independently verified dialogue-relevant subgroup |

These are five **registered engineering probes**, not yet five fully defensible causal architectural removals. In particular, `structured_grounding` needs a separate genuine representation-removal comparator if that precise wording is central to the manuscript. **Do not relabel the prompt-only proxy as a full removal.**

## Verification and release decisions

- Prior user-supplied full checkout: **115/115 synthetic tests passed** before these latest changes.
- Partial local workbench HTTP test: **6/6 passed**; not equivalent to all newer tests.
- GitHub workflow `Research regression checks` has not been observed completing successfully for this integration head; verify green CI and complete local checkout tests before merge.
- No live Gemini verification, approved semantic references, independently reviewed simulator branches or held-out predictions have been established.
- No merge into `main` is authorized by this document.
- Frozen case cohort, approved 74 execute/26 clarify routes, system budgets, seeds and semantic endpoint are unchanged.
- Model smoke tests belong to the user's local development runtime. Never use a key pasted in chat.

## Integration exit criteria

1. Run `python -m unittest discover -s tests -v` on a full checkout of this branch; fix new failures.
2. Verify GitHub CI run has completed, not merely been queued.
3. Review and seal the chosen 2,500-row schedule and intervention descriptions **before** any evaluated inference.
4. Independently audit full semantic gold, simulated answers, capability catalogs and subgroup labels; record separate review identities.
5. Complete live non-test Gemini S0/S1 checks and confirm requested model is actually available.
6. Approve a versioned final protocol/readiness manifest. Until then, no held-out prediction calls or semantic correctness claims.
