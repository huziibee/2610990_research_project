# Independent semantic judgment preparation (post-run evaluator only)

**Status: engineering prototype, NOT a completed semantic evaluation.**
This module is explicitly outside the model-inference code path.

## Purpose

`research.blinded_judgments` prepares semantic judging sheets after predictions
have been **immutably sealed** and the complete 100-case reference export,
26 clarification branches and authorized source snapshots have been
**independently approved**.

It accepts versioned expected branch tasks, the four visible source fields,
and saved model predictions. The researcher holds a private HMAC blinding
secret, at least 32 bytes. A system-blinded reviewer packet shows the
original context, the expected completed task, the predicted task and blank
ratings on these exact seven dimensions:

- `goal`, `actions`, `order`, `arguments`, `constraints`,
  `dependencies`, `evidence_supported`.
- Independently record `unsupported_detail` and
  `initial_clarification_appropriate` (the latter at turn zero only).

The separate **private linkage** maps randomized assignment IDs to
the original case, seed, branch and turn, plus hashes of the prediction
and reference. **Never include the private linkage in a reviewer packet, model
request or publicly released dataset.** The review packet deliberately omits
system and seed labels, but masking metadata is not a guarantee that
a reviewer cannot recognize a system from its output style.

## Required human workflow

1. Independently authenticate a complete sealed prediction archive and a
   final approved reference export. Hash checking in this module is not a
   substitute for the existing experiment integrity/readiness gates.
2. Prepare blinded packets from the authenticated inputs and keep the HMAC
   secret plus linkage map private to the evaluation coordinator.
3. Have **two real different human reviewers** each read the relevant source,
   reference task and predicted output; submit complete boolean dimensions
   and substantive notes independently, without seeing the other's ratings.
4. `combine_independent_reviews` detects disagreements and reports
   `NEEDS_INDEPENDENT_ADJUDICATION` rather than guessing a majority answer.
5. Have a real third reviewer resolve disagreements through a separately
   documented and independently authenticated adjudication protocol.
   Keep original reviews and resolution evidence.
6. Externally authenticate reviewer identities and snapshot approval,
   then explicitly release the final immutable judgment export into the
   pre-existing `research.semantic_metrics.score_semantics` evaluator.

**Deliberate fail-closed boundary:** Even when two submitted reviewer
identities differ and their selections agree, the helper labels outputs
`agreement_candidate_unverified`, with
`reviewer_identities_authenticated=false` and
`final_score_release_authorized=false`. These candidates MUST NOT be
silently relabelled as verified. The existing semantic scorer rejects them.
No actual human review occurred by writing or running this module.

Operational failures have no invented field-level human judgments and remain
denominator failures in the final evaluator.

## Tests

```powershell
py -m unittest tests.test_blinded_judgments -v
py -m unittest discover -s tests -v
```

All existing 100 held-out records, route decisions, prompt settings and Gemini
calls remain unchanged. The final trajectory runner, reviewer identity
authentication, external release approval and score-report export remain
outstanding and must be completed before this is a production judging process.
