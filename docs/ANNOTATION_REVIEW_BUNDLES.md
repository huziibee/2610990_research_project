# Annotation review bundle preparation

This is a **post-annotation tool**, not a replacement for human semantic
annotation. The complete 100-case semantic gold set does not yet exist.
Do not generate benchmark references from model guesses or route labels.

Once the existing annotation ledger reaches 100 finally approved cases,
produce an exclusive versioned export using:

```powershell
py tools/annotate.py status
py tools/annotate.py export --version semantic_gold_v1 --require-complete
py tools/prepare_annotation_review.py --export-version semantic_gold_v1 --bundle-id review_001 --preview
py tools/prepare_annotation_review.py --export-version semantic_gold_v1 --bundle-id review_001
```

The command confirms source and derived data hashes; exact export digest,
100-case ordering, immutable ledger heads, complete human approvals and
the fixed 74/26 route distribution. A preview never creates files.
The bundle is written under ignored `runs/annotation_review/review_001/`:
`reviewed_coverage_CANDIDATE.json`, `clarification_matching_CANDIDATE.json`
and `summary.json`. An existing output directory is never overwritten.

**Candidates are deliberately marked unverified.** The program copies
reviewed question text and branch identifiers, but never writes hypothetical
answers, expected tasks, model predictions, or credentials. It creates only
canonical approved question variants; any alternate paraphrases must be
explicitly reviewed and added by a human. Independent reviewers must confirm
eligibility, semantics and question matching. A separate reviewed, hashed
manifest is required before the experiment readiness gate can pass.

The generated coverage and matching candidates must NOT be renamed
to production readiness artifacts or treated as evidence of independent
verification. The tool never calls Gemini and never releases held-out
predictions. See `protocol/FREEZE_STATUS.md` for the remaining gates.

Test with:

```powershell
py -m unittest discover -s tests -v
```
