> Historical implementation handoff. The selected semantic method is now the explicitly adopted one-human author-review protocol. See [current methodology handoff](GEMMA_SEED17_AUTHOR_REVIEW_HANDOFF_20261019.md) and `protocol/seed17/AUTHOR_REVIEW_METHOD_v1.json`. The independent-review blockers described below record the earlier gate and are not the selected seed-17 methodology. Protected evaluation remains disabled.

# Gemma 4 protected seed-17 implementation — local handoff

**Implementation and synthetic validation only. Protected evaluation remains disabled.**

The working tree, including the uncommitted Gemma changes, was the starting point. Before integration, 20 modified/untracked files and a binary Git diff were preserved under `runs/development/local_before_seed17_20261019T195731Z/`. PR [#12](https://github.com/huziibee/2610990_research_project/pull/12), exact commit `2d68261f6268a1b4d95a00802b7256ccc963855a`, was inspected and its five additive files integrated individually. No merge, reset, checkout of an older project, or protected run occurred.

## Implemented contract

Separate protocol: `protocol/gemma4_seed17_v1.json`; release evidence schema: version 2. Gemma `gemma-4-26b-a4b-it`, `thinkingLevel: minimal`, `includeThoughts: false`, provider JSON schema and strict local validation remain mandatory. S0 uses one 4096-token call per prediction; S1 uses two 2048-token stages. Seed is exactly 17. Automatic transport and malformed-output retries are zero.

`protocol/seed17/main_200.jsonl` is the prespecified shuffled 100-case S0/S1 schedule. Its rows equal the historical 1000-row plan's seed-17 prefix. `protocol/seed17/ablations_500.jsonl` separately prepares all five matched interventions. No ablation execution command was added to the protected runner. Original source records, approved 74/26 routes, dataset/archive hashes, historical schedules, author ledger and author-review exports are preserved.

The historical `research/evaluation_gate.py` was restored to its original Git bytes. Its prior local Gemma adaptation was carried into the **new** `research/seed17_gate.py`, rather than weakening the five-seed gate. Other earlier local Gemma edits remain in the branch. The older `gemini_protocol_v1.json` is retained as the pre-existing local candidate/history; the new runner uses the distinct seed-17 file.

## Runner and process boundary

`tools/run_single_seed.py` defaults to a read-only, separate-process readiness check. A protected invocation requires the signed-off versioned bundle and a fixed execution directory. Each case/system has one initial prediction, shared across its verified hypothetical-answer branches. Every branch then starts from the same original input and initial task.

`research/seed17_oracle_service.py` is the evaluator process. It rechecks readiness and reads the verified export, ledger-bound references and reviewed exact-normalized question variants. Only branch metadata and the next matching simulated reply cross its RPC interface. Its sequence/case/branch/turn queries are checked. There is no arbitrary or model-generated reply fallback. Execute cases that unexpectedly request clarification receive no hypothetical answer.

`research/seed17_worker.py` is the model process. It imports no reference reader, annotation ledger, answer matcher or semantic scorer. It accepts only the strict visible input contract. Scene, instruction and capabilities stay frozen; only correctly scoped question/answer pairs may be appended to dialogue. It rechecks code/protocol fingerprints before predictions. Every task is revalidated after each approved reply. Loops stop at action readiness, unavailable answer, error or five replies, and preserve all successful/failed turns and termination reasons.

## Crash recovery and resources

The PR's `AttemptJournal` now validates schedule binding, claims and completion hashes. The new per-call `RequestJournal` writes and fsyncs a claim **before** each provider request, then stores an immutable response/error receipt. Keys include the scheduled sequence, branch, turn and stage. Initial calls are shared, rather than repeated per branch.

- Saved responses may be replayed **locally** to reconstruct an interrupted pipeline. An S1 goal saved before a crash is reused without resending it.
- A claim with no valid outcome blocks **the entire run** as `INTERRUPTED_UNRESOLVED_NO_REROLL`. Do not delete claims or use a fresh directory to reroll. Unknown/partial/corrupt journal files require explicit resolution.
- Known errors remain failed attempts. HTTP 429/500/503, network timeouts/failures and unexpected thinking output pause execution; they do not trigger a retry. An explicit later resume can proceed to other unstarted scheduled requests while retaining the failed result.
- Kernel locks prevent overlapping coordinators and overlapping use of the shared quota ledger. They release when a process exits; lock files and immutable records are retained.
- Local pacing reserves at most **15 RPM, 15,000 TPM, 14,000 RPD**, below the user-reported 30/16,000/14,400 limits. Windows are 61 seconds and a rolling 24 hours, including failed and ambiguous reservations. Numeric or HTTP-date Retry-After values are captured. Oversized requests/daily exhaustion pause before another send. No prompt truncation or cap reduction is applied.

The input-token reservation is UTF-8 request bytes plus the complete output cap plus 1024 tokens. It is a conservative reservation estimate, not measured tokenizer usage. The ledger cannot observe other clients using the same Google project. [Google documents](https://ai.google.dev/gemini-api/docs/rate-limits) that active limits depend on the project/tier; verify availability in AI Studio before a live smoke or eventual release. The earlier manual/API smoke calls predate this new ledger.

## Readiness remains blocked

`protocol/seed17/FREEZE.json` is **UNSIGNED**. The protocol is **CANDIDATE**, `allow_held_out_predictions` is **false**, and no launch-authorization evidence has been supplied.

The new gate requires:

1. Exact seed-17 contract, both schedules and the original historical-schedule hash.
2. All 100 independently verified, finally approved semantic references with source/ledger/export bindings. The existing private release remains `AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED`; it is not relabeled. No alternative review protocol has been authorized. An alternative requires an explicit, separately reviewed amendment; it is not enabled by a bundle flag.
3. Reviewed clarification rules, all branch/answer coverage and verified dialogue/dependency subgroup labels.
4. Successful live synthetic S0/S1 initial tests and current-code live S0/S1 trajectories completing at least two approved replies, with schema, stage/context, model-version, response-ID and usage evidence. Mock output is rejected as live evidence.
5. Passing scoring/leakage/interruption fixtures, independently reviewed test evidence, complete source/prompt/runtime fingerprints and a signed-off freeze with explicit launch authorization.

Documentary signer/reviewer fields and file hashes are not represented as externally authenticated identities or authenticated model-review logs. No people, signatures, approvals or review logs were fabricated.

Earlier S1 initial live evidence exists at `runs/development/20261019T193654Z_9ba00626`. Following explicit user authorization, current-code live synthetic calls were run; see the live follow-up below. The Qwen cluster attempt is separate and cannot satisfy Gemma readiness.

## Safe verification and evidence

The repeatable validation harness snapshots code **before** testing, verifies frozen data, runs the full suite, synthetic S0/S1 and clarification tests, a complete 200-prediction mock run with trajectories, the archive audit and both schedule preparations. It checks that source/config hashes did not change while validating. Its bundle is explicitly unapproved and preserves absent reviewer fields as waiting states.

```powershell
py tools/validate_seed17_safe.py --output runs/readiness/NEW_SAFE_CHECK_NAME
py tools/check_seed17_readiness.py --bundle runs/readiness/NEW_SAFE_CHECK_NAME/candidate_bundle.json
```

The second command is expected to exit 2 while scientific/release gates are incomplete. Safe-check evidence is not evaluation permission. Use a new name each time; no evidence or output directory is overwritten.

Final validation output for this implementation is recorded separately under `runs/readiness/gemma_seed17_safe_20261019_v2/`: **288 tests passed**, frozen-data verification passed, synthetic S0/S1 and clarification checks passed, and the complete mock produced **200 initial predictions and 528 unique mock calls** across all fixture trajectories. The 200/500 schedules were prepared and audited without launching ablations. Earlier validation directories are retained. The safe validation summary, test log, implementation snapshot and detailed `readiness.json` give the actual counts and exact current gate failures. Development artifacts and private references remain ignored by Git.

The version-2 candidate evidence has **17 passing checks and 14 failing checks**. Passing checks include dataset integrity, exact contract/schedules, snapshot binding, runtime/prompt fingerprints and the historical S1 initial live smoke. Failures cover the unreleased protocol, independently verified reference export/ledger binding, reviewed coverage/matching/subgroups, live S0, independently reviewed scoring/leakage fixtures, signed launch release and current-code live multi-turn evidence. `ready=false`, `protected_execution_authorized=false`, `benchmark_executed=false`. No protected execution directory was created.

Optional **synthetic-only** live command, once project quota is available:

```powershell
py tools/run_single_seed.py --live-smoke --output runs/development/NEW_GEMMA_LIVE_SMOKE_NAME
```

This uses only newly authored synthetic inputs. It uses the same request journal, pacing, provider schema and validation. It pauses on a provider error, with no automatic reroll. Successful smoke exports are written in a separate sibling evidence directory so the sealed run stays immutable. This command was not run in this development pass.

## Eventual protected commands — only after release and authorization

First complete the actual reference/rules/subgroup review, live smokes and independent scoring-fixture review. Freeze the new protocol and signoff, archive exact fingerprints, and provide explicit authorization evidence bound to the freeze digest in a version-2 release bundle. Do not edit the historical gate or mark the author-only export independently verified to get a green status.

```powershell
py tools/check_seed17_readiness.py --bundle runs/readiness/APPROVED_RELEASE/bundle.json
py tools/run_single_seed.py --execute --bundle runs/readiness/APPROVED_RELEASE/bundle.json
```

The fixed directory is `runs/evaluation/seed17/gemma4-seed17-v1`. If the run pauses after a known failure and explicit continuation is authorized:

```powershell
py tools/run_single_seed.py --execute --resume --bundle runs/readiness/APPROVED_RELEASE/bundle.json
```

An unresolved send will still refuse to continue. Partial files, changed bindings or an attempted new output directory do not bypass this restriction. Do not launch the old `run_experiment.py --execute` five-seed sweep for this study.

## Output and scoring

Archives contain the immutable initial journal, 200 initial records, every case/system/branch trajectory, per-call records, request claims/receipts, pause checkpoints and a final hash seal. The auditor checks exact case/system/seed pairing, all branches, contiguous turns, stop rules, immutable input/context, stage/schema/cap/thinking settings, provider-output equality, call-to-claim hashes and missing/orphaned records. Errors remain in the denominator.

```powershell
py tools/score_single_seed.py runs/evaluation/seed17/gemma4-seed17-v1
py tools/score_single_seed.py runs/evaluation/seed17/gemma4-seed17-v1 --judgments runs/scoring/VERIFIED_JUDGMENTS.json --pricing protocol/seed17/pricing_20261019.json --output runs/scoring/NEW_SCORE_REPORT.json
```

The judgment file contains separate `S0` and `S1` lists. Each successful turn requires independent field-level judgments tied to the exact prediction hash and reference revision/hash; errors have no invented judgment. Complete-task correctness requires action readiness, all required semantic fields correct and no unsupported detail. Routing or a valid question alone earns no completed-task credit. Branches are averaged within a case, and the S1–S0 interval resamples 100 paired cases 10,000 times with bootstrap seed 20261019. **Between-seed variability is NOT_ESTIMABLE.**

Efficiency reports deduplicate shared initial calls, retain raw input/output/available reasoning tokens and model versions, and compute P50/P95 of branch-mean per-case request latency including pacing. This latency scope excludes coordinator/oracle IPC, local validation and crash downtime; it is stated in the report. Missing token counts remain unavailable, with separate coverage and reported-only totals. [Published Gemma pricing](https://ai.google.dev/gemini-api/docs/pricing#gemma-4) was checked on 2026-10-19; the published free-tier input/output rate is zero, but the account tier is **not verified**. The dated pricing record therefore produces no monetary estimate until the tier is verified. Estimates are not invoices. No real main-result latency, cost, semantic scores or confidence intervals have been populated.

## Source changes

- PR integration: `research/single_seed_plan.py`, `tools/plan_single_seed.py`, `tests/test_single_seed_plan.py`, the candidate amendment and original PR staging note.
- Runtime and recovery: `research/seed17_engine.py`, `seed17_worker.py`, `seed17_journal.py`, `seed17_processes.py`, `seed17_oracle_service.py`, `tools/run_single_seed.py`; `research/gemini_backend.py` retains local Gemma defaults and adds safe Retry-After metadata.
- Release and scoring: `research/seed17_config.py`, `seed17_gate.py`, `seed17_audit.py`, the separate protocol/schedules/unsigned freeze/pricing record, `tools/check_seed17_readiness.py`, `tools/score_single_seed.py`.
- Synthetic validation: `research/seed17_synthetic.py`, `tests/test_seed17_execution.py`, `tests/test_seed17_gate.py`, `tools/validate_seed17_safe.py`.
- Preserved earlier local work: Gemma helper/backend/development runner, relevant budget tests, protocol amendment/status notes, Qwen smoke source and its failure note. No cluster logs, protected logs, private reference exports, `.env` or keys are committed.

Scientific results remain **NOT_COMPUTED**. Final evaluation and ablations were not launched.

## Authorized live follow-up

Six live provider requests completed using `gemma-4-26b-a4b-it`, minimal thinking and `includeThoughts: false`, without HTTP errors or automatic retries. The first smoke (`runs/development/gemma_seed17_live_20261019_01`) produced valid S0 and S1 initial tasks from three calls. Both asked questions outside the frozen synthetic question whitelist; the oracle released no answer and stopped with `ANSWER_UNAVAILABLE`. Initial smoke success does not establish semantic correctness or multi-turn success.

A separate ordered-question synthetic diagnostic (`runs/development/gemma_seed17_live_20261019_ordered_diagnostic_01`) declared its changed visible scenario and accepted question variants before sending its three requests. All three provider responses passed provider-output parsing, but strict task validation rejected S0 (`before requires whole action references`) and S1 (`Argument type/value mismatch`). Those errors remain recorded; neither failed prediction was retried. This interface diagnostic is distinguished from the uncoached smoke and provides no independent review evidence. No protected input was used in either run.

The updated candidate bundle and gate report are under `runs/readiness/gemma_seed17_live_20261019/`. Readiness is **20 passed / 11 blocked**, `ready=false`, `protected_execution_authorized=false`, `benchmark_executed=false`. Both initial live smoke gates now pass. Successful live two-answer S0/S1 trajectories, scientific reference/matching/subgroup review, reviewed scoring fixtures, final freeze and authorization remain outstanding. Raw requests, receipts, calls and sealed archives are retained locally and ignored by Git. Token totals across all six requests: 2,068 input, 2,214 output, 4,282 total; reasoning-token counts were unavailable. Full per-request latency and usage are in `live_summary.json`. These are synthetic development measurements, not main-study results.
