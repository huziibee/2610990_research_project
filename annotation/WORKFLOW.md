# Human semantic-reference workflow

All 100 annotation workspaces and blank drafts are prepared. Existing routes and strategy sequences are locked. The CLI never calls Gemini or any evaluated model. Prefer human-authored references; no protected case has been automatically interpreted for these drafts.

## View and prepare a case

From the project folder in PowerShell:

```powershell
py tools/annotate.py status
py tools/annotate.py show CA-0001
```

`show` displays the original utterance, scene, dialogue, capabilities, approved route, current reference and immutable history head. Edit the corresponding `annotation/workspace/drafts/CA-0001.json` file with your editor. Fill `reference`; preserve the envelope's case ID and `expected_head`. [REFERENCE_FORMAT.md](REFERENCE_FORMAT.md) documents every required field. Newly authored examples in `development/annotation_example_execute.json` and `development/annotation_example_clarify.json` illustrate the format without using a benchmark case.

Do not infer missing preferences. Ground goal/action/argument/constraint/dependency claims using exact quoted source spans. Quotes make review traceable, but a quote's existence does not prove it supports a claim. Explain critical unknowns; do not insert a guessed value to make an execute reference pass. If a source/approved-route tension cannot be resolved, record it as an annotation issue rather than changing the route or inventing evidence.

For clarify cases, provide a base CLARIFY task and explicitly simulated answer branches. Each branch has one to five question/answer turns and a complete expected final task. Each answer resolves its named critical field; answers and branch tasks remain hidden from inference until the frozen oracle receives a matching question. Do not put an expected task or extra preferences into the reply.

```powershell
py tools/annotate.py validate CA-0001 --file annotation/workspace/drafts/CA-0001.json
py tools/annotate.py submit CA-0001 --file annotation/workspace/drafts/CA-0001.json --actor YOUR_ACTUAL_PREPARER_ID
```

Use the same actual stable identity throughout. Actor names are self-attestations, not authenticated accounts; do not create aliases to simulate independence. If the reference was model-assisted, submit with `--provenance model_candidate`; it remains labelled through later human edits. Do not name a model as a human verifier.

## Verify, disagree and correct

A real independent human who did not contribute to preparation/adoption/corrections inspects both original context and reference. Run `show` to obtain the current `Head`, then replace the literal placeholders below:

```powershell
py tools/annotate.py verify CA-0001 --actor ACTUAL_INDEPENDENT_REVIEWER_ID --decision approve --head CURRENT_HEAD --notes-file review_notes.md
```

Use `--decision disagree` with concrete issue notes when necessary. Disagreement IDs appear in `show`/`history`. To correct a reference, create a new draft at the current head (existing files are never overwritten):

```powershell
py tools/annotate.py draft CA-0001 --output annotation/workspace/drafts/CA-0001_revision2.json
py tools/annotate.py revise CA-0001 --file annotation/workspace/drafts/CA-0001_revision2.json --actor YOUR_ACTUAL_PREPARER_ID
```

Only the reviewer who raised an issue may acknowledge its resolution using `resolve --disagreement-id ISSUE_HASH --actor REVIEWER_ID --head CURRENT_HEAD --notes-file resolution.md`. Every correction invalidates prior verification. Resolve all issues and independently verify the exact current revision again.

Model candidates require explicit human adoption (`adopt`, with actual identity, head and review notes) before independent verification. Human adoption does not remove the model-assistance provenance. Final approval uses `approve --actor ACTUAL_APPROVER_ID --head CURRENT_HEAD --notes-file approval.md` only after independent verification. The current implementation locks finally approved references; later corrections require a new versioned workspace preserving this history.

## History, exports and experiment release

```powershell
py tools/annotate.py history CA-0001 --json
py tools/annotate.py export --version review_snapshot_001
py tools/annotate.py export --version semantic_gold_v1 --require-complete
```

Every export directory is create-exclusive. Candidates and final approved references occupy different files; the manifest records coverage and hashes. Complete export fails until all 100 cases are independently verified and finally approved. Blank/unreviewed references never become gold. Maintain external backups/pins of export manifests: hash chains detect edited events but do not prevent an administrator rewriting or truncating a complete unanchored history.

The separate readiness checker additionally requires verified question-matching rules, subgroup eligibility, scoring tests, live synthetic S0/S1 evidence and a current final code/protocol freeze. No benchmark is run by annotation commands or the checker. Run `py tools/check_experiment_readiness.py` for the outstanding gates. See TODO.md for newly discovered engineering items.
