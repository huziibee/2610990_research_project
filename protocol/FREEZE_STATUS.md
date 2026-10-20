# Freeze status

> Current model amendment (2026-10-19): use `gemma-4-26b-a4b-it`, thinking OFF (`thinkingLevel: minimal`), provider JSON schema and strict local validation. S0 output cap 4096; S1 2048 per stage. Synthetic smoke tests first, then one full seed (17) after readiness release and runner/scoring amendments. Earlier Gemini/thinking-enabled and five-seed descriptions below are historical and superseded for the next run. See [model amendment](amendments/GEMMA_THINKING_OFF_20261019.json). Held-out predictions remain disabled.

**Design decisions locked. Full scientific protocol: NOT_FROZEN. Held-out predictions: disabled.**

The design below is settled and is not expected to change during ordinary implementation. A full freeze also requires verified task references, a scoring procedure and the evidence needed to run the design. Those missing artifacts cannot be replaced by labelling a document frozen. This distinction preserves the completed work and avoids reopening decisions already made.

## Done: stable decisions and completed foundations

- Current dataset: **100 source/model-input records**, all protected for evaluation; 74 execute and 26 clarify. All 100 are source records in the author's corrected reporting classification. CA-0100 had an earlier disputed `assistant_authored_synthetic` origin label in the immutable release 1.0.1 files; the author's current correction is recorded separately in `protocol/amendments/CA-0100_source_status_20261019.json`. It remains the 100th protected evaluation input. This correction does not assert that CA-0100 belongs to the original Pilot-120 subset. Metadata clarification in version 1.0.1 changes no input rows or approved routes.
- All 100 routes and strategy sequences are author approved. Dataset renaming, sequential IDs, historical dispute resolution, crosswalk, corrected source-status overlay and preserved historical provenance, separate source/label files and hashes are already completed.
- Gemini **2.5 Flash-Lite** is the selected model. S0 and S1 are the main systems; S2 is an optional extension. No further choice about their main/optional status is needed.
- Main comparison: all 100 cases, five runs per system, seeds 17, 29, 43, 71, 101; **10 main runs**. The seed field is logged without claiming hosted determinism.
- Thinking is enabled in both main systems. S0 uses one call with generation/thinking caps 8192/2048. S1 uses two real stages with caps 4096/1024 each. Summed requested caps match; actual input tokens, consumption, call count and latency are still measured.
- Development defaults: temperature 0.7, topP 0.95, JSON responses, thought summaries off, 90-second timeout, zero automatic retries. Optional S2's second interpretation is independent; exact structured disagreement triggers adjudication.
- Primary target: a semantically correct completed task by at most five simulated clarification turns. Correct routing or a good initial question alone does not count as completed-task success. Initial routing and question quality are separate measures.
- Paired case-level intervals average runs within each case before bootstrapping cases; five outputs for one case are not five independent samples. Five specified ablations and the dependency/dialogue subgroup definitions are documented.
- Source/derived integrity, leakage boundary, stage independence, budgets, malformed-response and paired-denominator checks have passed local tests. These checks establish software behavior, not scientific performance.

## Still required: evidence gates

| Gate | Missing evidence | Why it prevents a full freeze |
|---|---|---|
| Complete semantic references | Verified goals, required actions/arguments, constraints, acceptable equivalents and evidence for all 100 cases | Approved routes/strategy sequences alone cannot score complete-task correctness |
| Simulated clarification | Verified hypothetical replies, question-to-field matching rules and branch-specific expected tasks | The pipeline cannot invent a reply or use a complete hidden answer as dialogue |
| Subgroup eligibility | Verified relevant-dialogue and explicitly linked-dependency case manifests | Nonempty dialogue and co-occurring ambiguity labels do not establish these subgroups |
| Semantic scoring review | Tested rubric, correct/incorrect fixtures and independent review for borderline judgments | JSON/schema checks and model self-review do not prove semantic equivalence |
| Live model access | Successful non-evaluation request with chosen model/settings and recorded modelVersion/usage | Documentation lists support but does not establish this project's access or request success |
| Final evaluation archive | Reviewed development snapshot, runtime inventory, exposure log and the 1,000-entry paired schedule are prepared; final semantic references/scorer are still missing | The final evaluated snapshot must include those missing artifacts before predictions |

The primary dataset remains **all 100** while coverage is completed. Missing references leave primary task correctness `NOT_COMPUTED`; they do not silently shrink the primary set. A historical-origin analysis is optional descriptive work, not a required 99-case evaluation. The second-model efficiency experiment is an optional scope extension and requires a justified model choice and recorded design before it is activated; it does not reopen the settled S0/S1 main comparison.

## What a final freeze will mean

Once the evidence gates are satisfied, archive the exact artifacts and record a dated freeze manifest before viewing evaluated predictions. No change to settled design is expected merely to fill these gates. If a real incompatibility forces a change, record a versioned amendment and whether results had been seen. Until then, the current candidate config deliberately keeps held-out prediction disabled and no complete-task results are claimed.
