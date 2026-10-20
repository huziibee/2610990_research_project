# Seed-17 coding-agent handoff — 20 October 2026

## Starting point

Start from `main` at integration merge `38714aa0d34dcebbea8384ce3e1427aba7b79b91` (PR #17). It consolidates the nested archive / integrated / timeout-300-preflight work and the separate synthetic-only HTTP 5xx diagnostics. The older draft PRs (#12–#16) are historical staging paths, **not independent upgrades to merge again**. First fetch and inspect the current remote HEAD, which may be newer than this document.

The latest consolidated branch regression was **390 tests passing** ([run](https://github.com/huziibee/2610990_research_project/actions/runs/39423943269)). Its secret-backed diagnostic workflow failed ([run](https://github.com/huziibee/2610990_research_project/actions/runs/39423937361)). CI passing does **not** establish successful live synthetic S0/S1 clarification.

The research protocol remains `protocol/gemma4_seed17_v1.json`, with `allow_held_out_predictions=false` and protected execution requiring separate explicit hash-bound authorization. **Do not launch any protected 100-case predictions, protected judging, or 500-case ablations.** Do not alter or regenerate approved references to satisfy checks.

## Engineering and research status

- **Built**: S0 direct generation; S1 goal-first/grounding; strict structured task schema, dependency and evidence validation; isolated clarification-oracle processes; immutable no-reroll receipts; author-reviewed agent-assisted reference validation for 100 cases (74 execute, 26 clarify) and 26 approved branches; 200-prediction mock main schedule; 500-prediction mock five-ablation schedule; automatic semantic judge with current-code five-fixture live calibration reportedly completed; analysis and technical-freeze tooling.
- **Main unresolved gate**: a successful **current-code** live synthetic S0 and S1 two-answer trajectory, each `CLARIFY -> CLARIFY -> ACTION_READY`, exact approved question matching, no failed stages or unrecorded provider calls. Synthetic mock completion does not count.
- **Private references**: original restored local release was reported as validated (100 references and 26 branches); private plaintext export, author receipt, ledger, encryption key and complete execution archives are intentionally not committed. An integration/final hash-binding check must be performed where these private files are legitimately accessible. Do not claim the private release was freshly revalidated in GitHub CI.
- **Final gates**: rebind successful current-code live S0/S1 smoke, current judge calibration, exact current code/prompt/config snapshots and private reference bindings; run `tools/check_seed17_readiness.py` and the safe validator, then `tools/prepare_seed17_freeze.py` for a **PREPARED_UNSIGNED** freeze. An unsigned freeze is the target; user has NOT authorized the protected experiment.

## New diagnostic evidence — don't hide these failures

`tools/diagnose_seed17_http500.py`, `tests/test_seed17_http500_diagnostic.py`, and `.github/workflows/seed17-http500-diagnostic.yml` are development-only. The diagnostic permits bounded 500/502/503/504 retries with exponential backoff, retains attempt-level results and supports adjustable S1 output token caps. It is **not** the protected runner and **not** qualifying freeze evidence.

Secret-backed live diagnostic [run 39423937361](https://github.com/huziibee/2610990_research_project/actions/runs/39423937361):
- S0: attempt 1 `HTTP 500 INTERNAL` in ~0.44 s, attempted backoff 2 s; attempt 2 ended `INFERENCE_FAILURE` after ~101 s. Probe stopped. No valid S0 success.
- S1: attempt 1 `HTTP 500 INTERNAL` in ~0.26 s, attempted backoff 2 s; attempt 2 ended `INFERENCE_FAILURE` after ~27 s. Probe stopped. No valid S1 success.
- The error body had the same hash in both first failures; category `internal_error`, no `Retry-After` header. Do **not** assume these are rate limits or token exhaustion.
- The diagnostic currently retries a **whole S1 predict()** after HTTP 5xx; this is only an independent invented-input probe. Protected requests have immutable identities and a no-reroll policy, and must never silently repeat after ambiguous sends. Any scientifically justified retry policy change needs protocol amendment, audit, fresh tests and explicit authorization.
- Read the archived workflow artifacts and `calls.jsonl` to identify the `INFERENCE_FAILURE` cause (e.g. finish reason or local response validation); diagnostic summary alone is insufficient.

Other live experiments established that S1 sometimes returns valid responses at 6144–8192 caps but was not reliable across attempts. The active candidate specifies `request_timeout_seconds=300`; raising timeout had not resolved HTTP 500.

## Coding agent next actions (goal: priorities 1–4, never protected execution)

1. **Reproduce and diagnose provider failures** on *invented* records, retaining all raw metadata and failed call receipts; distinguish HTTP 5xx, `finishReason`, malformed output, validation, timeout, quota and transport. Never use held-out protected inputs. Inspect `research/gemini_backend.py`, `research/seed17_worker.py`, `research/systems.py`, current generation JSON schema, prompt probes, and workflow logs. Avoid guessing quota/tokens as explanation.
2. **Obtain an official end-to-end live synthetic smoke** using the existing strict `tools/run_single_seed.py --live-smoke --output runs/development/<fresh-unique>` and the synthetic approved two-reply fixture. The full S0 and S1 trajectories must pass the strict evidence/audit checks. Preserve every failure; no rerolls or manual fabricated evidence. The diagnostic probe cannot substitute for this.
3. **Bind latest code+review artifacts** with the already developed safe validator. Review `docs/SEED17_TECHNICAL_FREEZE_V2.md`, `docs/GEMMA_SEED17_PRELAUNCH_HANDOFF_20261020.md`, `docs/GEMMA_SEED17_ABLATION_RUNNER.md`, and `docs/SEED17_ANALYSIS_PIPELINE.md`. These are sometimes historical snapshots; verify current branch code over notes. Confirm that the live judge calibration is for the exact final rubric, prompt, and code fingerprint.
4. **Run readiness and prepare only the unsigned technical freeze** after live and private-artifact checks are valid. Use `tools/check_seed17_readiness.py --bundle <candidate_bundle>` and `tools/prepare_seed17_freeze.py --bundle <candidate_bundle> --output <new-private-path>`. The legitimate unsigned bundle should leave only the separately required `signed_off_release` authorization gate outstanding. Do not create authorization or start protected inference.

Keep protocol, source/reference bytes, question matching, ablation definitions, and no-reroll receipts unchanged unless there is an explicitly justified, versioned amendment. Model judge scores and real paper results remain **NOT COMPUTED**.

## Scope and reference links

- [Integrated PR #17](https://github.com/huziibee/2610990_research_project/pull/17)
- [Successful final-head offline regression, 390 tests](https://github.com/huziibee/2610990_research_project/actions/runs/39423943269)
- [Failed live 5xx diagnostic](https://github.com/huziibee/2610990_research_project/actions/runs/39423937361)
- [300-second timeout preflight CI](https://github.com/huziibee/2610990_research_project/actions/runs/39420263723)
- [Older integrated live gates](https://github.com/huziibee/2610990_research_project/blob/main/.github/workflows/seed17-integrated-live-gates.yml)

This handoff is a code/evidence map, not a claim of current study readiness.
