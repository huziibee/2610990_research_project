# Gemini research execution tracker

Updated: 2026-10-19. This tracker supersedes the old Qwen3/99-case checklist for implementation planning. No evaluated predictions or scientific results have been produced in this work session.

## Confirmed dataset work (already complete)

- [x] Dataset renamed/versioned, all 100 sequential IDs and approved routes/strategy sequences recorded.
- [x] Three historical route disputes resolved to clarify; old-to-new crosswalk supplied.
- [x] Input/reference separation, integrity and original archive preservation verified; historical synthetic provenance disclosed.
- [x] User-requested definition corrected in Data release 1.0.1: source_records counts all 100 current inputs. Record and archive hashes are unchanged.
- [x] Dataset snapshot frozen in protocol/DATA_FREEZE_20261019.json; settled design locked in protocol/DESIGN_DECISION_LOCK_20261019.json.

## 1. Evidence and leakage prevention

- [x] Read the red-TODO manuscript and existing remaining-work checklist.
- [x] Verify the protected dataset package with `py Data/verify_package.py`: 100 cases, 74 execute / 26 clarify, all 100 routes approved, original archive and member hashes match.
- [x] Record approval scope: routes and strategy sequences are author approved; all structured task fields are **not** newly human adjudicated.
- [x] Generate separate strict model-input and reference-answer files with provenance hashes.
- [x] Test rejection of unexpected and nested reference fields at the model request boundary.
- [x] Keep all 100 cases held out; use independent synthetic fixtures for development.
- [x] Audit complete-task reference coverage, simulated answer coverage, and subgroup annotations; do not manufacture missing annotations.

## 2. Experimental protocol

- [x] Write a dated Gemini protocol candidate: primary/secondary metrics, clarification scoring, five documented run labels/seeds, paired case-level intervals, eligibility, ablations, fairness and cost controls.
- [x] Replace local checkpoint/quantization assumptions with hosted model/version/runtime reporting.
- [ ] Verify actual Gemini 2.5 Flash-Lite access with a non-evaluation prompt. Previous live attempt was blocked by local network connectivity; mocks are not live API evidence.
- [x] Decide whether S2 is retained in the main experiment or is an optional extension.
- [ ] Finalize full-task reference and independent semantic-review workflow before primary scoring.
- [ ] Define question-to-answer mapping for simulated clarification; unsupported replies must remain unavailable.
- [x] Main efficiency scope is S0/S1 on the selected Gemini model; a second model is an optional, unselected extension rather than a primary blocker.
- [x] Lock dataset/design decisions, archive reviewed development code/config hashes, runtime and the 1,000-entry paired schedule.
- [ ] Complete the final evaluation freeze with verified task references, simulated replies and semantic scorer. Held-out predictions remain disabled.

## 3. Implementation and development checks

- [x] Gemini structured-output client: seed/config/model-version/tokens/latency/error logging with no API keys in logs.
- [x] Initial strict action-ready task schema: goal, ordered actions, typed arguments, constraints, evidence, unresolved fields, dependencies, status and question.
- [x] Basic deterministic validation with clear limits: structural validity and exact evidence references are not semantic correctness.
- [x] S0 direct generation with thinking enabled; S1 goal-first then structured grounding.
- [x] Optional S2: independent second interpretation before either branch is shared for adjudication.
- [x] Clarification/revalidation loop, maximum five simulated turns, with unavailable answers recorded honestly.
- [x] Route scoring and paired confidence intervals with case/run alignment tests.
- [x] Prepared blank evaluator-only semantic-reference worksheet and independent-review rubric candidate; existing route approvals preserved.
- [x] Added local, loopback-only human annotation/review workbench with explicit ledger-bound preparation, adoption, independent verification, disagreement and final approval actions.
- [x] Added GitHub Actions checks for data release integrity, synthetic tests and non-authorization of held-out evaluation.
- [ ] Human preparers and independent reviewers complete all 100 semantic references and 26 clarification cases; browser code does not substitute for semantic adjudication.
- [ ] Confirm new workflow's full repository CI run succeeds before merging.
- [ ] Implement and verify semantic task comparison/scoring after complete references and equivalents are supplied.
- [ ] Supply independently verified capability catalogs to activate permitted-action/required-field checks for actual cases; raw prose is not such a catalog.
- [x] Run regression tests exclusively on synthetic examples and review agent work.

## 4. Experiments (not started)

- [ ] Main comparison: five runs/system, same frozen cases, schema, context and declared inference budgets.
- [ ] Five independent removals: goal-first, structured grounding, scene, dependency checks, dialogue.
- [ ] Efficiency: median/P95 end-to-end latency, calls, input/output/reasoning tokens and versioned pricing; report unavailable provider hardware metrics as unavailable.
- [ ] Simulated clarification completion at turns 0–5, separately from initial decisions and observed human conversations.
- [ ] Primary/secondary failure categories and independently verified representative examples.

## 5. Manuscript and release

- [x] Correct the red-TODO draft's model, dataset count, approval scope and obsolete route-dispute claims.
- [x] Preserve original report source/PDF; clearly identify revised planning source and PDF build status.
- [ ] Populate Results only from frozen, scored, verified experiments; no placeholder numbers.
- [ ] Finish bibliography, limitations, reproducibility package and rendered paper QA.

## Progress evidence

- Dataset integrity check: PASS on 2026-10-19, release 1.0.1.
- Mock pipeline smoke: S0 PASS (1 call), S1 PASS (2 calls), S2 PASS (4 independent-stage calls; matching proposals did not require adjudication).
- Independent reviews found and fixed reference integrity checks, context contamination, pointer validation, output parsing and protocol/runtime mismatches.
- Revised Gemini working source created; original TeX/PDF preserved, revised PDF not compiled.
- Regression suite: 33/33 PASS after independent review fixes.
- Main evaluated results: NOT_COMPUTED.
- Full semantic reference coverage: not established; the supplied native gold currently supports routing/annotation fields, not complete action-ready specifications.
- Live Gemini access: latest research smoke failed with CONNECTION_FAILURE; no modelVersion or live token usage was obtained. Earlier raw helper showed WinError 10061.
- A failed tempfile test left an inaccessible empty workspace folder; automatic approval policy rejected exact-path nonrecursive cleanup. No ACL changes or further deletion attempted.
