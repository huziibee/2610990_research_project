# Manuscript results renderer (separate from semantic judging)

**Branch:** `research/paper-results-20261019`, based on the reconciled evaluation branch. It does not modify the protected dataset, approved routes, semantic-gold ledger, blinded reviewer workflow, core experiment runner, or the working `.tex`. Human-scored experiments remain pending.

## Why this exists

The working Gemini manuscript asks for: (1) S0/S1 complete-task/route/unsupported table, (2) five-seed stability points, (3) accuracy-versus-median-latency figure, (4) P50/P95 latency table, (5) five ablations relative to S1 with matched eligibility, (6) failure categories, and (7) clarification success through turn five. The renderer emits **review-only LaTeX candidate artifacts** for these seven slots, plus a per-seed CSV and a JSON summary. It never manufactures values or overwrites report source.

## Expected handoff bundle

`tools/render_paper_results.py` consumes a **post-scoring, human-verified evidence bundle**, not predictions. The other workstream must decide and authenticate semantic judgments first. Interface schema:

```json
{
  "schema_version": 1,
  "evidence_class": "INDEPENDENTLY_SCORED",
  "review_manifest_sha256": "<actual SHA-256 of externally authenticated scoring/reviewer release>",
  "seeds": [17, 29, 43, 71, 101],
  "case_run_scores": [
    {"case_id": "CA-0001", "seed": 17, "condition": "S0",
     "complete_task_correct": null, "route_correct": null, "unsupported": null}
  ],
  "eligible_case_ids": {"dialogue": ["CA-xxxx"], "dependency_checking": ["CA-yyyy"]},
  "completion_by_turn": {"S0": [0, 0, 0, 0, 0, 0], "S1": [0, 0, 0, 0, 0, 0]},
  "latency_seconds": {"S0": {"p50": 0, "p95": 0}, "S1": {"p50": 0, "p95": 0}},
  "failure_analysis": {
    "incorrect_goal": {"count": 0, "denominator": 1},
    "wrong_argument": {"count": 0, "denominator": 1},
    "missing_constraint": {"count": 0, "denominator": 1},
    "unsupported_detail": {"count": 0, "denominator": 1},
    "unnecessary_clarification": {"count": 0, "denominator": 1},
    "missing_clarification": {"count": 0, "denominator": 1}
  }
}
```

**This is illustrative SHAPE ONLY**, deliberately incomplete and containing invalid placeholder/null correctness. Do not pass it as scientific evidence. A real scored bundle must include **exactly one row per (100 case IDs × five seeds × seven conditions) = 3,500 case/run/condition rows**; `complete_task_correct` is a verified score from 0–1, including branch averages where applicable; missing `route_correct` or `unsupported` is explicit `null` and displays an em dash. `completion_by_turn` must have six nondecreasing values and its final value must equal scored final correctness.

For the real bundle, a `review_manifest_sha256` label is **not proof of review by itself**. The evaluator must independently verify the manifest, its hashed judgments, released references, independence of reviewers, locked eligible sets and the frozen run grid before creating this render input. This presentation module checks structure/completeness, not reviewer authentication or semantic truth.

Per-case grouping matters: the rows must already contain the 0–5-turn semantic score after branch averaging, **not an initial route correctness flag**. The scene and dependency mechanism controls must retain the limitations documented in `protocol/BRANCH_RECONCILIATION_20261019.md`. A human must also validate failure-category coding; categories may overlap unless a separate primary-type coding procedure prevents this.

## Commands (on Windows)

```powershell
git fetch origin
git worktree add ..\research-paper-check origin/research/paper-results-20261019
cd ..\research-paper-check
py -m unittest discover -s tests -v
```

Once an **actual independently reviewed** scored bundle has been prepared:

```powershell
py tools/render_paper_results.py --scored-bundle runs/scoring/verified_paper_bundle.json --output runs/paper_candidate_001
```

The output directory must not exist. Nothing writes into the manuscript automatically. Generated `.tex` and `run_variation_figure.tex`, `tradeoff_figure.tex`, `clarification_figure.tex` can be reviewed and manually integrated after authenticity and statistical checks; do not imply completed benchmark results from mere LaTeX output. Synthetic tests call the pure function with `synthetic=True` and use `SYNTHETIC-*` IDs.

## Still open

- Verify the new renderer tests (full checkout CI/local run); reconcile with changes from the semantic-scoring workstream.
- Agree the final scored bundle exporter and verify all reference/reviewer hashes outside this renderer.
- Add paired case-level bootstrap intervals from the already implemented `research.semantic_metrics.paired_semantic_bootstrap`, with a rigorously reviewed S1-minus-S0 sign and no treating 500 outputs as independent cases.
- Apply subgroup logic to complete-trajectory case/run correctness; additionally report eligible denominators and failure coding agreement.
- Perform a visual LaTeX compile/column-fit review before replacing any manuscript placeholders.
- Attach dated provider pricing or explicitly mark monetary cost unavailable; efficiency reporter does not infer prices.

**No empirical accuracy, stability or completion results are asserted by this branch.**
