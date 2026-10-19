# Ablation implementation status (engineering, not evaluated results)

The candidate protocol predeclares five removal conditions. **The two input-context interventions and a two-call alternate first-stage
control are now implemented**, on synthetic examples. The latter is only a
*proxy* for removing an explicit goal intermediate, not proof of a pure
causal goal-first ablation.
Neither is activated in the protected benchmark runner.

| Removal | Implementation | Limitations |
|---|---|---|
| Scene context | \`research.ablations.masked_input(..., "scene")\` | Uses an explicit neutral WITHHELD sentinel because the canonical input contract requires a nonempty scene string. Evidence citing the marker is rejected after task validation. This is masking, not a zero-length field. |
| Dialogue | \`masked_input(..., "dialogue")\` | Replaces the dialogue list with an empty list; retained scene/instruction/capabilities are unchanged. |
| Goal-first | PARTIAL MATCHED CONTROL: `research.context_stage_design.predict_without_explicit_goal_stage` | Replaces the goal-object first stage with a context-summary first stage using the same two model calls and token/thinking caps; enforces a distinct JSON key. Generated summaries may implicitly contain goal information, and prompt content differs, so an output audit and interpretation caveats remain essential. |
| Structured grounding | NOT IMPLEMENTED | Removing only the prompt instruction is insufficient when JSON schema/validation still impose a structured representation; need an operationally distinct, predeclared comparator. |
| Dependency checking | NOT IMPLEMENTED | Removing checks requires a versioned validator policy while preserving fair reporting of invalid dependency outputs as errors, not silently crediting them. |

The helper \`predict_context_ablation\` supports S0 and S1 only. It retains
the per-system budgets, explicit seeds, stage structure and ordinary schema
checks, and never imports hidden references. All passed-through inputs are
validated and defensively copied. A masked source cannot be cited as positive
evidence. The helper does **not** add schedules, unlock an evaluation gate,
modify the main S0/S1 protocol or report an experimental finding.

The goal-representation comparator is intentionally separate from the locked S1 main system and from evaluated scheduling. Its synthetic tests check the two-stage context schema, independence from hidden answer objects, and matched maximum budgets. A non-goal schema cannot guarantee the model has not semantically inferred the goal in prose.

All primary results remain NOT_COMPUTED. Any expansion of the five-ablation
plan, activation of ablations on held-out cases, or interpretation of
mechanistic causal effects requires a versioned freeze/amendment, appropriate
eligibility denominators, and independently scored results.
