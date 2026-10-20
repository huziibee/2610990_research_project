# Gemma smoke tests before one full seed

User scope: `gemma-4-26b-a4b-it`, thinking off, smoke tests first; the next intended evaluation is one full seed, not the historical five-seed sweep. No protected predictions were run.

The candidate configuration uses `thinkingLevel: minimal` and `includeThoughts: false` at every stage, including direct generation and optional adjudication. Requested output caps are matched: S0 4096; S1 two calls of 2048. Provider JSON schema and strict local validation are retained. Zero automatic transport or malformed-output retries remain in force. Google's [Gemma API documentation](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) defines minimal as thinking disabled. Missing provider reasoning-token fields stay unavailable, rather than being reported as measured zeros.

| Priority | Work | Smoke evidence and remaining gate |
|---|---|---|
| Critical | Semantic reference release | Read-only schema, receipt/export hashes and all 100 ledger bindings pass. Exactly 26 clarification cases contain 26 branches. Existing author signoff is preserved. Independent verification and final approval remain incomplete; authenticated two-model review logs are absent. |
| Critical | Live model verification | Gemma access succeeded in minimal diagnostic requests. S1 initial prediction passed with the current 2048-per-stage caps and provider schema in `runs/development/20261019T193654Z_9ba00626`. S0 diagnostic succeeded at 4096 but the standard smoke remains unresolved with HTTP 500 INTERNAL. S0/S1 live readiness is not jointly green. |
| Critical | Full multi-turn evaluation | New `--clarification` development mode exercises one synthetic question, one simulated answer and revalidation: mock S0 passes with two calls; mock S1 passes with four. Live attempts did not complete this cycle. Existing protected runner still performs initial predictions only. Protected oracle/process orchestration and all eligible branches need verification before a full evaluation. |
| Critical | Experimental freeze | Candidate only; held-out predictions disabled. Preserve historical lock/snapshot bytes. Rebuild protocol binding, prompt/code/runtime hashes, reviewed subgroup labels, scoring fixtures and readiness bundle after missing evidence is supplied. |
| Critical | Main results | Next intended seed: 17; all 100 cases paired across S0/S1 (200 initial predictions, plus approved clarification trajectories). Independent scoring and paired case-level confidence intervals remain uncomputed. |
| Next | Five ablations | Synthetic intervention tests are available. One matched seed would contain 500 initial ablation predictions, plus the approved clarification trajectories. Existing limitations of prompt/checker controls remain applicable. No evaluated ablation ran. |
| Next | Latency and cost | Live development call logs contain latency and provider input/output tokens. They are smoke measurements, not main-result estimates. P50/P95, consumption, versioned API pricing and trade-off figures must use completed matched evaluation logs. |

Reference audit: `runs/development/gemma_private_reference_audit_20261019.json`. Existing review workspace: `runs/human_review_20261019`; its separate author receipt is `AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED`. The default blank annotation workspace is not the private author-reviewed release.

Do not run the historical `run_experiment.py --execute` sweep for the proposed single seed. Its schedule and several archive/scoring checks still require five seeds. Amend and test those together, including paired ablations and completed clarification trajectories, before releasing the single-seed protocol. Preserve the original 1000-row schedule as historical evidence. A single seed supports paired case-level intervals but cannot estimate variation across seeds.

## Reproduce development checks

```powershell
py Data/verify_package.py
py -m unittest discover -s tests -v
py tools/run_development.py --system S0
py tools/run_development.py --system S1
py tools/run_development.py --system S0 --clarification
py tools/run_development.py --system S1 --clarification
```

Adding `--live` uses the existing local API key and only synthetic inputs. Each attempt creates a fresh logged directory; preserve failures. The development clarification reply whitelist is specific to the new synthetic shelf example and cannot replace protected, independently reviewed question-to-answer rules. JSON-only diagnostic probes did not resolve provider errors and were not adopted as an alternate decoding policy.

Main semantic results, confidence intervals and API-cost tables remain `NOT_COMPUTED`.

Final local verification: **252 tests passed**, zero failures/errors (`runs/development/gemma_verified_regression_20261019.log`). Final mock clarification runs: `20261019T194259Z_74f51e2a` (S0, two calls), `20261019T194259Z_5fb1918c` (S1, four calls). The machine-readable evidence index is `runs/development/gemma_smoke_summary_20261019.json`; these artifacts are development evidence, not a frozen readiness release.
