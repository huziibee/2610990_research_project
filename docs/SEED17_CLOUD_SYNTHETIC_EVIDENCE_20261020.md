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
