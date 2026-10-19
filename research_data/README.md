# Evaluation data boundary

Run `py tools/prepare_evaluation_data.py` to reproduce these derived files.
`Data/` remains the immutable published source. `MANIFEST.json` records SHA-256
hashes of every original file and every derived JSONL file.

- `model_inputs/evaluation_100.jsonl` contains only record ID and the four permitted
  input fields: instruction, scene, dialogue, and capabilities.
- `references/author_approved_routes_100.jsonl` holds the authoritative route and
  strategy references. The other two reference files retain native annotations
  and annotation review history separately.
- `research.input_contract.model_visible_context` validates exact keys and types
  immediately before requests and omits the record ID from model context.

All 100 cases are evaluation-only: 99 originate from the frozen Pilot-120 subset
and one is assistant-authored synthetic. None may be used for prompt development,
debugging, checkpoint selection, or development splits. Debug with newly authored
examples independent of these cases. Local IDs are specific to this release.

The author approved routes and strategy sequences for all 100 cases, synthetic
inclusion, and the CA-0025 capability attestation. This does not establish human
adjudication of every structured field or independent blinded review. The native
annotations do not contain complete semantic action/argument specifications or
annotated hypothetical clarification replies. Complete-task and simulated-turn
evaluation remain blocked until those references are independently prepared and
frozen; route accuracy alone cannot establish complete-task correctness.

The leakage test checks schema contamination, strict request context, file
separation, provenance hashes, and reference independence. It cannot prove that
arbitrary natural-language source text contains no unintended hints, or protect
against code that deliberately bypasses the request boundary.
