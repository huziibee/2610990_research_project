# Seed-17 cloud integration and provider test evidence — 20 October 2026

## Integration state

All six newly pushed local engineering branches were merged into **main** via [PR #18](https://github.com/huziibee/2610990_research_project/pull/18) (merge commit `544c54d4a752fb6ad6836d1fbf1c0a65928fb643`). The consolidated agent branch passed **409/409 regression tests** ([run 39438843460](https://github.com/huziibee/2610990_research_project/actions/runs/39438843460)), and the merge's main-branch regression passed ([run 39439337495](https://github.com/huziibee/2610990_research_project/actions/runs/39439337495)).

Merged changes: explicit main authorization helper and negative tests, original-hash-preserving unsigned design lock rebind, stage-accurate shared grounding prompt check, strict invented smoke grounding validation, fail-closed transient handling of HTTP 502/504 and downstream tests. Earlier draft PRs #12–#16 are historical nested work, not extra independent patches to replay.

This document records live cloud tests made **after** the merge. These are invented-fixture engineering diagnostics only. **No held-out main or ablation predictions, no protected judging, and no technical freeze/launch signoff have occurred.** Local 100-case author-review and five-fixture judge calibration evidence are not in public GitHub Actions; their successful *local* checks were reported in `docs/SEED17_ENGINEERING_GATE_STATUS_20261020.md`. Do not claim they were independently reverified in this cloud environment.

## New live evidence

1. **Strict official current-code live smoke**: [run 39439748598](https://github.com/huziibee/2610990_research_project/actions/runs/39439748598), branch `research/seed17-cloud-current-smoke-20261020`, current main implementation plus a diagnostic-only workflow. Actual `S0.direct` call returned `HTTP_FAILURE` / HTTP 500 before any S1 call or clarification. The strict S0/S1 two-answer trajectory audit **FAILED**. Recorded full invented-only receipts as an Actions artifact. No retry and no protected cases.
2. **Provider mode matrix**: [run 39440155550](https://github.com/huziibee/2610990_research_project/actions/runs/39440155550), branch `research/seed17-provider-schema-matrix-20261020`. Four invented diagnostic probes returned: `goal_contract` -> HTTP 500 INTERNAL, `direct_initial_contract` -> HTTP 500 INTERNAL; `direct_initial_shallow_schema` -> local validation failure; `direct_json_mode_no_schema` -> inference failure. The workflow reports `success` because individual probes are intentionally `continue-on-error`; **all four actual probes failed**. The cloud 500 responses retained the already observed error body hash `8afb0f460c66c8c994af4793c44df522eb1a5d19c266051b83bc31ff0a64671f`. Reduced or omitted provider schema is NOT an acceptable confirmed solution; never change the registered task structure on these results.
3. **Current API responseFormat with unchanged full JSON schema**: [run 39441381207](https://github.com/huziibee/2610990_research_project/actions/runs/39441381207), branch `research/seed17-responseformat-diagnostic-20261020`. Three offline schema-equivalence unit tests passed. The diagnostic moved the existing complete nested JSON schema from `generationConfig.responseJsonSchema` to `generationConfig.responseFormat.text.schema`, with MIME `application/json`, without weakening any constraint. **Both actual live goal and direct requests returned HTTP 400 INVALID_ARGUMENT**, same 708-byte provider error body SHA `7be3c566d0ff2f9618c256da836b51f78762f944071519bee0757b25d0895038`. This field substitution is therefore **NOT** a verified Gemma API solution and was NOT merged into production. Google API docs describe `responseFormat` as a newer syntax, but acceptance for this actual model/payload has not been demonstrated.

For diagnostics: `research/gemini_backend.py` intentionally stores only bounded provider error metadata and a response-body hash, not arbitrary provider text or secrets. Classify HTTP 400 separately from HTTP 500, terminal finish reasons, malformed duplicate-key JSON and task validation failures. Do not assume rate limiting or token exhaustion from a 500 without matching evidence.

## Recommended immediate next steps

- In the original local trusted workspace, preserve all ignored evidence: `runs/readiness/agent_b_20261020_current/`, `runs/judgments/agent_d_current_live_20261020_02/`, and `runs/development/coordinator_live_20261020_final_02/`. Do not overwrite/redact raw local receipts or publish private references.
- For Google API's 400 error, use an **invented-only**, secret-redacted diagnostic to extract only safe structural `fieldViolations[].field`/error classification from the provider response if necessary. Avoid copying raw error text or API keys into public Actions logs. This may identify unsupported `responseFormat` fields on the specific hosted Gemma model.
- Investigate provider support/availability for `gemma-4-26b-a4b-it` and original `responseJsonSchema` on invented inputs using the existing journal and quota controls. The historical local minimal/JSON probes sometimes succeeded while full-schema calls also sometimes returned 500. Do not assume all provider failures share one cause.
- Change production prompts/schema/transport only with a versioned protocol amendment, full strict task validation, fresh current-code live evidence, updated tests and revalidated reference/prompt bindings. Do not silently reduce required fields or invent retry successes.
- After **verified** `S0/S1 CLARIFY -> CLARIFY -> ACTION_READY` live synthetic trajectories, resume the authoritative [end-to-end coding-agent runbook](SEED17_END_TO_END_CODING_AGENT_RUNBOOK_20261020.md): safe validation, readiness, unsigned freeze, actual explicit main authorization, sealed protected main, **separate explicit ablation authorization**, sealed 500-case ablations, isolated judging and real statistical analysis. No manuscript work.

## Current readiness

| Area | State |
|---|---|
| Merged local engineering | **COMPLETE**, regression pass |
| Original private reference review | **Reported validated locally** (100 refs, 26 branches; not publicly rechecked) |
| Frozen judge calibration | **Reported passed locally**; final-code/hash bindings still required |
| New cloud official live two-answer S0/S1 | **BLOCKED**, S0 HTTP 500 |
| New responseFormat transport | **NOT COMPATIBLE IN TESTED FORM**, HTTP 400 |
| New shallow or plain JSON schema | **NOT QUALIFIED**, validation/inference failure |
| Final unsigned technical freeze | **NOT PREPARED** |
| Protected 200-main / 500-ablation runs and final real results | **NOT COMPUTED** |

This is an evidence record, not an authorization or a claim that research outcomes have been measured.
