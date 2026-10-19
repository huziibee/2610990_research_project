# Seed 17 protected evaluation -- implementation staging handoff (2026-10-19)

This is the historical PR #12 scaffold note. Its five additive files have now been reconciled with the newer local Gemma implementation. See [current implementation handoff](GEMMA_SEED17_LOCAL_HANDOFF_20261019.md) for completed runner/recovery/scoring work and the remaining scientific release gates. The staging checklist below is preserved as PR provenance.

**DO NOT launch held-out inference. This branch contains the safe scheduling, pairing, and attempt-journal core only.**

The current upstream `main` is still Gemini 2.5 Flash-Lite with 1000 scheduled
initial predictions (five seeds). The user has separately validated a *local,
not yet pushed* Gemma 4 26B A4B prototype with `thinkingLevel=minimal`,
provider schema, S0 4096 output tokens, S1 two 2048-output-token stages,
and synthetic clarification mock passes. Do not overwrite those changes,
merge this branch blindly, or claim that this branch contains the local Gemma
runtime.

## What is implemented here

- Deterministic 200-row **paired** S0/S1 schedule for seed 17, equal to the
  original five-seed schedule's first 200 rows; never changes the original.
- Deterministic 500-row five-ablation schedule, every intervention exactly
  once per case for seed 17.
- Schedule-only, hash-logged plan under a create-exclusive `runs/plans`
  directory and a read-only paired archive auditor that preserves errors.
- Crash-safe, no-reroll journal primitive with explicit
  `INTERRUPTED_UNRESOLVED_NO_REROLL` state. A start marker means a call
  *might* have reached the provider; interrupted requests are NOT retried.
- CLI `--execute` refuses protected execution; no API imports or calls in
  the planning path; no private references consumed.

## Run now from the combined local worktree (safe)

```powershell
py Data/verify_package.py
py -m unittest discover -s tests -q
py tools/plan_single_seed.py
py tools/plan_single_seed.py --prepare --output runs/plans/seed17_candidate_v1
```

Each `--prepare` output directory must be new. Do not use
`tools/run_experiment.py --execute` or `tools/plan_single_seed.py --execute`.
Do not run the old five-seed ablation sweep.

## Still required for a *real* protected runner

1. Commit/push and reconcile the local Gemma 4 backend, provider schema,
   thinking-disabled S0/S1 and synthetic dialogue smoke code first.
2. Implement a completely isolated evaluation-only question matcher with
   binding to *approved* clarification branches. It may release **one answer**
   only after a matching model question. End on readiness, no available
   answer, error, or the fifth turn. Do not pass gold into model generation.
3. Implement the protected live engine integrating attempt-claim journaling,
   10-15 RPM / 16K TPM quota-aware pacing, explicit before-call fsync, call
   records, frozen settings and hashes, and safe handling of interrupted
   attempts without replay. A provider/network error is an experiment attempt,
   not grounds for an unrecorded retry.
4. Extend the readiness checker for this **versioned** single-seed protocol.
   The old checker expects five seeds and independent human approval; do not
   weaken it silently. Independently approve or explicitly record a supervisor
   authorized *alternative* if human verification cannot be obtained.
5. Implement one-seed-only output seals and trajectory/scoring audit.
   One seed permits paired case-level CIs, not between-seed variance.
6. Complete live synthetic S0, S1 and multi-turn smoke before freezing.
   Tests passing alone do not open evaluation permission.

The author-review `AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED` private release
is preserved and must not be silently relabeled FINAL_APPROVED. The 100 source
records and route decisions remain untouched.

**No scientific results were generated in this workstream.**
