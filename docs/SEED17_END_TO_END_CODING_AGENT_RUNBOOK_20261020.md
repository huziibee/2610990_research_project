# Seed-17 end-to-end coding-agent execution runbook (20 October 2026)

> **Mission**: take the current research implementation to fully validated, executed and analyzed scientific results: successful live S0/S1 clarification, verified private review release, current-code judge calibration, unsigned technical freeze, separately authorized **protected main experiment and five protected ablations**, isolated semantic judging, complete paired statistical analysis and reproducible result archives. **Do not draft, edit, compile, render or grade the research manuscript/paper.**
>
> **Operating mode**: proactive debugging, parallel subagents for independent engineering streams, short feedback cycles, comprehensive failure logs and continuous forward progress. Never equate mocked correctness, CI, diagnostic calls or a failed run with completed scientific results. Never bypass a security/research gate just to get a green check.

## 0. Entry point and authoritative state

Repository: `huziibee/2610990_research_project`; starting branch **`main`**. Integration PR [#17](https://github.com/huziibee/2610990_research_project/pull/17) merged the nested archive/integrated/300-second-timeout research branches and the separate synthetic HTTP 5xx diagnostic. Latest documented handoff commit: `bb3b70c78fca77c97bc496a5a975db8902333b57` (may be older than remote main; fetch first). [Post-merge CI on merge commit passed](https://github.com/huziibee/2610990_research_project/actions/runs/39424738891). [Next handoff-commit CI passed](https://github.com/huziibee/2610990_research_project/actions/runs/39425002016). Last consolidated regression was **390 passing tests**; that is an offline engineering result, not protected research success.

**Do not merge the older draft PRs #12–#16 blindly.** Their useful code is already consolidated into main. Check ancestry/diffs if unsure. Keep experimental raw artifacts in their designated ignored directories; do not commit plaintext private references, encryption keys, API keys, provider request payloads containing protected cases, author identifiers not already legitimately public, or protected model output.

Start with `git fetch origin && git switch main && git pull --ff-only origin main`. Capture `git rev-parse HEAD`, `git status --short`, current active branches/PRs and CI before starting. Check `requirements.txt`, Python/runtime compatibility and the actual CLI `--help` flags. Prefer a clean git worktree/branch per subagent. Read source code over historical handoff prose if there is any discrepancy.

Read these files first, **in this order**:

1. This runbook; `docs/SEED17_CODING_AGENT_HANDOFF_20261020.md` (previous engineering history).
2. `protocol/gemma4_seed17_v1.json`; `protocol/seed17/ablation_contract_v1.json`; `protocol/seed17/analysis_contract_v1.json`; `protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json`.
3. `docs/GEMMA_SEED17_AUTHOR_REVIEW_HANDOFF_20261019.md`; `docs/GEMMA_SEED17_PRELAUNCH_HANDOFF_20261020.md`; `docs/SEED17_TECHNICAL_FREEZE_V2.md`.
4. `docs/GEMMA_SEED17_ABLATION_RUNNER.md`; `docs/SEED17_ANALYSIS_PIPELINE.md`; `docs/SEED17_ANALYSIS_PIPELINE.md`.
5. `research/systems.py`, `research/gemini_backend.py`, `research/generation_schema.py`, `research/task_schema.py`; `research/seed17_engine.py`, `research/seed17_worker.py`, `research/seed17_journal.py`, `research/seed17_gate.py`, `research/seed17_freeze.py`, `research/seed17_author_review.py`, `research/seed17_judge.py`, `research/seed17_ablation*.py`, `research/seed17_analysis.py`.

The historical five-seed 1,000-main / 2,500-ablation plan and older Qwen comparators are **not** the active experiment. This is the registered single-seed Gemma experiment. An optional S2 system exists in code but is **not** part of the registered seed-17 main comparison or five interventions. Do not silently add it.

## 1. Architecture and scientific question

**Input per source case**: human utterance/instruction, scene, prior dialogue and explicitly available capabilities.

- **S0 (direct)**: one Gemma model generation of a schema-validated structured task, `S0.direct`.
- **S1 (goal-first)**: Gemma `S1.goal` creates an explicit `intended_goal`; Gemma `S1.ground` uses that proposed goal plus the original visible context to generate a typed, evidence-linked structured task. Two calls per initial prediction.
- **Task validator**: enforces JSON/task schema, readiness, exact capability/argument identifiers, argument types, evidence-pointer validity, action/dependency structure and absence of unsupported fabricated details to the extent deterministically checkable. Validation is not semantic correctness.
- **Clarification controller**: when a task is `CLARIFY`, asks one critical missing-field question, accepts a **simulated author-approved answer** from an **isolated reference oracle**, appends it to dialogue and re-predicts with the same system. Stop at `ACTION_READY`, `ANSWER_UNAVAILABLE`, `ERROR` or `TURN_LIMIT`; maximum five answers. Nonmatching questions receive no fabricated answer.
- **Separation**: protected references/approved answers belong in oracle and isolated evaluator only. The generation process sees model-visible inputs and approved answers only after permitted questions; it never imports the semantic gold table or receives evaluator feedback.
- **Evaluation**: first deterministic checks, then isolated `gemini-3.8-live` semantic judge on author-reviewed, model-assisted references; freeze the judge rubric/model/config, preserve abstentions and evidence. Compare S1 vs S0 and each ablation vs **matched main S1**.
- **Outcome**: action-ready *representation*, not physical robot execution. Primary outcome is terminal complete-task correctness; also readiness/confusion, individual semantic fields, clarification-turn success, unsupported detail and efficiency.

The active benchmark contains **100 source cases: 74 initial execute references and 26 initial clarify references**, with **26 author-approved clarification branches**. Seed **17**; **200 main initial predictions** (S0/S1 × 100); **500 ablation initial predictions** (five interventions × 100). Clarification continuations add further calls. Every source case stays in the denominator, even on failure.

## 2. What is actually complete and what is not

| Area | Present status | What is required to call it complete |
| --- | --- | --- |
| Structured S0/S1, synthetic oracle, controllers and validations | Implemented, offline CI passes | Full successful *current-code* live two-answer S0 and S1 smoke |
| Private author-approved reference release | Original local validation reported 100/100 and 26/26 | Revalidate unchanged exact local export/receipt/ledger/matching/eligibility against active release hashes |
| Semantic judge | The user reports an independently verified five-fixture live calibration | Confirm artifact exists and is valid against current rubric/config and relevant code fingerprints; rerun if stale |
| Mock main | All 200 initial predictions and continuations were simulated | Re-audit under final current code after integration |
| Mock ablations | All 500 initial predictions and continuations were simulated | Re-audit exact 500 grid under final current code |
| Provider live smoke | Unsuccessful end-to-end | S0 and S1 `CLARIFY -> CLARIFY -> ACTION_READY` with real provider calls and strict synthetic oracle |
| Technical release | Freeze/checker implemented, unsigned freeze not completed | Final hash-bound bundle passes all technical gates, only authorization outstanding |
| Protected main and ablations | **Not executed** | Separately authorized, durable sealed live runs and complete audit |
| Real judging/statistics | **NOT COMPUTED** | Isolated judge receipts plus real results/CSVs/figures, with unknowns honestly represented |
| Paper | Out of scope | **Do not work on it** |

Use status labels `IMPLEMENTED`, `TESTED_SYNTHETIC`, `TESTED_LIVE_SYNTHETIC`, `TECHNICALLY_FROZEN`, `EXPLICITLY_AUTHORIZED`, `PROTECTED_EXECUTED_AND_SEALED`, `JUDGED`, `ANALYZED`; never conflate them.

## 3. Parallel subagent structure

**Appoint one coordinator/orchestrator** who owns the current branch, merges, release decisions and immutable experiment execution. Delegate *independent* subagents as below; run read-only audits and local mock tests in parallel while only ONE owner launches live provider calls to avoid a shared RPM/TPM/quota ledger race.

- **Agent A — Provider and live clarification**: owns invented-fixture reproduction, S0/S1 prompt/schema/transport diagnosis, no-secret logging, valid live three-state trajectories and current-code evidence audit. Changes only its feature branch; does not touch private reference files.
- **Agent B — Private release and gate audit**: read-only verifies 100 reference rows, author receipt, 26 branches, ledger/source pins, matching/eligibility, encrypted archive and readiness-gate expectations. Does not regenerate/normalize original private files. Reports absent private inputs as blockers with exact paths.
- **Agent C — Ablation correctness and failure injection**: inspects all five registered interventions, mask/evidence logic, branch-answer visibility, exact 500-case pairing, request/journal resilience and ablation authorization. Runs full mock and adversarial negative tests, no protected predictions.
- **Agent D — Judge, scoring and statistics**: checks final five-fixture live judge calibration provenance (no need to rerun if exact valid), deterministic/semantic scoring, abstention semantics, aggregate case/branch denominators and real analysis CLI. Runs invented analysis fixtures; never changes frozen judge after protected runs.
- **Agent E — Integration/release engineering**: CI, dependency/runtime fingerprints, safe-validation bundle, `PREPARED_UNSIGNED` technical freeze, hashes and release manifests. Starts freeze preparation only after A/B/C/D branches have been merged and tests pass.
- **Agent F — Independent adversarial audit** (optional): actively test negative scenarios: missing private records, changed bytes, failed HTTP calls, repeated/unsupported questions, truncated JSON, incompatible stage cap, leaked references, duplicate requests, interrupted writes, stale judgments, wrong schedule/seed or denominator. Its job is to catch false positives, not make the gate pass.

**Worktree rule**: no subagent edits the same working tree or shared `runs/` directory; every synthetic run uses a fresh unique directory. Agents A and D may both use the provider; serialize their real calls and record quota sessions. Coordinator commits/merges each validated change and reruns tests. A change to any frozen Python/protocol/prompt/runtime field can invalidate current-code live evidence and technical hashes: do live qualification and final freeze **after** all engineering modifications are integrated. Do not run protected main and protected ablations concurrently without demonstrated isolated journaling/quota safety; sequential protected launches are preferred.

Each agent's delivery: actual changed files or a read-only audit, test commands and exit codes, exact evidence paths and SHA-256, failure analysis, unresolved risks. Coordinator must not accept “works” without inspectable receipts.

## 4. Immediate known failure: upstream HTTP 500 plus later inference failure

The configured API key **is present in GitHub Actions secrets**, established by the synthetic workflow's successful `Confirm configured secret` step. It must never appear in logs, commits, messages or public artifacts.

Evidence: [secret-backed synthetic HTTP 5xx run 39423937361](https://github.com/huziibee/2610990_research_project/actions/runs/39423937361). S0 first attempt: `HTTP 500 INTERNAL`, ~0.44 seconds, no `Retry-After`; after 2s backoff, second attempt `INFERENCE_FAILURE` after ~101s. S1 first attempt: `HTTP 500 INTERNAL`, ~0.26s; after backoff, second attempt `INFERENCE_FAILURE` after ~27s. Both first error responses had the same small-body hash. Neither case passed. These are NOT proven rate-limit or token-cap failures. Inspect archived `calls.jsonl`/provider metadata to distinguish `finishReason`, token usage, invalid JSON/schema, model-version behavior, task validation and pure transport error. Preserve all failures.

The diagnostic script `tools/diagnose_seed17_http500.py` offers bounded retries of **500/502/503/504 only**, exponential backoff, `Retry-After` handling and independently selectable S1 token caps of 2048/4096/6144/7168/8192, on invented fixtures only. The associated workflow is `.github/workflows/seed17-http500-diagnostic.yml`. Do not claim these probes qualify as official two-answer smoke or as freeze evidence. The real worker in `research/seed17_worker.py` uses a **300-second** timeout; timeouts and HTTP 500 are distinct.

Earlier S1 grounding sometimes returned valid JSON at caps 6144–8192 with ~137 generated tokens; higher limits alone do not solve upstream 500s. Verify the *actual* stage caps and contract: main protocol currently registers S0 `4096`, S1 `2048`; ablation contract registers `2048` per stage. Any final parameter change must be principled, registered consistently, **tested on synthetic fixtures**, and frozen before protected runs. Do not tune against protected case scores or silently change ablation conditions.

**Hard no-reroll rule**: the diagnostic can make fresh synthetic attempts; the protected runner cannot automatically retry ambiguous/failed sends. A request ID claimed before a network call has durable records; resuming replays known receipts and blocks unknown sends. Never delete a failed log or “start again” in a second protected output directory. Never lower schema or evidence standards merely to pass smoke. If proposing a protected retry design, it requires an explicit protocol amendment, fixed retry budget, policy/audit integration, fresh evidence, and separate author approval before release; default is **no protected retries**.

### Provider-debug work plan

1. Inspect the precise failure body classification and `finishReason`/token accounting from existing diagnostic artifacts, with secrets and protected payloads redacted.
2. Verify model endpoint availability, request JSON schema compatibility, `thinkingLevel:minimal`, `includeThoughts:false`, `responseMimeType:application/json`, system-prompt constraints, provider revision and provider diagnostics **on invented fixture only**. Separate first-stage and grounding-stage tests.
3. Compare minimal and full schemas and a deliberately simple invented request; check whether an upstream internal error depends on the model/API, schema, or request length. Do not generalize from one success.
4. Implement minimal fixes with deterministic tests for success, HTTP 5xx, nonretryable 4xx, max tokens, invalid JSON, validation failure, repeated questions, and legitimate two-answer updates. Run CI and inspect receipts.
5. Produce the **official** live synthetic smoke (fresh dir), e.g. `python tools/run_single_seed.py --live-smoke --output runs/development/<unique-id>`, then audit exported `<unique-id>_evidence`. Require both S0 and S1 turns `0,1,2`: `CLARIFY, CLARIFY, ACTION_READY`, correct approved questions and supplied answers, all provider call receipts `OK`, no missing request, no mismatch in full implementation fingerprints.
6. If provider remains unreliable, document minimal reproduction and provider error IDs/hashes; investigate compatibility/support and alternative *registered* parameter designs without claiming success. A genuine external outage is a blocker, not an excuse to fabricate qualification.

## 5. Five registered ablations — do not omit any

Contract: `protocol/seed17/ablation_contract_v1.json`. Generated grid: `protocol/seed17/ablations_500.jsonl`; **100 source cases per intervention, seed 17, paired with main S1**.

| Intervention | Actual implementation meaning | Failure-mode audit |
| --- | --- | --- |
| `goal_first` | Replace explicit `intended_goal` intermediate with a `context_summary`; second stage still infers goal implicitly | Do not call it “no goal inference”; compare actual prompts/stage metadata |
| `structured_grounding` | Remove explicit grounding instructions in S1 second prompt; preserve JSON schema/task validation | Do not call it removal of all structure; validate retained checks |
| `scene` | Mask scene in **every** model stage and clarification turn; reject scene evidence citations | Confirm no original scene leaks through prompt or stage context |
| `dependency_checking` | Disable only deterministic dependency-consistency checks; keep typed args and evidence validation | Incorrect dependencies still count against scored correctness |
| `dialogue` | Mask original dialogue **and all approved simulated replies** on every turn; oracle can issue answers but generator never sees them | Repeated/unsupported question -> `ANSWER_UNAVAILABLE`, retained in denominator |

Before execution, confirm exactly 500 matched scheduled initial rows, 100 per condition, fixed IDs/order/seed, typed task validation and unchanged question matching, reference isolation and output caps. Run `python tools/run_seed17_ablations.py` (read-only plan), `python tools/run_seed17_ablations.py --mock --output runs/mock_seed17_ablations/<unique-id>`, `python tools/score_single_seed.py runs/mock_seed17_ablations/<unique-id> --ablations --synthetic`, and dedicated ablation tests. Verify synthetic receipt/resume/tamper audit in `research/seed17_ablation_audit.py`.

Protected ablations have a **separate execution scope and authorization**; main launch permission NEVER grants ablation permission. Bound execution directory is `runs/evaluation/seed17/gemma4-seed17-ablations-v1`. Initial calls are at most 1,000; clarification continuations increase requests; actual upper bound is branch-dependent. Enforce shared quota ledger pacing and journal integrity; no automatic protected retries.

## 6. Work through these gates in order (do not stop at step 4)

### Gate A — Stable implementation and tests (parallel engineering)

- Fetch main, inspect code/tests/schedules/runtime and existing GitHub Actions. Make a clean baseline audit, including whether any private artifacts are unavailable in the coding agent's environment.
- Subagents develop, test, merge only justified fixes. Run `python Data/verify_package.py`, `python -m unittest discover -s tests -v`, mock 200 main and 500 ablation checks, adversarial integrity tests, and `python tools/analyze_single_seed.py --synthetic-fixture --output runs/readiness/<fresh-synthetic-analysis>`.
- Do not rerun stale evidence from before final code changes as final qualification.

**Accept**: clean reproducible CI, exact mock schedules and audited seals; no changed source gold; no hidden skip/weakening; unique evidence directory per run.

### Gate B — Live S0 and S1 clarification

- Run the strict real-provider official live synthetic smoke on an **invented** two-answer case, with reference oracle in its separate process.
- Confirm S0 and S1 each produce full `CLARIFY -> CLARIFY -> ACTION_READY` trajectory (turns 0,1,2), valid typed grounded tasks, approved question sequence, proper evidence for simulated replies, all calls finished normally and receipts/provenance sealed.
- Preserve unsuccessful attempts, provider errors, actual model versions, token usage and stages.
- Audit using the existing strict smoke evaluator/CI checks rather than visual plausibility.

**Accept**: qualifying S0/S1 `live_prediction_*`, `live_calls_*` and `live_multi_turn` evidence bound to exact final code.

### Gate C — Private author-review release (can run while B is debugging)

- Locate legitimately available private `runs/human_review_20261019/author_review_export/` materials, human receipt, raw references, encrypted archive, source pins and ledger; never pretend they are in public GitHub.
- Validate exactly **100 author-approved reference rows (74 execute, 26 clarify), 26 approved answer branches**, adoption history, task/evidence schema, frozen source joins, strict question normalization/matching, branch-answer hashes and eligibility masks. Do **not** require or claim a second human reviewer.
- Historical documented hashes: author receipt `5cdda0cbc69724a0c04a7a12988b442d8b1751ee3b5b00747142bbaf5a3b29c8`; plaintext export `8bff3db92f2539b284d0fee359dc245979c25553d211b5931273591a0daed138`; encrypted archive `4290647c43bb69f0caf36c32601f9c6b2693eb399d8f42cf33fcf6ac151d48d0`. Treat these as historical expectations to verify against current freeze, not as substitutes for opening and checking private files.
- `python tools/prepare_seed17_author_release.py --output runs/readiness/<fresh-release-projection>` after inspecting its CLI and authorized local paths. Keep exports/matching projections ignored/unpublished.

**Accept**: hashes and source joins validated, matching/eligibility releases audit clean. If private bytes/key are missing, report exact required artifacts and do not fabricate them.

### Gate D — Automated semantic judge (can audit in parallel with B/C)

- Evaluate user-reported prior five-fixture live calibration against exact *final-code* `judge_v1.json`, `judge_rubric_v1.json` and judge-related Python hashes. If stale or unverifiable: run `python tools/calibrate_seed17_judge.py --live-synthetic --output runs/judgments/<fresh-live-calibration>`.
- Cases must cover exact correctness, paraphrase, incorrect semantics, contradictory reference/evidence **abstention**, and other fixed fixtures. Validate tool-call response structure and all mandatory evidence pointers.
- Missing/malformed/abstaining decisions remain **UNRESOLVED**, not zero, not success; no judge feedback to generator.
- After a protected run, do not change judge rubric/prompt based on its observed results.

**Accept**: valid all-five live fixture calibration for the exact frozen judge version, with sealed receipts.

### Gate E — Safe prefreeze and unsigned technical freeze

Do this **after** all code branches are merged and B/C/D evidence matches that exact code:

```bash
python tools/validate_seed17_safe.py \
  --output runs/readiness/<fresh-candidate> \
  --live-smoke-evidence runs/development/<successful-smoke>_evidence \
  --judge-calibration runs/judgments/<successful-current-calibration>/calibration.json

python tools/check_seed17_readiness.py \
  --bundle runs/readiness/<fresh-candidate>/candidate_bundle.json

python tools/prepare_seed17_freeze.py \
  --bundle runs/readiness/<fresh-candidate>/candidate_bundle.json \
  --output runs/readiness/<fresh-unsigned-freeze>
```

Validate local files, Python/platform/runtime/dependency versions, all `research/`, `tools/`, `tests/` Python inventory fingerprints, prompts, protocol amendment JSONs, judge/rubric, 200/500 mock seals, original source hashes, author-reviewed private receipts, live smoke and judge calibration. Every artifact must exist and match its SHA-256; schema version 5; no silently changed references. The unsigned freeze record must have `status=PREPARED_UNSIGNED`, `authorization_granted=false` and no pretend signer. **A successful pre-freeze** leaves exactly the `signed_off_release` gate pending; code calls this `ready_for_authorization`, not permission to execute.

**Accept**: immutable `technical_freeze.json`, `candidate_bundle.json`, `readiness.json`, with current-code checks and SHA bindings, no protected predictions yet.

### Gate F — Obtain **explicit main launch authorization** for the exact frozen release

This project specifically requires a *separate, release-bound approval after the technical freeze*. A general instruction to finish the engineering or experiments is not a substitute for a verbatim signoff tied to hashes. Ask the user **once** at the actual freeze boundary, presenting exact study/scope, expected main 200 initial predictions plus permitted clarification branches, model/cost/quota implications, technical-freeze SHA-256 and referenced base/root-freeze hashes. Do not ask for this before the final freeze exists; do not invent the signer's identity, time or words.

The source validator `research/seed17_freeze.py::validate_launch_authorization` requires an actual authorization evidence document with:

- `status: EXPLICIT_USER_LAUNCH_AUTHORIZATION`; `authorization_granted: true`.
- `study_id: gemma4-seed17-v1`; `scope: seed17_main_with_approved_clarification_only`.
- `authorized_by`, timezone-aware `authorized_utc`, exact `verbatim_authorization`.
- `technical_freeze_sha256`, `base_artifacts_sha256`, `freeze_sha256` matching the legitimate immutable release.

Bind that document as `authorization_evidence` in a **separate authorized copy** of the prepared bundle, without mutating the source protocol or unsigned technical freeze. If the repository lacks a tested helper for constructing/verifying this authorized copy, implement and unit-test a narrowly scoped helper instead of hand-editing unchecked JSON. Then verify `check_seed17_readiness` actually reports `ready=true` and exact file hashes.

**Accept**: independently checked, explicitly authorized hash-bound main bundle; no authorization inferred or fabricated.

### Gate G — Execute and seal the **protected main S0/S1 experiment**

Only after Gate F succeeds, and after confirming no code/config/runtime drift:

```bash
python tools/run_single_seed.py --execute --bundle <authorized-main-bundle.json>
# --resume is permitted ONLY as explicitly verified immutable receipt replay:
python tools/run_single_seed.py --execute --resume --bundle <same-authorized-main-bundle.json>
```

Exact output directory: `runs/evaluation/seed17/gemma4-seed17-v1`. Verify the fixed schedule has 200 initial predictions (100 S0, 100 S1), plus all registered clarification branch continuations through terminal stop conditions. Audit source-case denominators, 74/26 strata, question matching/answers, no reference leaks, fail-closed on unknown sends, immutable receipts, source and code fingerprints, provider usage, stop reasons, and seal membership. No alternative seed, cherry-picked rerun or output-directory rollover. A provider error counts as a real failed attempt and can require safe pause/manual reconciliation, not silent deletion.

**Accept**: exact authorized complete sealed main run with defensible failures and all initial predictions/branches accounted for. If a failure prevents completion, report its attempt and preserve data rather than labeling a partial run complete.

### Gate H — Obtain **separate explicit ablation authorization**

Main permission **does not include the five ablations**. Present the exact freeze, the registered five interventions, 500-row schedule, planned provider budget and fixed directory. Obtain the user's actual verbatim separate ablation authorization bound to the frozen release **after** it exists.

`research/seed17_ablation.py::validate_authorization` checks:
- `status: EXPLICIT_USER_ABLATION_AUTHORIZATION`, `authorization_granted: true`, `study_id: gemma4-seed17-v1`.
- Scope exactly the constant in the **current** `research/seed17_ablation.py` (registered ablation scope), not the main scope.
- `technical_freeze_sha256`, `base_artifacts_sha256`, `ablation_contract_sha256`, hash of the exact 500-row schedule, `execution_directory`.
- Real `authorized_by`, timezone-aware `authorized_utc` and verbatim text.

Do not manufacture, retroactively date or reuse the main authorization as ablation consent. Store the raw authorization privately and verify it with the source validator.

**Accept**: separate valid ablation authorization, matching current contract/schedule/freeze exactly.

### Gate I — Execute and seal **all five protected ablations**

Only after Gates G/H, one controlled protected coordinator at a time:

```bash
python tools/run_seed17_ablations.py --execute \
  --bundle <same-authorized-main-bundle.json> \
  --authorization <separate-explicit-ablation-authorization.json>
# Only when safe durable resume is supported:
python tools/run_seed17_ablations.py --execute --resume \
  --bundle <same-authorized-main-bundle.json> \
  --authorization <same-ablation-authorization.json>
```

Expected fixed directory: `runs/evaluation/seed17/gemma4-seed17-ablations-v1`. Audit `research/seed17_ablation_audit.py`: 500 initial predictions, 100 per intervention, same source cases/seed as main S1, exact ablation-specific transformed model-visible fields at **every turn**, no fabricated answers, no errors or abstentions excluded from denominators, sealed receipts and safe resume. Keep the synthetic smoke and live study completely separate.

**Accept**: one audited sealed full 500-initial-prediction ablation archive with all clarification trajectories and condition manifests, even if some cases genuinely fail.

### Gate J — Judge both archives and generate real statistical results (NO PAPER)

Use the isolated judge and author-reviewed release **only on fully sealed, authorized runs**. Exact command flags are in `tools/score_single_seed.py --help` and `docs/SEED17_ANALYSIS_PIPELINE.md`; inspect whether the ablation scorer expects the same main authorized bundle plus the run-bound independent ablation authorization. Do not invent an ablation bundle shape. Typical commands:

```bash
python tools/score_single_seed.py runs/evaluation/seed17/gemma4-seed17-v1 \
  --automated --run-judge --bundle <authorized-main-bundle.json> \
  --judge-directory runs/judgments/<fresh-main-judge-dir> \
  --output runs/readiness/<fresh-scoring-dir>/main_scores.json

python tools/score_single_seed.py runs/evaluation/seed17/gemma4-seed17-ablations-v1 \
  --ablations --automated --run-judge --bundle <authorized-main-bundle.json> \
  --judge-directory runs/judgments/<fresh-ablation-judge-dir> \
  --output runs/readiness/<fresh-scoring-dir>/ablation_scores.json
```

If the ablation scoring route requires a separately bound scoring bundle, produce it from the actual release/authorization using the validators and record exactly how. Do not bypass `score_single_seed.py` or `seed17_analysis.py` audits. Preserve incomplete or abstaining judge outcomes as **UNRESOLVED**; report completion bounds rather than a fabricated final accuracy. The automated judge is not an independently human-verified correctness oracle.

Then produce the **actual, not synthetic** joint analysis:

```bash
python tools/analyze_single_seed.py \
  --run runs/evaluation/seed17/gemma4-seed17-v1 \
  --bundle <authorized-main-bundle.json> \
  --judge-directory runs/judgments/<main-judge-dir> \
  --ablations runs/evaluation/seed17/gemma4-seed17-ablations-v1 \
  --ablation-bundle <correctly-validated-ablation-bundle.json> \
  --ablation-judge-directory runs/judgments/<ablation-judge-dir> \
  --output runs/readiness/<fresh-real-analysis-dir>
```

The actual current implementation may allow the same main bundle as `--ablation-bundle` if independent authorization is verified from the ablation run manifest; **validate** rather than assume. Generate sealed outputs including `results.json`, `main_comparison.csv`, `main_metrics.csv`, `paired_effects.csv`, `ablation_effects.csv`, `clarification_curve.csv`, `readiness_confusion.csv`, `eligibility_subgroups.csv`, `failure_categories.csv`, `error_inventory.csv`, `observation_scopes.csv`, `self_reported_judge_confidence.csv`, `efficiency.csv` and analysis SVGs. This is **data and figures only**: NO report/paper/LaTeX editing.

**Statistical contract**: equal branch weights within cases, equal case weights, case-level matched S1−S0 and ablation−S1, 10,000 paired bootstrap resamples (seed 20261019), 95% percentile intervals when outcomes resolve; one seed cannot give between-seed uncertainty. Readiness is **initial** routing, terminal completeness is after allowed clarification; keep metric scopes separate. Unknown judgments are unknown; operational failures remain unsuccessful, fully counted cases; failure taxonomies overlap. Judge low/medium/high confidence is self-reported, not calibrated probability. Do not claim causal isolation stronger than intervention actually tests.

**Accept**: sealed audited result files with provenance/hashes, main contrast, five paired ablation effects or explicit unresolved bounds, clarification curves, error taxonomy, efficiency and exact denominators. An unresolved judge outcome may prevent a point estimate; preserve that limitation rather than falsely marking it complete.

### Gate K — Final research-engineering delivery

Provide a succinct final run manifest (no paper): current Git commit; protocol, technical-freeze and source hashes; main/ablation authorization evidence status; actual provider model versions and configuration; exact main and ablation run paths, seals, number of initial predictions and continuation requests; judge calibration/receipts and coverage; real scoring/analysis artifact paths/hashes; counts of abstentions/errors/unknowns; CI commands, versions and results; any limitations/blockers; and a 1–2-page interpretation of measured outcomes if fully resolved. Commit **code/tests/documentation only**, not private or protected raw results. Make artifacts securely available through the project's approved storage, not public repository files.

No output should say `FULLY DONE` unless: current-code live smoke passed; reference and judge bindings passed; technical freeze passed; explicit main and separate ablation authorizations obtained; protected main **and all five protected ablations** completed and sealed; isolated judge run completed with honest unknowns; real joint analysis passed strict audits. If the only blocker is absent authorization or genuinely inaccessible private artifacts, stop **at that precise gate** and request exactly what is missing rather than falsely claiming success.

## 7. What to avoid

- Do **not** modify/write/render the paper, or resurrect Qwen/legacy five-seed comparators.
- Do **not** regenerate approved source data, rewrite 26 clarification answers or loosen question matching to rescue model outputs.
- Do **not** treat provider HTTP 500 as definitely quota/token exhaustion; record diagnostics.
- Do **not** raise rate limits beyond real provider entitlements or parallelize calls into collisions.
- Do **not** automatically rerun unknown/failed protected requests, delete immutable receipts, or silently restart the experiment.
- Do **not** use protected gold, reference leakage or scored held-out outputs for prompt tuning or ablation selection.
- Do **not** equate synthetic 200/500 predictions to protected scientific findings.
- Do **not** create fake signatures, authorization times, five-fixture passes, reference hashes, model revisions, successful results or missing-data point estimates.
- Do **not** mark readiness green by disabling tests, relaxing schema, excluding failures, or changing denominator semantics.
- Do **not** confuse private author-reviewed references with independent human verification.
- Do **not** alter code/protocol/requirements after technical freeze and assume its hashes remain valid.
- Do **not** merge historical PRs into main again merely because they remain open.

## 8. Efficient progress and reporting

Maintain a gate checklist with evidence path, current commit, test count and blocker. Each subagent must deliver a diff/test result or a reproducible diagnosis before the coordinator marks an item done. While waiting on rate limits/provider, run independent release/judge/ablation audits in parallel. Favor isolated invented-fixture reproductions before any expensive cloud calls. Never claim background execution if you cannot schedule or actually run it.

**Milestones**: A engineering stable → B live smoke → C private release verified → D current judge calibration → E unsigned freeze → F main author signoff → G sealed main experiment → H separate ablation signoff → I sealed 500-prediction ablations → J isolated judging and real statistics → K final engineering deliverables. Only F and H require fresh user action *after exact release hashes exist*, or other genuinely missing credentials/private artifacts that cannot be recovered programmatically.

## 9. Pointers

- `docs/SEED17_CODING_AGENT_HANDOFF_20261020.md` — previous live HTTP failure evidence.
- `docs/SEED17_TECHNICAL_FREEZE_V2.md` — exact unsigned freeze strategy.
- `docs/GEMMA_SEED17_ABLATION_RUNNER.md` — interventions, execution authorization and audit.
- `docs/SEED17_ANALYSIS_PIPELINE.md` — statistical contract, output semantics and offline CLI.
- `docs/GEMMA_SEED17_AUTHOR_REVIEW_HANDOFF_20261019.md` — original author-reviewed release/provenance.
- `research/seed17_freeze.py::validate_launch_authorization` and `research/seed17_ablation.py::validate_authorization` — authoritative auth schema.
- `tools/run_single_seed.py`, `tools/run_seed17_ablations.py`, `tools/score_single_seed.py`, `tools/analyze_single_seed.py` — actual runner interfaces.
- [Failed synthetic HTTP 5xx diagnostic](https://github.com/huziibee/2610990_research_project/actions/runs/39423937361); [passing post-merge regression](https://github.com/huziibee/2610990_research_project/actions/runs/39424738891); [passing handoff-commit regression](https://github.com/huziibee/2610990_research_project/actions/runs/39425002016).

This document is an **execution specification** for the next coding agent. It does not assert live qualification, freeze authorization or protected study findings.
