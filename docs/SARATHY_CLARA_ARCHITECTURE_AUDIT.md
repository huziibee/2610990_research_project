# Sarathy and CLARA adaptation — architecture audit and implementation

**Scope:** This is an evaluator-side extension of the existing Goal-First task representation. No changes to the model output JSON, prompts, S0/S1/S2 control flow, freeze schedule, dataset, routes, primary endpoint, manuscript or results renderer. These diagnostics are **not empirical results**. Reviewed human references are still required.

## 1. Audit of original code before new work

| File | Already implemented | Missing for the requested literature integration |
|---|---|---|
| `research/task_schema.py` | Goal, ordered typed actions, per-argument source pointers, constraints, unresolved critical fields, `same_value` equality, `before` ascending-index check, `depends_on` endpoint existence, permitted-capability IDs and required catalog arguments; rejects malformed ACTION_READY/CLARIFY | No explicit SPC referent identity; no graph comparison to independently reviewed semantic reference; no relational cycle or duplicate diagnostics; no end-to-end semantic correctness guarantee. `depends_on` checks endpoint existence, not whether a task is semantically feasible. |
| `research/systems.py` | S0 direct task, S1 goal then grounded task, optional S2 independent interpretation; catalog SHA tied to visible capabilities; per-turn answer callback; append question/answer to dialogue and generate a fresh validated task, up to five turns | No posthoc test that a question addressed the approved missing field, kept established bindings, or detected contradictions with earlier answers. Catalog `verified_by` is an attestation string, not authenticated identity. |
| `research/reference_schema.py` | Exact quote evidence claims, route lock, accepted alternative tasks, critical unknowns, simulated clarification branches, explicit subgroup eligibility and catalog evidence | Exact substring does not prove contextual meaning; a complete/approved reference still requires real independent human review. |
| `research/clarification_matching.py` | Frozen canonical question normalization, approved variant matching, sequential release of simulated replies, no future answer disclosure | It can refuse unapproved paraphrases; question relevance/answer entailment are not established by exact matching. |
| Existing tests | Shape, evidence-pointer rejection, capability IDs, matched budgets, simulated answers, branch constraints, ledger gates | Missing separate relational graph diagnostics, human-attested capability-vs-missing-detail diagnostics and cross-turn continuity audit. |

## 2. Sarathy et al. — exact source and adaptation

V. Sarathy, M. Fawn, M. McWilliams, M. Scheutz and B. Oosterveld, *On Evaluating LLM Integration into Robotic Architectures*, ACM Transactions on Intelligent Systems and Technology, 2025, DOI [10.1145/3754340](https://doi.org/10.1145/3754340). Source: `Evaluating LLM integration.pdf`.

- **Paper, §2.1, pp. 3–4:** Information structure separates communicative intent, **core propositional content (CPC)** and supplemental/given content (**SPC**) used for reference resolution. The paper uses lifted symbolic actions and entity descriptors tied to robot functions.
- **Paper, §3.3, pp. 7–8:** Evaluates correct intent, CPC name, SPC structure, variable bindings and graph structure, including isomorphism/matching-based criteria.

**What we adapted in `research/semantic_relations.py`:**
1. Project the existing `intended_goal` and ordered `actions` into a *CPC-inspired* graph, without rewriting the model output schema.
2. Project typed action arguments into *SPC-inspired* reference links. A separate `referent_bindings` mapping permits **externally reviewed** entity IDs; otherwise binding is a literal typed-value placeholder. Do not infer synonyms, deixis or physical identity automatically.
3. Compare goal literals, action/argument/constraint structure, binding identities, and explicit dependency edges against independently supplied reference projections. Mapping between action indices must be provided explicitly for non-identity alignment.
4. Flag missing/extra dependencies, duplicate relationships, referent-binding conflicts and directed relationship cycles as deterministic *diagnostics*. These are not a substitute for ground-truth semantic judgments.

**What we did NOT implement:** Sarathy's DIARC architecture, speech-act parser, cognitive-status/Givenness markers, lambda calculus or lifted predicates, a symbolic perception system, automatic graph isomorphism search, automatic anaphora resolution, or its precise reported metrics. Literal goal equality is **not** synonymous with communicative-intent correctness. Any candidate mapping requires independent human semantic adjudication.

## 3. CLARA — exact source and adaptation

J. Park et al., *CLARA: Classifying and Disambiguating User Commands for Reliable Interactive Robotic Agents*, IEEE Robotics and Automation Letters, accepted Nov. 2023; source `Clara.pdf`. Section III.C discusses capability-aware feasibility checks, explanations/questions for ambiguity and restarting the uncertainty assessment after a reply.

**What we adapted in `research/capability_diagnostics.py`:**
1. Keep two evaluator diagnostics separate: an execution-critical **information gap** and a robot **capability limitation**. The former is explicitly declared in existing `unresolved` fields, not inferred from task risk.
2. Bind capability-catalog identifiers and required-argument names to the **visible capability description** using the existing catalog implementation and its SHA-256; require a distinct human preparer/verifier attestation and exact contextual quotes.
3. With no reviewed catalog, status is **UNKNOWN_NO_VERIFIED_CATALOG**, never silently classified as infeasible.
4. Label contextually resolved information only as an **evidence-backed reviewer candidate**. An exact source substring is mechanically checkable, but may be pragmatically inadequate.
5. Preserve the existing ACTION_READY/CLARIFY task contract. Unsupported capability is an **evaluator diagnostic**, not a new terminal route.

**What we adapted in `research/clarification_continuity.py`:**
1. Replay the explicitly approved synthetic question/answer steps into temporary dialogue copies.
2. Revalidate each trajectory task using the unchanged task schema (and optionally existing verified catalog).
3. Detect an answer targeting the wrong unresolved field, an unanswered critical field, a discarded previously bound argument, a contradictory argument change, a reopened resolved field, duplicate fields, and mismatched questions/answers.
4. Allow corrections only when an explicit per-turn action/argument slot exception is supplied; a granted exception is **not** proof the corrected value is semantically justified.
5. Return violation categories, not verdicts about human pragmatic appropriateness or ground-truth correctness.

**What we did NOT implement:** CLARA's uncertainty sampling, entropy/CDF thresholds, few-shot prompts, model-based feasibility inference, separate infeasible terminal route, physical task feasibility, free-form question generation, or reported SaGC result reproduction. Current infrastructure remains text-to-text and does not execute robot actions.

## 4. Deterministic versus semantic evidence

All added functions deliberately return `semantic_correctness: NOT_COMPUTED`. Reference-ID attestations and reviewer names are **self-attested**, not cryptographically authenticated identities. Diagnostics must not be relabelled as `independently_verified` or used to authorize held-out predictions. Frozen S0/S1 predictions, semantic scoring and primary endpoint are unchanged.

These helpers run **after** predictions or on newly authored synthetic cases in evaluator-only tools; they must not enter model-visible context, hidden answer-oracle callback content, model prompts or the JSON response schema.

## 5. Synthetic regression suite and remaining gates

New suites:
- `tests/test_semantic_relations.py`: CPC/SPC projections, referent aliases, invalid pointers, action alignment, missing/duplicate/cyclic dependencies, invalid or inconsistent graph bindings.
- `tests/test_capability_diagnostics.py`: supported/unknown/unsupported capabilities, required slots, forged source quotes, stale hashes, self-review, conflicting unknown and contextual resolution.
- `tests/test_clarification_continuity.py`: one- and two-turn updates, answer-target consistency, preservation, contradictions, evidence pointers, allowed corrections, no input mutation and turn limits.

Run on the new branch:

```powershell
py -m unittest tests.test_semantic_relations tests.test_capability_diagnostics tests.test_clarification_continuity -v
py -m unittest discover -s tests -v
```

Remaining before scientific use: actual independent verification of 100 task references and 26 branch tasks; genuine human referent alignment and catalog authentication; test-driven correction of any full-suite failures; live synthetic Gemini smoke evidence; final signed/fingerprinted freeze. These modules do not bypass any requirement.
