# Local annotation workbench

This is a **human-facing, evaluator-only** browser interface for the already
frozen 100 input records. It never calls Gemini, changes an approved route,
creates human identities, infers an expected task, or marks anything as gold.

## Start

From the project root:

~~~powershell
py tools/serve_annotations.py
~~~

Open **http://127.0.0.1:8765/** on the same Windows machine. Stop with
Ctrl+C. The service binds only to 127.0.0.1, rejects foreign Host/Origin values,
uses a per-process CSRF token, escapes input text, returns no-store headers and
does not embed third-party scripts. It should not be exposed through a reverse
proxy or a public tunnel. Human identity fields are self-attested; this is not
an authentication system.

Click a case to see the exact original instruction, scene, dialogue, and
capability description next to a JSON reference form. The approved route and
strategy sequence are locked. Empty semantic fields are **placeholders**,
not an auto-generated interpretation. No example source case is loaded into
Gemini for draft preparation.

Use **Save draft locally** to preserve unfinished content without changing
the annotation ledger. Saved drafts live in
\`annotation/workspace/drafts/CA-XXXX.json\`; protect these files as
evaluation-only materials. **Validate structure** checks task/reference schema
and source quotation existence; passing validation does not prove meaning or
human semantic correctness. **Submit to review ledger** asks for the actual
preparer identity and correct human/model-assisted provenance; it runs the
existing validation and creates a hash-linked *candidate* event, not an
approval.

The same page also supports **Adopt model candidate**, **Verify reference**,
**Record disagreement**, and **Final approval**. These are explicit human
actions requiring a real actor name and substantive notes. Review actions
apply only to the *exact current ledger reference*; they reject unsaved
edits and stale heads. The ledger rejects self-verification, verification
without explicit adoption of model-assisted candidates, final approval
before independent verification, and approval over unresolved
disagreements. Disagreement acknowledgment is deliberately left to the
existing reviewer-specific CLI workflow.

After a submission, the saved draft has an old history head. The button
**Load latest ledger revision** displays a new envelope bound to the current
head without destroying the saved draft. Correct references by revising them,
then use the established independent human verification and final approval
commands in \`annotation/WORKFLOW.md\`.

Clarification cases require explicit critical unknowns, realistic
hypothetical answer branches (maximum five turns), answer-grounded final
tasks, and independent review. **Never use this interface to fabricate
simulated answers or to auto-approve model candidates.**

## Verification

~~~powershell
py -m unittest discover -s tests -v
py tools/annotation_triage.py --summary-only
py tools/check_experiment_readiness.py
~~~

The readiness checker is expected to report NOT READY while human task
references and live Gemini evidence are incomplete. The CI job verifies that
triage never authorizes evaluation, even when software tests pass.

## Boundaries

- The workbench reads only the pinned annotation ledger and its local drafts.
- A saved draft and a structurally valid candidate are not human gold.
- Model predictions never import the annotation modules.
- Human independent verification and final approval remain separate steps.
- No hidden task answers, simulated replies, or keys are transmitted to Gemini.
- No held-out results are produced by the server.
