# Gemini research implementation

Current implementation: [Gemma seed-17 local handoff](docs/GEMMA_SEED17_LOCAL_HANDOFF_20261019.md). The protected single-seed runner, oracle boundary, no-reroll journaling, pacing, archive audit and scoring bridge are implemented. Its separate protocol remains CANDIDATE and its freeze UNSIGNED. Run `py tools/validate_seed17_safe.py --output runs/readiness/NEW_NAME` for synthetic-only validation; no protected evaluation is authorized.

> Current model amendment (2026-10-19): use `gemma-4-26b-a4b-it`, thinking OFF (`thinkingLevel: minimal`), provider JSON schema and strict local validation. S0 output cap 4096; S1 2048 per stage. Synthetic smoke tests first, then one full seed (17) after readiness release and runner/scoring amendments. Earlier Gemini/thinking-enabled and five-seed descriptions below are historical and superseded for the next run. See [model amendment](protocol/amendments/GEMMA_THINKING_OFF_20261019.json). Held-out predictions remain disabled.

Start with [TODO.md](TODO.md) for completed work and [protocol/FREEZE_STATUS.md](protocol/FREEZE_STATUS.md) for the exact remaining gates. Main design: all **100 source input records**, S0 direct versus S1 structured, five runs each, Gemini 2.5 Flash-Lite with thinking enabled in both. S2 is optional. No evaluated predictions or scientific results have been produced.

## Run local checks

No external Python packages are required; use the Windows `py` launcher.

```powershell
py Data/verify_package.py
py tools/prepare_evaluation_data.py
py -m unittest discover -s tests -v
py tools/run_development.py --system S0
py tools/run_development.py --system S1
py tools/run_development.py --system S2
```

The three development commands use a newly authored synthetic fixture and mocked transport. Logs explicitly label mock execution; token counts missing from the provider remain null. Actual non-test Gemini access can be checked with:

```powershell
py tools/run_development.py --system S0 --live
```

This uses the local `.env` key and incurs normal Gemini API usage. It accepts only the fixed development fixture, with no held-out input-path argument. Each run writes a new directory under `runs/development/`; credentials and provider error bodies are excluded from logs. JSON transport success and prediction/schema validity are separate statuses. A failed live smoke request is not a successful model test.

## Input, reference and scoring boundaries

`research_data/model_inputs/` contains model inputs, while `research_data/references/` holds existing route/native/history annotations. Strict input validation admits only instruction, scene, dialogue and capability descriptions to prompts. Intermediate contexts are also restricted by stage. Original and derived hashes are verified before preparation or offline scoring; accidental reference merges, duplicate JSON keys, modified routes and incomplete run grids fail closed.

`research/task_schema.py` validates goal/action/argument/evidence/dependency/unresolved-field structure. A separately verified capability catalog can enable deterministic permitted-action and required-field checks; raw capability prose is not falsely treated as such a catalog. Evidence-reference existence does not prove semantic support. Textual contradictions, missing semantic requirements and semantic equivalence still require the independent scoring workflow.

`tools/score_routing.py` supports offline routing metrics and paired case-level bootstrap intervals on complete real evaluated prediction grids. Errors stay in the denominator. It rejects development/mock logs. It does **not** score complete-task correctness from route labels.

`annotation/semantic_reference_template_100.jsonl` is a blank evaluator-side worksheet, not gold. It holds existing route approvals separately from missing semantic specifications and simulated answers. Do not send it to a model during prediction.

## Paper and freeze status

`Report/Cooccurring_Ambiguity_Paper_Gemini_Working.tex` is the revised planning source. Original paper source/PDF files are preserved; a revised PDF has not been compiled. Results remain placeholders. Protocol configuration is a candidate with held-out prediction disabled; the dataset and settled design decisions have dated lock records. Full experimental freeze awaits the references, scoring evidence and live access listed in `protocol/FREEZE_STATUS.md`.
