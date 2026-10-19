# Research paper — remaining work (19 October 2026)

**Status:** Manuscript and study design exist; experiments are not represented as completed. Red notes and red `TBD` cells in the accompanying PDF mark unfinished items. This is a priority-ordered execution checklist, not a claim that any of the tasks below has been run.

## Phase 1 — Freeze the experiment BEFORE evaluated runs (essential)

- [ ] **Adjudicate and freeze the 99-case reference.** Confirm the final author-approved action-ready specifications, including disputed routing labels for CA-0029, CA-0239, and CA-0565; version the reference and record reasons for any changes. Preserve the dataset as a single 99-case dataset in the paper. The 76/23 split describes recorded original route labels and must not be silently treated as final if adjudications change.
- [ ] **Prevent answer leakage.** Only send utterance, scene, dialogue, and capability input fields to models; keep task references, expected clarification answers, and human adjudication separate. Use distinct non-test examples for all prompt/schema debugging.
- [ ] **Freeze study protocol.** Declare primary endpoint (complete-task semantic correctness), secondary metrics (route confusion matrix, field grounding, unsupported details, question quality, completion, latency), five runs, paired case-level comparisons, and eligible subsets. Register interpretation rules for hypothetical clarification answers.
- [ ] **Select exact Qwen3 checkpoints.** Pin primary and smaller checkpoints, thinking-mode support, quantization, inference backend, same final schema, matched prompts/context, maximum thinking tokens, and inference-budget comparisons. A smaller model is an efficiency analysis, not an artificially weakened main baseline.

## Phase 2 — Build and smoke-test the pipeline (essential)

- [ ] **Implement Qwen3 inference and logging.** Record seeds, versions, model calls, token counts (including reasoning), end-to-end latency, and hardware/runtime state.
- [ ] **Implement the task schema.** Use standard typed JSON/Pydantic validation for goals, action order, required arguments, constraints, evidence references, status, and clarification questions; independently test semantic grounding.
- [ ] **Implement S0/S1 and optional S2.** S0 direct-to-schema; S1 goal -> grounded arguments -> readiness validation -> targeted clarification; S2 an independent interpretation and optional adjudication before validation. Smoke-test on synthetic/non-evaluation examples.
- [ ] **Implement the CLARA-inspired clarification loop.** Ask for only unresolved critical information, incorporate hypothetical answers, reevaluate, and stop at five turns. Label these as simulated outcomes, not observed user conversations.
- [ ] **Build scoring/reporting and regression tests.** Validate full-task semantics and action references; add error categories, routing confusion matrix, per-case logs, and checks against improper reuse of AmbiK substring matching.

## Phase 3 — Execute the planned comparisons (essential for results)

- [ ] **Main comparison:** S0 vs S1 vs S2 on identical inputs, with comparable output schemas and inference budgets; five documented runs.
- [ ] **Component and context ablations:** drop goal-first, structured representation, scene, dialogue, and dependency checks with eligible-case denominator reporting; linked-dependency results are exploratory due to small explicit subgroup.
- [ ] **Efficiency tests:** primary and smaller Qwen3 checkpoint by system; p50 and p95 end-to-end latency, tokens and cost, consistent warmups and server conditions.
- [ ] **Clarification evaluation:** initial necessity, quality/minimality, eventual completion with stated simulated-answer assumptions, missed critical details and unnecessary queries.
- [ ] **Case-level failure audit:** assign primary failure classes and select 2–3 illustrative cases with explicit input evidence.

## Phase 4 — Complete writing and release (essential for submission)

- [ ] Replace **every red TBD** and red empty plot note with real values and uncertainty intervals; double-check figures/tables appear after their first mention and captions/axis labels are accurate.
- [ ] Write Results interpretations tied to RQ1–RQ3; acknowledge null findings, uncertainty, small sample and synthetic clarification replies without overstating claims.
- [ ] Write Discussion, limitations and future work; update abstract, introduction, conclusion with verified findings only.
- [ ] Audit all citations for exact title/authors/year/venue/DOI/URL; verify model provenance and permissible repository reuse/licenses.
- [ ] Prepare reproducibility release: versioned gold/reference, source files, prompts, configs, pinned checkpoints, scripts and access restrictions, subject to dataset release permission.
- [ ] Final proofread, check Wits experimental-CS rubric, visually inspect every IEEE two-column page, and verify page minimum and figure/table placement.

**Priority if time is limited:** freeze reference and protocol -> S0/S1 -> scoring -> main comparison -> ablations -> latency -> S2 -> complete paper. Do not sacrifice matched baselines and valid evaluation to add extra models.
