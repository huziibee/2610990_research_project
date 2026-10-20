# Seed-17 automated analysis

`protocol/seed17/analysis_contract_v1.json` registers the metrics and statistics.
This is **automated semantic evaluation** of author-approved, agent-assisted
references. It does not claim independent human verification or guaranteed
semantic truth. No experimental results are included here.

The offline analysis command reads actual sealed run archives through the same
strict audits and exact author-release joins as the scoring command. It cannot
generate predictions or invoke the judge. Main-run analysis requires a ready,
explicitly authorized bundle. An ablation archive additionally requires its own
authorization and audit; use its separate bundle and judge receipts. Unsigned
development bundles cannot be used as study-result releases.

After the separately authorized experiments and isolated judging have finished:

```powershell
py tools/analyze_single_seed.py --run <sealed-main-directory> --bundle <authorized-main-bundle.json> --judge-directory <main-judge-directory> --output <new-analysis-directory>
```

To include the separately authorized ablation archive, add:

```text
--ablations <sealed-ablation-directory> --ablation-bundle <authorized-ablation-bundle.json> --ablation-judge-directory <ablation-judge-directory>
```

Optional `--pricing <dated-verified-tier-pricing.json>` uses the existing scoring
pricing contract. Missing tokens, provider revision identifiers or verified
prices remain unavailable. Generation efficiency includes provider elapsed time
and pacing, excluding oracle/coordinator processing, crash downtime and judge
costs. The source scoring output retains token-reporting coverage and raw
latency values. These are estimates rather than invoices.

For safe development, run this command with no study-artifact arguments:

```powershell
py tools/analyze_single_seed.py --synthetic-fixture --output runs/readiness/synthetic_analysis_unique
```

The four invented cases test exact success, failure, two-reply clarification and
abstention. Every generated table and vector figure carries the
`SYNTHETIC_DEVELOPMENT_ONLY_NOT_STUDY_FINDINGS` label. Existing output directories
are never overwritten. `analysis_seal.json` hashes every completed output file.

## Denominators and uncertainty

The independent statistical unit is the source case, with seed 17 only. Approved
answer branches receive equal weights within a case before cases are averaged.
Readiness confusion counts use one initial prediction per case, even if its
initial result is shared by several branches. Operational errors remain
complete-task failures and readiness errors; semantic fields without judgments
remain unknown.

Unresolved case outcomes block the corresponding point estimate and paired
confidence interval. Completion bounds preserve known branch contributions and
place unknown branch outcomes between zero and one. They are identification
bounds, **not confidence intervals**. Missing semantic decisions never become
fabricated zeroes, successes or complete-case-only estimates.

Resolved contrasts use 10,000 paired source-case bootstrap resamples with seed
20261019 and percentile 95% intervals. The main contrast is S1 minus S0. Each
registered ablation is compared to the same main S1 case/seed/branch grid.
Eligibility subgroup contrasts use frozen dialogue, dependency and capability
catalog labels; they are descriptive, without multiplicity-adjusted inference.
One seed cannot estimate between-seed variability.

## Outputs

- `results.json`: all summaries, case scores, provenance bindings and unknowns.
- `main_comparison.csv`, `main_metrics.csv`: readiness plus explicitly scoped
  initial/terminal semantic dimensions, unsupported-detail rates and operational failures.
- `paired_effects.csv`, `ablation_effects.csv`: paired differences and intervals;
  unresolved contrasts have empty estimates and intervals.
- `clarification_curve.csv`: cumulative success by turn zero through five for
  all cases and initially clarify-eligible cases.
- `readiness_confusion.csv`: reference readiness versus predicted readiness,
  including an explicit operational-error column.
- `eligibility_subgroups.csv`: case-weighted subgroup dimensions and denominators.
- `failure_categories.csv`, `error_inventory.csv`: nonexclusive error categories
  and case identifiers; no source text, answers, predictions or references.
- `efficiency.csv`: P50/P95 generation latency, tokens and available dated costs.
- `observation_scopes.csv`: initial, terminal-branch and all-unique-prediction
  denominators; explicit abstentions, unresolved outcomes and unsupported-detail
  incidence without deleting errors or unknowns. Shared initial predictions are
  counted once across branches. These output-level diagnostics differ from the
  primary case-weighted outcome.
- `self_reported_judge_confidence.csv`: low/medium/high counts and unavailable
  counts for every semantic field and observation scope. Confidence is a model
  report, not a calibrated probability of correctness.
- Vector SVGs for all-case and initially clarify-eligible completion curves, complete-task comparisons, paired effects,
  failure categories and available latency measurements.

Failure taxonomy counts overlap. They cannot be summed to infer the number of
failed cases. Unsupported-detail rates require a decisive supported/unsupported
judgment; missing judgments remain unresolved. Terminal and all-turn abstention
and unknown counts are reported separately in JSON. Judge provenance and
response evidence remain in the isolated immutable evaluator archive, never in
generation inputs. Do not use these judgments to tune systems on protected cases.
