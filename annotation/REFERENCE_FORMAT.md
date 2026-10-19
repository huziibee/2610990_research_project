# Semantic reference preparation format

These documents are hidden evaluator material. They must never be passed to
Gemini, used in prompt tuning, or used as development examples. Start with
human-authored references. A model candidate, if ever separately authorized,
must retain its origin through preparation, review, correction and export.

`research.reference_schema.reference_template(record_id, approved_route)`
creates an **unannotated draft**, with null semantic content. The original
worksheet remains a record of missing references. A draft cannot pass
`validate_reference(reference, model_input, approved_route)` until completed.

The validator takes the original approved routing row, including
`terminal_strategy` and `strategy_sequence`. Both approved values, and the case
identifier, must match exactly. This process does not reopen the 100 approvals.

## Required fields

| Field | Annotation |
| --- | --- |
| `record_id` | Existing case identifier |
| `author_approved_route` | Existing `execute` or `clarify` approval |
| `author_approved_strategy_sequence` | Existing approved sequence, unchanged |
| `reference_task` | Complete shared task schema described below |
| `evidence_claims` | Evidence mappings for the initial reference task |
| `acceptable_semantic_alternatives` | Complete alternative tasks, or `[]` |
| `critical_unknowns` | Objects with nonempty `field` and `reason`; `[]` if none |
| `hypothetical_answer_branches` | Explicit hypothetical branches, or `[]` for execute |
| `dialogue_relevant` | Human decision: boolean |
| `explicit_linked_dependencies` | Human decision: boolean |
| `verification_evidence` | Contextual support, ambiguity and subgroup eligibility review notes |
| `verified_capability_catalog` | Null, or context-supported capability catalog |

Preparation may retain worksheet metadata `reference_preparer`,
`independent_verifier`, and `semantic_reference_status`. These fields cannot
approve a reference: the workflow's append-only events determine who prepared,
independently verified, corrected and finally approved each revision. Leave
missing people as `[Waiting for ...]`. A reviewer must check the actual meaning
of all evidence, unresolved fields, alternatives, branch answers, and eligibility
notes. Never invent a missing preference, capability or fact.

## Shared task schema

`reference_task` uses `research.task_schema.TASK_FORMAT`: nonempty intended
goal, ordered actions with distinct IDs, capability IDs, typed arguments with
values and evidence sources, per-action constraints, unresolved fields,
dependencies, readiness and clarification question. Permitted argument types
are `object`, `location`, `time`, `string`, `number` and `boolean`.

Evidence strings inside typed arguments refer to `instruction`, `scene`,
`capabilities`, or `dialogue/N`. Dependencies use JSON pointers and relations
`same_value`, `before` or `depends_on`. A structurally valid task is insufficient
for correctness. The human verifier must also check completeness, action order,
constraints, capability meaning, and whether every execution-critical unknown
has been retained. An empty object is never a complete expected task.

For an execute case the reference must be `ACTION_READY`, have at least one
action, have no critical unknowns, and have no clarification question. A clarify
case requires a `CLARIFY` base task, nonempty clarification question, and critical
unknowns matching its unresolved critical fields.

## Evidence mappings

Each mapping is exactly:

```json
{"target":"/actions/0/arguments/object/value","source":"instruction","quote":"blue cup"}
```

`target` is a JSON pointer **relative to the associated task**, not the reference
document. `source` is `instruction`, `scene`, `capabilities`, or `dialogue/N`.
`quote` must be a nonempty exact substring of that text field. The quotation can
be longer than the annotated value to preserve relevant context. Every task
requires mappings for `/intended_goal`, each action's `/capability_id`, each
argument's `/value`, each constraint, and each whole dependency.

Exact quotes prevent nonexistent citations; they do not establish entailment.
For example, quoting a scene containing two shelves does not establish which
shelf the user chose. Absence cannot be proven by a quote: describe it in
`critical_unknowns` and have a verifier assess it against all four source fields.

Each semantic alternative requires a corresponding list in optional
`alternative_evidence_claims`. Alternatives must preserve the approved route
and the same critical unknown fields. A different permissible final task after
a supplied answer belongs in an explicit branch.

If `verified_capability_catalog` is supplied, it is a list of
`{"capability_id":"move","required_arguments":["object","destination"]}`.
Supply a matching `capability_catalog_evidence` list of
`{"capability_id":"move","quote":"...exact capability-context text..."}`.
The verifier must confirm required argument completeness; matching a substring
does not certify the catalog. External capability attestations cannot be
silently added to model-visible context.

## Hypothetical clarification branches

Every clarify reference needs at least one branch with these required fields
and, optionally, a `turns` path:

```json
{
  "branch_id": "destination-a",
  "question": "Where should the cup go?",
  "field": "destination",
  "answer": "shelf A",
  "simulated": true,
  "reference_task": "REPLACE WITH COMPLETE ACTION_READY TASK OBJECT",
  "evidence_claims": []
}
```

This illustrative fragment is deliberately incomplete and will not validate.
Branch IDs must be unique. `field` must name an initial critical unknown.
`question` is a human-approved acceptable question about that field. The answer
is an explicitly hypothetical user choice, never an observed conversation or a
claim that the original context contains that choice. Do not invent preferences
and present them as source facts. The verifier checks that the branch supplies
enough information for its complete final task and propagates dependent fields.

For branch task validation, only the answer text is appended to a copy of the
original dialogue. Argument evidence can cite its resulting `dialogue/N` index.
Branch evidence mappings may additionally use `source: "hypothetical_answer"`.
This evidence source is forbidden in initial tasks. Each branch requires a full
`ACTION_READY` expected task and its own evidence mappings. The complete hidden
branch task and its gold arguments must never be supplied as the reply.

The simulator must release **only the selected answer text** after a verified
question-to-field match. Ambiguous or multi-field questions require explicit
review or abstention, not automatic selection based on word overlap. Multiple
possible answer branches require a frozen selection rule before experiments;
the schema alone does not define that policy.

### Paths requiring multiple clarification turns

When a case needs two or more independent missing fields, add a `turns` list of
one to five objects, each exactly `{question, field, answer, simulated: true}`.
The first object must match the branch's top-level question, field, answer and
simulation flag. A legacy branch without `turns` remains a one-turn path.

For example, a hypothetical path can first ask which of two cups to move, then
ask which shelf to use. Each `field` must name a distinct initially critical
unknown. Repeated fields and newly invented unknowns are rejected by this
version: a policy supporting follow-up questions that revisit a field requires
an explicit future schema/protocol extension. A human must check that later
questions remain necessary after prior answers and dependency propagation.

Only after validating the whole path is its final expected `reference_task`
checked against an augmented context containing the path's reply texts in order.
The final expected task must be complete and `ACTION_READY`. This final-context
validation is an evaluator operation; it does not authorize sending future
answers or the final task to the evaluated model. During prediction the future
answers stay hidden until their corresponding eligible questions occur.

Multi-turn evidence mappings must identify the precise reply using
`hypothetical_answer/0`, `hypothetical_answer/1`, etc., or use the precise
appended `dialogue/N` location. Unindexed `hypothetical_answer` is permitted only
for one-turn paths; it is rejected for longer paths. Indexes are zero-based and
must exist. No hypothetical answer source, indexed or unindexed, is permitted
in an initial-task evidence mapping. The branch's final task has its own full
evidence mappings; intermediate task snapshots, question matching, alternative
path selection and dynamic dependency progression need the separately frozen
oracle/simulator policy before benchmark experiments.

## Limits of automated validation

Validation checks structure, route preservation, typed values, exact quote
locations, reference consistency, explicit simulation labels, and known
capability contradictions. It cannot prove complete semantic coverage,
interpret ambiguous language, certify preferences, or certify that an
alternative, dependency, subgroup label, or reply is justified. Independent
human verification and final approval remain necessary before gold export.

## Operational review identities and history limits

The local workflow records actor names supplied by the operator. It does not
authenticate accounts or establish that two different names represent different
people. Use a stable, agreed identity for each actual human; never enter a name
on someone's behalf or label an automated check as human verification. An
independent verifier must be a person who did not prepare, adopt, or correct the
reference. The ledger enforces this exclusion for recorded contributor names.

Hash-linked, exclusively created events preserve corrections and disagreements
and reject stale updates or edited events. Keep externally pinned backups of
the manifest, event heads and export manifests: local hashes alone cannot
detect an attacker rewriting the whole workspace or removing its entire tail.
Final approval seals that case; subsequent amendments require a new versioned
workspace. Exported candidates remain separate from final approved references,
and a persistent `model_assisted` flag keeps model origin visible after human
corrections.
