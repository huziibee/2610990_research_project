# Ablation implementation status (engineering, not evaluated results)

The candidate protocol predeclares five removal conditions. **The two input-context interventions, a two-call alternate first-stage
control and deterministic dependency-consistency guard removal are now implemented**, on synthetic examples. The latter is only a
*proxy* for removing an explicit goal intermediate, not proof of a pure
causal goal-first ablation.
Neither is activated in the protected benchmark runner.

| Removal | Implementation | Limitations |
|---|---|---|
| Scene context | \`research.ablations.masked_input(..., "scene")\` | Uses an explicit neutral WITHHELD sentinel because the canonical input contract requires a nonempty scene string. Evidence citing the marker is rejected after task validation. This is masking, not a zero-length field. |
| Dialogue | \`masked_input(..., "dialogue")\` | Replaces the dialogue list with an empty list; retained scene/instruction/capabilities are unchanged. |
| Goal-first | PARTIAL MATCHED CONTROL: `research.context_stage_design.predict_without_explicit_goal_stage` | Replaces the goal-object first stage with a context-summary first stage using the same two model calls and token/thinking caps; enforces a distinct JSON key. Generated summaries may implicitly contain goal information, and prompt content differs, so an output audit and interpretation caveats remain essential. |
| Structured grounding | PROMPT-ONLY PROXY: `predict_without_explicit_grounding_prompt` | Removes the targeted second-stage grounding instructions but retains the goal-first stage, JSON schema, typed arguments and structural/evidence validators. This is **not** a removal of structured representation. Full structural removal remains an open design gate requiring a fair canonicalization/evaluation strategy. |
| Dependency checking | PARTIAL POST-PROCESSOR: `predict_dependency_consistency_ablation` | Suppresses *only* same-value conflict and reverse-action-order checks; schema, relation types, argument grounding and JSON-pointer integrity remain required. Prompt-level dependency reasoning remains active. Contradictory tasks that now pass structural validation must be independently scored as semantic failures. |

The helper \`predict_context_ablation\` supports S0 and S1 only. It retains
the per-system budgets, explicit seeds, stage structure and ordinary schema
checks, and never imports hidden references. All passed-through inputs are
validated and defensively copied. A masked source cannot be cited as positive
evidence. The helper does **not** add schedules, unlock an evaluation gate,
modify the main S0/S1 protocol or report an experimental finding.

The dependency consistency ablation is a distinct post-processor intervention with the same model calls and prompts, not a claim that all dependency reasoning was removed. It must be evaluated with normal correctness judgments and operational error accounting.

The goal-representation comparator is intentionally separate from the locked S1 main system and from evaluated scheduling. Its synthetic tests check the two-stage context schema, independence from hidden answer objects, and matched maximum budgets. A non-goal schema cannot guarantee the model has not semantically inferred the goal in prose.

The prompt-only grounding comparator runs the same two stage labels and budget
caps as S1, with an unchanged final schema. It isolates a narrower question:
whether explicit grounding instructions contribute beyond the mandatory
structured-output interface. It cannot answer whether representation alone
improves task correctness.

All primary results remain NOT_COMPUTED. Any expansion of the five-ablation
plan, activation of ablations on held-out cases, or interpretation of
mechanistic causal effects requires a versioned freeze/amendment, appropriate
eligibility denominators, and independently scored results.
