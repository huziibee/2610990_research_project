# Author-led model-assisted semantic review: 100 protected cases

**Implementation:** \`tools/review_author_batch.py\` on branch \`research/literature-evaluation-20261019\`.

This is a **separately labelled one-human, model-assisted author-approval track**. It does not impersonate or manufacture another person. It never describes itself as independently human verified and does **not** silently pass the pre-existing two-human verification gate. The supervisor-approved protocol variant, if adopted, must be clearly documented in the manuscript rather than relabelling this as an independently reviewed gold release. Earlier claims of two-model adjudication require their actual saved evidence (model identities, blinded outputs, timestamps, disagreements and resolutions) to be added before that history can be asserted as verified.

## What is ready before any human click

The frozen case cohort, 74/26 routes and existing 100 model-assisted draft proposals are separate from model inference. Import the **private ZIP** using its included \`install_candidates.py\` into your local, Git-ignored workspace. Do not commit the ZIP or reference drafts to GitHub: these contain protected hidden answers.

PowerShell from the updated research branch:

~~~powershell
git fetch origin
git switch --detach origin/research/literature-evaluation-20261019
py Data/verify_package.py
py tools/annotate.py --workspace runs/human_review_20261019 init
py runs/model_assisted_candidate_100/install_candidates.py --workspace runs/human_review_20261019 --install
py tools/review_author_batch.py --workspace runs/human_review_20261019 --check
~~~

If installed already, do not rerun the ZIP importer; it intentionally refuses to replace human-edited files. Open two separate PowerShell terminals and run:

~~~powershell
py tools/serve_annotations.py --workspace runs/human_review_20261019
py tools/review_author_batch.py --workspace runs/human_review_20261019
~~~

Read the proposals at **http://127.0.0.1:8766/**. Open any case at the workbench **http://127.0.0.1:8765/** to correct and save the current **unsubmitted** local draft. Refresh the review portal after corrections. This portal contains no AI inference, external scripts or upload requests. Its review confirmation is a real local POST, not a fake UI action.

## One actual human final review

Once the reviewer has inspected **all 100 source→reference** decisions, including **all 26 simulated answer paths**, enter their actual identity, substantive notes and tick the explicit reviewed-all attestation. Press **I have reviewed all 100 — record my approval**. This is the only human final-confirmation step. The workflow:

1. Revalidates **every** source-pinned draft, exact case ID, route, strategy, evidence-quotation existence, action schema and clarification branch.
2. Fails before any submission if a reference is malformed, stale, or disagrees with already submitted ledger content. The system cannot prove that a passage semantically entails the claim; the human reviewer is responsible.
3. Records the entire cohort as actual **model-candidate** submissions, then **human adoption** by the entered person in the existing hash-chained annotation ledger. Interruptions can be resumed if no conflicting edits occurred. It never calls \`verify\` with an invented second person.
4. Creates \`runs/human_review_20261019/author_review_export/author_reviewed_references_100.jsonl\` and \`AUTHOR_REVIEW_RECEIPT.json\` using exclusive filenames, saved reviewer identity/notes, the 100 immutable reference/history hashes and exact source manifest digest.
5. Retains independent verification status \`false\`, source origin and original frozen routing metadata. No Gemini predictions or measured results are generated.

**Status after sign-off:** \`AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED\`. This is a human-author-approved reference set with explicitly model-assisted drafting. It is not a fake \`FINAL_APPROVED\` export from the old independent-verifier workflow.

## What sign-off does NOT do

- It does not change the historic origin of CA-0100 (author-included synthetic-origin source case). All 100 remain members of the frozen evaluation cohort, but provenance stays truthful.
- It does not supply proof that two specific external models independently reviewed or adjudicated every reference. Attach their real logs separately if they exist.
- It does not update model prompts, alter protected cases, modify the primary endpoint, invent independent output judgments, or unlock the frozen held-out run gate. The existing \`research.evaluation_gate\` still enforces its separately frozen requirements; a supervisor-authorized alternative needs an explicit versioned protocol amendment.
- It does not merge this branch to \`main\` until the actual human reports their completed review and explicitly confirms merging. It does not upload private reference content to GitHub.

## Integrity and backups

The reviewer must back up the private \`runs/human_review_20261019\` directory, including event history and approval receipt, to an access-controlled location. \`runs/\` is Git-ignored. The signed-off release has integrity hashes but no authenticated digital signature or external timestamp authority. Do not erase corrections or overwrite an existing receipt; create a new versioned release for changes.
