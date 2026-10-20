# Seed-17 synthetic cloud provider evidence — 20 October 2026

**Scope:** Development-only tests using invented SYNTHETIC-001 and invented semantic judge fixtures. No held-out inputs or hidden answers are present.

## Live Gemini API results from repository-secret GitHub Actions

- [Full-schema comparison 39403446814](https://github.com/huziibee/2610990_research_project/actions/runs/39403446814): original Gemma 4 S0 provider schema yielded a locally valid task. A shallower schema also returned a model response but failed strict local task validation. The full schema is not consistently unsupported.
- [First S0/S1 smoke 39403788190](https://github.com/huziibee/2610990_research_project/actions/runs/39403788190): fail-closed PAUSED on a transient provider error, no silent retries.
- [Second S0/S1 smoke 39404278317](https://github.com/huziibee/2610990_research_project/actions/runs/39404278317): S0.direct completed twice, S1.goal completed once, then S1.ground timed out. The coordinator paused; no complete two-answer trajectory was verified.
- [Initial judge calibration 39404046036](https://github.com/huziibee/2610990_research_project/actions/runs/39404046036): five invented fixtures were reported passed, but the initial report checked only overall verdict, not the stronger explicit abstention contract.
- Subsequent calibration code requires explicit abstain=true, all uncertain low-confidence fields, and unsupported_detail=uncertain on the source/reference-conflict fixture. This stricter version requires its own successful live calibration.

## Implementation and limitations

- The narrowly scoped empty-thought-marker fix accepts only demonstrably empty thought:true parts and keeps rejection of nonempty or extra payload, positive reasoning tokens and malformed reported token counts.
- The protected dataset, encryption key and author-reviewed reference contents were not exposed to cloud workflows. Protected benchmark executions and ablations have not occurred.
- No production switch from the original provider schema to the shallow diagnostic schema was made.
- The user's 43-file unpublished local handoff is newer than this development branch. Reconcile rather than overwrite it.
- Exact technical-freeze, complete live multi-turn evidence, strict judge calibration and documented execution authorization remain separate gates.
- Live-test workflows are manual-dispatch after the recorded runs, to avoid unintentional repeated model calls.

## Later current-code evidence

- [Strict judge calibration 39404914774](https://github.com/huziibee/2610990_research_project/actions/runs/39404914774): all five invented live fixtures passed after correcting the reporter to require explicit abstain=true and low-confidence uncertain field verdicts for inconsistent references. This is evidence for the isolated cloud-branch code fingerprint; it is not automatically a local frozen calibration.
- [One-call S1 ground timeout diagnostic 39405465447](https://github.com/huziibee/2610990_research_project/actions/runs/39405465447): even with a diagnostic-only 180-second timeout the provider returned HTTP 500 in 0.31 seconds. This test does not show a successful long-running grounding call and does not justify silently changing the experiment timeout.
- Other previously recorded S1.ground calls timed out at the configured 90-second limit. The mix of HTTP 500 and timeout responses remains a live provider reliability blocker; no root cause has been proven.

## Release boundary

The repository Actions secret allows live synthetic development tests. Neither the restored plaintext author references nor the local archive decryption key exist in these cloud jobs. There is no authorized, hash-bound protected release on this branch. No scientifically valid 100-case or 500-ablation benchmark was executed.

## Additional isolated S1 grounding comparisons (development only)

- [JSON-only vs original schema 39407840079](https://github.com/huziibee/2610990_research_project/actions/runs/39407840079): JSON-only transport returned in 6.85 seconds but failed strict local task validation. The original provider schema reached the configured 90-second timeout. No readiness gate was passed.
- [Intermediate schema 39408269986](https://github.com/huziibee/2610990_research_project/actions/runs/39408269986): simplifying deep argument schema still resulted in HTTP 500 in 0.31 seconds. This did not establish a working production schema alternative.
- Consequently the original provider schema and strict local validation remain unchanged. Provider-side intermittency is a genuine unresolved prelaunch blocker; do not claim a complete live S0/S1 multi-turn success.

## Newer local engineering handoff

The user provided a later, unpushed 43-source-file code handoff that locally passed 376 regression tests after narrow compatibility changes. That code includes the ablation runner, offline statistical analysis and version-2 technical freeze. The handoff was reconstructed and SHA-256 packaged outside this repository. It is not represented by GitHub PR #14, whose cloud tests use the older checked-in implementation. The precise local reference ledger, decrypted author release and generated current-code validation logs are not available in cloud Actions.
