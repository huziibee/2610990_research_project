# Seed-17 engineering gate status, 20 October 2026

This is an engineering continuation record. The protected experiment and real
statistical results remain **NOT COMPUTED**. No paper files were changed.

## Checkout and integrated corrections

Fetched and fast-forward checked `main`: `814e50f118271fe360478d21fedac6432813be59`.
The dedicated local integration branch is `research/seed17-completion-20261020`.
The integration includes:

- HTTP 502/504 now pause execution after a durable failure receipt, alongside
  the existing transient classes. Explicit resume retains failed outcomes and
  does not resend their requests.
- `tools/authorize_seed17_main.py` validates an existing, actual hash-bound
  authorization and writes an exclusive separate bundle. It never creates
  consent or modifies the unsigned release. Synthetic negative tests cover
  mismatched hashes, scope, missing approval, naive time, escapes and overwrite.
- The initial S1 readiness check now expects the registered shared grounding
  prompt. Exact prompt equality remains enforced; stale variants fail.
- The unsigned design lock now binds the unchanged timeout-300 protocol bytes.
  The earlier timeout change had left the timeout-90 hash in the lock. Original
  lock bytes and a provenance amendment are preserved under `protocol/amendments/`.
  Only `config_sha256` changed; authorization, signer and status fields did not.
- An incomplete sealed live-smoke trajectory now produces a blocked readiness
  report rather than indexing a nonexistent third turn. A regression covers
  zero, one and two observed turns, plus a three-turn unresolved task with no
  physical action.

The three pre-existing untracked README files were preserved. Agent worktrees
are locally excluded from Git. No private reference or request record was
deleted, normalized, regenerated or published.

## Evidence and remaining gates

| Gate | Evidence and state |
| --- | --- |
| Frozen inputs/private release | `runs/readiness/agent_b_20261020_current/`: 100 references, 74 execute / 26 clarify, 26 branches, 100 ledger histories; all 303 authenticated archive members match local bytes. |
| Safe engineering | Final current-code validation directory: `runs/readiness/coordinator_integrated_20261020_04/`. Read its actual summary, snapshot, test log, sealed 200-main/500-ablation mocks and synthetic analysis. |
| Live judge qualification | **TESTED_LIVE_SYNTHETIC**: `runs/judgments/agent_d_current_live_20261020_02/calibration.json`, SHA-256 `08339b2b1fc7f9e0930c0721670c3f9e40f958080185e6433562380b5baf8f4b`. All five fixtures and `verify_calibration(require_live=True)` pass, including explicit reference-conflict abstention. Provider revision identifiers are unavailable. |
| Live generator qualification | **FAILED, preserved**: `runs/development/coordinator_live_20261020_final_02/` and its `_evidence` directory. Sealed archive audit accounts for two initial predictions and three calls; both initial predictions failed. S0 returned `RECITATION`; S1.goal succeeded, while S1.ground returned `STOP` with duplicate-key/malformed output. No clarification replies were completed. This archive predates only the readiness crash fix and does not qualify as current-code success. |
| Technical freeze | Not prepared. Successful current-code S0/S1 two-answer trajectories remain required. Inspect the final candidate/readiness report; preparation must refuse incomplete evidence. |
| Main authorization/execution | No release-bound launch authorization exists. Protected main directory was absent when checked. Do not create authorization from the general goal instruction. |
| Five ablations | All five exact 100-case synthetic grids audited; 500 synthetic initial predictions and 1,660 calls. Protected execution still needs the separate hash-bound ablation authorization after main execution. |
| Protected judging/real analysis | Not started. Mock analysis verifies unresolved-outcome handling but supplies no study findings. |

Original private receipt/reference/archive hashes remain the registered values.
The protocol raw SHA-256 is
`db2ca7473d38c0b8e45f516bac395afeda3766e16503c6f6d371f1f16c399c67`;
the repaired unsigned root lock is
`9804e5a35fb1236f69079cbe203ead0df07e89570d820c981937e678ae0dcffc`.

## Provider diagnosis and continuation

Ignored, invented-only comparison receipts are preserved under
`runs/development/coordinator_endpoint_probe_20261020_01` through `_06`, with
their corresponding `coordinator_provider_probe_20261020*.py` scripts. Plain,
seed-only, JSON-mode and simple legacy-schema requests succeeded. Tiny
`responseJsonSchema` requests, its tested aliases, and the stable API endpoint
reproduced HTTP 500 `INTERNAL` (109-byte body hash
`8afb0f460c66c8c994af4793c44df522eb1a5d19c266051b83bc31ff0a64671f`).
The unchanged full task schema on the legacy field was rejected with HTTP 400.
The official S1 goal-stage success shows that JSON-schema use is not uniformly
rejected. These observations do not establish one root cause or a quota failure.

The [legacy provider Schema](https://ai.google.dev/api/generate-content#Schema)
cannot express the current typed arbitrary-name argument map without either
excluding currently valid names or leaving their values unconstrained. No
weaker provider schema or plain-JSON fallback was adopted.

Continue invented-fixture generator diagnosis with shared quota serialization
and preserved receipts. Integrate any justified fix before new qualification
and a fresh safe bundle. Only after all technical gates pass may an unsigned
technical freeze be prepared and the exact hash-bound main approval requested.
Main approval never authorizes the 500 ablations. Use the runbook's full A–K
scope through actual sealed runs and real joint analysis; this record does not
reduce that goal to engineering checks.
