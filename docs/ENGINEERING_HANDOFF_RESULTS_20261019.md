# Engineering handoff — results, CI and evaluation audits

Branch: **research/results-validation-20261019** (based on the reconciled evaluation and paper-results work). Nothing has been merged to main or evaluated against protected commands in this workstream.

## Completed engineering

1. **Preserved original dataset freeze.** Six text files and the Data/MANIFEST.json package manifest had lost their original CRLF bytes in Git. Restored the exact content bytes and checked original SHA-256 hashes. Did not amend the pinned protocol/DATA_FREEZE_20261019.json, derived dataset manifest, source records or original approval labels.
2. **Portable CI triage.** GitHub Actions creates a separate Linux-pinned temporary annotation workspace; it does not rewrite or replay the human's Windows-pinned review history. The CI workspace has zero human-approved semantic references by design.
3. **Statistical paper output.** The manuscript renderer now reports S1 minus S0 and each ablation minus S1 via 10,000 resamples of paired cases, averaging seeds within each case. A new paired_effects_table.tex and summary JSON show signed percentage-point effects, 95% intervals and subgroup case counts.
4. **Verified provenance input.** Real renderer CLI use now requires a matching, actual review manifest file via --review-manifest; SHA-256 match does not replace external human identity authentication.
5. **Route diagnostic.** A sealed, completed main-run archive can be compared against the author-approved route labels to make a 2x3 execute/clarify/error confusion matrix. Errors stay in the denominator. This is initial routing, not semantic task accuracy.
6. **Cross-run pairing audit.** A distinct read-only audit validates complete 1000-row S0/S1 and 2500-row ablation archives, preserving exact case/seed pairing and settings. It does not authorize inference.
7. **Fake-data figure demo.** A standalone script creates marked DEMO LaTeX fragments from invented SYNTHETIC cases, not publishable measurements.

## Run now — Windows PowerShell

Use a separate Git worktree so you do not disturb the other chat's annotation work.

    git fetch origin
    git worktree add ..\research-results-check origin/research/results-validation-20261019
    cd ..\research-results-check

    py Data/verify_package.py
    py -m unittest discover -s tests -v
    py tools/run_experiment.py --phase ablations
    py tools/demo_paper_results.py --output runs/synthetic_paper_demo_001

The demo's DEMO_*.tex files, and every supplied numerical value, are explicitly synthetic. The folder must not already exist. The default committed annotation workspace contains machine-specific absolute source pins; do not edit those to suppress hash checks.

## Future commands only after approved semantic gold and complete freeze

    py tools/report_efficiency.py runs/evaluation/MAIN_RUN
    py tools/audit_run_pairing.py --main-run runs/evaluation/MAIN_RUN --ablation-run runs/evaluation/ABLATION_RUN --output runs/reports/paired_audit.json
    py tools/report_route_matrix.py --run-dir runs/evaluation/MAIN_RUN --output runs/reports/route_matrix_001
    py tools/render_paper_results.py --scored-bundle runs/scoring/verified_paper_bundle.json --review-manifest runs/scoring/verified_review_release_manifest.json --output runs/paper_candidate_001

Those paths identify FUTURE artifacts, not existing results. They cannot create or authorize protected benchmark runs. A published score requires a verified human judgment release, not the presence of a plausible-looking file with a hash.

## Scientific work still open

- Human annotation and independent review of all 100 complete tasks, including the 26 clarify cases and their human-approved simulated answer branches.
- Verified capability catalogs and dialogue/dependency eligible sets; question-to-answer oracle and score/reviewer workflow.
- Successful live non-evaluation Gemini checks by the user, then explicit final protocol and ablation freeze.
- Main, ablation and up-to-five-turn clarification evaluations, after independent release approval.
- Converting real, independently reviewed scored case/run data to the final 3500-row presentation bundle.
- Audit whether prompt-only structured-grounding and checker-only dependency controls support the exact mechanistic claims proposed in the paper.
- Compile and proofread final column-fit LaTeX and limitations, after empirical scoring.

Held-out predictions remain disabled and primary complete-task semantic correctness remains NOT_COMPUTED.
