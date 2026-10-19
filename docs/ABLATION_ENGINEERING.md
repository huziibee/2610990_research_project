# S1 ablation engineering: isolated pre-evaluation component

**Status:** implementation plus synthetic tests committed on \`research/ablation-engineering-20261019\`; NOT protocol-frozen and NOT an evaluated result. Do not run the 100 protected examples through this module until the repository's independent readiness and semantic-gold gates are satisfied.

The helper \`research/ablations.py\` accepts an already constructed backend and a caller-provided validated input. It does not load the dataset, inspect references, set any protocol flag, or call a hosted API on its own. It preserves the input and produces the shared task output shape. Run its local synthetic checks via:

\`\`\`powershell
py -m unittest tests.test_ablations -v
py -m unittest discover -s tests -v
\`\`\`

| Removal name | Engineered change | Scientific interpretation |
| --- | --- | --- |
| goal_first | Reuse S0 direct one-call generation | This is **identical to the existing S0 control**, not an extra independent S1 ablation. Input-call budget differs; report it as S0, not as a new S1-only experiment. |
| structured_grounding | Retain the S1 goal call but remove the explicit argument-by-argument grounding directive in the second call; the common schema and structural checks remain | A prompt-component intervention; the final output schema is still shared. |
| scene | Replace scene description with a conspicuous withholding sentinel in both S1 calls | Information removal, *not* an equal-evidence comparison. The sentinel never claims to represent a real scene. |
| dependency_checking | Keep the two ordinary S1 generations and all nondependency validators; skip deterministic checks for dependency pointer/value/order consistency | A validator ablation, *not* evidence that the model ceased to reason about dependencies. Its output is intentionally not certified valid under the normal dependency validator. |
| dialogue | Pass an empty dialogue list to both S1 stages | Information removal. Interpret primarily on independently verified dialogue-relevant cases. |

**Important implementation boundary:** \`predict_ablation\` is an engineering helper, not a scheduled experiment runner. It has no independent release flag and MUST NOT be connected to protected data until the future evaluation runner enforces the same fail-closed readiness checks, locked order, immutable prediction logs, model-version controls, run failures, and cost accounting as the main S0/S1 runner. It must not be used to tune on held-out examples.

**Remaining work before checking off experimental ablations:**
1. Run the synthetic tests and independent code review on the new branch.
2. Decide with scientific review whether the validator-only dependency removal and prompt-only structured-grounding removal are the actual intended interventions. If not, amend the design *before* looking at predictions.
3. Add guarded scheduling, model usage logs, and frozen intervention IDs/hashes through a separate evaluator after verified references and completed protocol freeze.
4. Run the prespecified cases/seeds, including appropriate dialogue/dependency subgroups; score against independently approved semantic references.

**No results or main evaluation progress are claimed.** Existing main \`protocol/gemini_protocol_v1.json\` stays at \`NOT_FROZEN\` with held-out predictions disabled.
