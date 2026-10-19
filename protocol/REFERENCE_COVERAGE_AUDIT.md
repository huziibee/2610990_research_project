# Reference coverage audit

Audit date: 2026-10-19. Read-only inspection of the current Data release
(version 1.0.1; 100 source records) and every recursively nested archive in its
preserved v6 archive. No dataset records, approvals, archives or snapshots were
changed. Inspection used file inventories, JSON key paths, nonempty-field
counts, CSV headers and documentation; cases were not used for prompt tuning.

## Completed references

`Data/data/author_approved_route_gold_100.jsonl` supplies all 100 author-approved
terminal routes and strategy sequences: 74 execute and 26 clarify. The author
review and explicit approval audit files corroborate that scope. These completed
approvals and dataset organisation are not being reopened.

`Data/data/gold_100_native_schema.jsonl` and
`Data/data/gold_100_with_author_review.jsonl` contain ambiguity types, capability
status, validity, strategy sequence, terminal strategy, field status and
provenance/review metadata. They do not contain complete intended-goal,
ordered-action, typed-argument, constraint/evidence task specifications or a set
of hypothetical clarification replies.

## Recursive archive evidence

The archive nesting is:

1. `Data/archive/Pilot_100_Author_Human_Adjudicated_Routes_v6.zip`
2. Inside v6: `archive/Pilot_100_Author_Human_Adjudication_v5.zip`
3. Inside v5: `archive/Pilot_100_Human_Adjudication_v4_UNAPPROVED.zip`
4. Inside v4: `archive/Pilot_99_Action_Readiness_Corrected_v3_AUTHOR_DIRECTED.zip`

Historical filenames containing `UNAPPROVED` describe archived review stages;
they do not undo the subsequent completed v6/current author route approvals.

| Location within the indicated archive | Observed coverage |
| --- | --- |
| v6 `data/pilot_100_author_route_gold_v6.jsonl` | 100 route/strategy references; no complete-task or reply schema. |
| v6 native/review gold; v5 schema-compatible/review gold; v4 proposed gold; v3 corrected/original gold | Routing, ambiguity, capability, validity and provenance schemas; no complete semantic task specifications or clarification-reply set. |
| v4 `proposals/ALL_100_REVIEW_QUEUE.jsonl` | 100 rows; `proposal` is null in 96 and an object in four. The four proposals have target/constraints/destination-status/temporal-constraint fields; three have a nonempty clarification question. These are partial historical proposals, not 100 full task references. |
| v5 `human_review/ALL_100_REVIEW_QUEUE_v5.jsonl` and `archive/ALL_100_REVIEW_QUEUE_v4_UNAPPROVED.jsonl` | Retain the historical proposal fields and review metadata; do not supply the missing full-case task/reply schema. |
| v3 `audit/THREE_CASES_FULL_CONTEXT_REVIEW_v3.json` | Three records with action, target, time, constraints, destination and proposed clarification questions, plus sidecar contrasts. Partial historical analysis, not full-set gold. |
| v3 `audit/CONSISTENCY_REVIEW_ALL_99.csv` | 99 rows. Columns: `record_id`, `original_route`, `proposed_route`, `destination_rule_category`, `rationale`, `source_evidence_fields`, `clarification_question_if_new`, `human_review_status`. Routing audit rather than complete task specifications. |

The v4 HTML review artifact and JSON proposal queues were also inventoried. No
separate complete-task gold or simulated-reply data artifact was found there.

## Mentioned sidecars are not supplied official gold

Inside v3, `FILTER_MANIFEST_v3.json` has a
`separate_structured_task_sidecars` field stating that these files had previously
been read:

- `pilot120_interpretation_key_candidate_v2.jsonl`
- `pilot120_provisional_interpretation_sidecar.jsonl`

The same field explicitly says **"not official gold"** and points to the
three-case review for source-derived evidence and conflicts. Neither sidecar is
included anywhere in the current Data directory or recursively nested archives.
Their names and partial historical contrasts cannot establish full task-reference
coverage or approval.

## Consequence for evaluation

Author-approved route scoring is supported. Complete-task semantic correctness,
field-level semantic grounding, question-quality scoring, dependency eligibility
and eventual task completion require additional frozen references/review rules.
No annotated hypothetical clarification-reply set was found, so simulated
multi-turn completion cannot yet be computed from the supplied package.

Any reference-preparation worksheet is a blank template for future work, not
completed annotation. Do not populate it by assumption, promote partial historical
proposals to official gold, or treat route accuracy as complete-task correctness.
This audit establishes what is supplied in this workspace; it makes no claim
about files that may exist outside the permitted workspace.
