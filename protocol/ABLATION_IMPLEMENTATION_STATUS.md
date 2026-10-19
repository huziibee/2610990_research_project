# Ablation implementation status (engineering, not evaluated results)

The candidate protocol predeclares five removal conditions. **Only the two
input-context interventions have been implemented**, on synthetic examples.
Neither is activated in the protected benchmark runner.

| Removal | Implementation | Limitations |
|---|---|---|
| Scene context | \`research.ablations.masked_input(..., "scene")\` | Uses an explicit neutral WITHHELD sentinel because the canonical input contract requires a nonempty scene string. Evidence citing the marker is rejected after task validation. This is masking, not a zero-length field. |
| Dialogue | \`masked_input(..., "dialogue")\` | Replaces the dialogue list with an empty list; retained scene/instruction/capabilities are unchanged. |
| Goal-first | NOT IMPLEMENTED | Simply substituting S0 is confounded by call count and prompt budgets. A genuine removal must preserve an appropriate two-call control or explicitly disclose budget changes. |
| Structured grounding | NOT IMPLEMENTED | Removing only the prompt instruction is insufficient when JSON schema/validation still impose a structured representation; need an operationally distinct, predeclared comparator. |
| Dependency checking | NOT IMPLEMENTED | Removing checks requires a versioned validator policy while preserving fair reporting of invalid dependency outputs as errors, not silently crediting them. |

The helper \`predict_context_ablation\` supports S0 and S1 only. It retains
the per-system budgets, explicit seeds, stage structure and ordinary schema
checks, and never imports hidden references. All passed-through inputs are
validated and defensively copied. A masked source cannot be cited as positive
evidence. The helper does **not** add schedules, unlock an evaluation gate,
modify the main S0/S1 protocol or report an experimental finding.

All primary results remain NOT_COMPUTED. Any expansion of the five-ablation
plan, activation of ablations on held-out cases, or interpretation of
mechanistic causal effects requires a versioned freeze/amendment, appropriate
eligibility denominators, and independently scored results.
