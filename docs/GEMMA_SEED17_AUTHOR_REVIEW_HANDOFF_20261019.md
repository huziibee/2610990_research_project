# Gemma seed-17 author-approved, agent-assisted evaluation

The selected evaluation method is **AUTHOR_APPROVED_AGENT_ASSISTED**, registered in `protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json`. The existing reference release is accepted as **AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED**. No additional human reviewer, per-output human scoring, independent verification or authenticated model-review log is claimed or required. Protected evaluation and ablations remain disabled.

## Completed implementation

- The separate Gemma protocol and version-4 readiness gate validate the exact existing author receipt, canonical receipt hash, raw export hash, source/route/worksheet pins, all 100 ledger histories and revisions, human adoption, task schemas, typed arguments, evidence pointers, all 26 branches and explicit eligibility labels. The original independent-review gate, oracle and semantic scorer remain available; the selected automated APIs are separate. The earlier seed-17 configuration, unsigned freeze and candidate amendment are preserved as versioned historical copies. Git history also retains the previous seed-17 gate implementation.
- Matching accepts only the already approved canonical questions, with whitespace collapse and Unicode casefold. The evaluator releases exactly one approved answer after a match. No paraphrases or answers were generated or added. The immutable matching projection includes answer hashes; the eligibility projection includes all source-to-reference bindings and capability-catalog, dialogue and dependency eligibility. Plaintext projections stay ignored under `runs/`.
- Layer A checks structure, readiness/stops, typed fields, evidence validity, approved capability catalogs, action/argument/constraint/dependency agreement and exact approved tasks. Structural differences requiring semantic interpretation remain unresolved, rather than automatically becoming errors. Layer B uses a fixed, system-blinded semantic rubric and an isolated **gemini-3.8-live** judge. It records field decisions, evidence explanations, confidence and abstention with configuration/prompt/request/response hashes and available usage. No judge data or feedback enters generation.
- Live uses a schema-declared `submit_semantic_judgment` function and strict local validation. Google documents that Gemini 3.8 Live does not support response-schema enforcement or thinking-level settings. The judge therefore uses its native Live API behavior and records reasoning-token usage without retaining thought text. Gemma generation still uses minimal thinking, `includeThoughts: false`, provider JSON schema and strict local validation. Unavailable provider revisions and response IDs are not invented; actual provider tool-call IDs are retained.
- Missing, malformed or abstaining semantic judgments remain unresolved. Every case and operational failure stays in the denominator. The scorer reports branch-averaged completion bounds and withholds the point estimate and paired interval while outcomes remain unresolved. Resolved results use paired case-level bootstrap intervals; one seed cannot estimate between-seed variability. Results are labelled **automated semantic evaluation**, never independently human-verified correctness.
- Protected judging is implemented as a separate evaluator process for an explicitly authorized, sealed experiment, with exact source/reference/configuration bindings and immutable no-reroll request receipts. Its frozen-configuration and authorization gates currently block execution.

## Verified reference and recovery evidence

The current release contains exactly **100 references, 74 execute / 26 clarify and 26 branches**. The existing restored workspace was revalidated against the original source pins and ledger: **303 files match byte for byte**. The original plaintext exports, author receipt, ledger, encrypted archive and encryption key were not changed.

- Author receipt SHA-256: `5cdda0cbc69724a0c04a7a12988b442d8b1751ee3b5b00747142bbaf5a3b29c8`.
- Reference export SHA-256: `8bff3db92f2539b284d0fee359dc245979c25553d211b5931273591a0daed138`.
- Encrypted archive SHA-256: `4290647c43bb69f0caf36c32601f9c6b2693eb399d8f42cf33fcf6ac151d48d0`.

The final integrity report and immutable matching/eligibility projections are in `runs/readiness/gemma_seed17_agent_eval_safe_20261019_v1/author_release/`. Their hashes are pinned in the candidate readiness bundle. These are frozen reference projections, not a signed experimental release.

## Safe validation and CI

`py tools/validate_seed17_safe.py --output runs/readiness/gemma_seed17_agent_eval_safe_20261019_v1` passed **309 tests**, frozen-data verification, synthetic S0/S1 and clarification tests, a complete **200-prediction mock schedule with 528 mock calls**, all five mock judge fixtures, and schedule/trajectory audits. The 500-prediction ablation schedule was prepared only. Tampering, receipt replay, interruptions, invalid matching/eligibility, unavailable judgments, abstention, pairing/denominators and generator/evaluator isolation have synthetic regression coverage. The exact remaining CI annotation-triage guard also passed locally. Dependency versions and code/prompt/protocol fingerprints are archived with the tests.

PR #13's original [failed regression job](https://github.com/huziibee/2610990_research_project/actions/runs/39320961249) ran 290 tests and failed only the archive round-trip test because `cryptography` was missing. Regression workflows now install `requirements.txt`; it pins the actual locally tested `cryptography` and `websockets` versions. Tests are not skipped or weakened. Consult the PR's current checks for the pushed revision; local results and GitHub results are distinct evidence.

Separate live synthetic judge diagnostics were also run, outside the safe harness. Early sessions exposed a shared-journal reasoning-policy mismatch and evidence-pointer format mismatch; those attempts remain immutable. The corrected version-3 calibration passed exact-match and paraphrase fixtures, then stopped at the incorrect-argument fixture because the judge omitted mandatory evidence paths in several fields. That response identified the incorrect argument but failed strict judgment validation, so it remains **UNRESOLVED**. The last two fixtures were not sent. No automatic retries, protected generation or protected judging occurred. Raw local diagnostics remain in `runs/judgments/seed17_gemini38_live_calibration_20261019_v1`, `_v2` and `_v3`; none is a complete live calibration pass.

## Exact remaining readiness blockers

Current state: **31 passed / 5 blocked**, `ready=false`, `protected_execution_authorized=false`, `benchmark_executed=false`.

1. `automated_judge_calibration`: complete a valid current-code live synthetic calibration including incorrect and abstaining examples. Existing live evidence is incomplete.
2. `live_multi_turn`: obtain successful current-code live synthetic S0 and S1 paths completing two approved replies. Prior initial smokes do not establish this.
3. `automated_evaluator_frozen`: freeze the final judge configuration, rubric and model identity after compatibility/calibration work; retain any unavailable revision limitation.
4. `frozen_protocol`: finalize the exact protocol/code/runtime/hash bundle. The protocol remains a candidate with held-out execution disabled.
5. `signed_off_release`: supply separate explicit launch authorization and a complete signed-off freeze. Current user instructions explicitly prohibit protected execution.

No second-human approval or per-output human judgment is among these blockers. Integrity checks do not guarantee semantic truth. Author-review bias, automated evaluator bias, correlated model errors, exact-question coverage, simulated replies and one-seed uncertainty are explicit methodological limitations.

## Current manuscript and safe commands

The updated [Gemma seed-17 manuscript](../Report/Cooccurring_Ambiguity_Paper_Gemma_Seed17_Working.tex) describes the actual author-approved reference provenance, programmatic validation, frozen automated rubric, Gemini 3.8 Live transport, abstention and limitations. Earlier manuscripts and PDFs are preserved. A new PDF has not been compiled or visually checked.

```powershell
py tools/check_seed17_readiness.py --bundle runs/readiness/gemma_seed17_agent_eval_safe_20261019_v1/candidate_bundle.json
# Expected exit 2: remaining release/calibration/multi-turn gates are blocked.
py tools/prepare_seed17_author_release.py --output runs/readiness/NEW_PRIVATE_PROJECTION_VERSION
py tools/calibrate_seed17_judge.py --output runs/judgments/NEW_MOCK_CALIBRATION_VERSION
# Explicit future synthetic-only live calibration, with a fresh directory:
py tools/calibrate_seed17_judge.py --live-synthetic --output runs/judgments/NEW_LIVE_CALIBRATION_VERSION
```

Offline automated scoring and optional isolated judge execution are exposed by `tools/score_single_seed.py --automated` and `--run-judge`; they require a sealed protected archive and an exact release bundle. `--run-judge` additionally requires a frozen evaluator and explicit protected authorization. Neither was invoked. No protected predictions, ablations, main semantic scores or main confidence intervals were produced.
