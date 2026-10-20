# Seed-17 ablation infrastructure

This is an engineering registration, not permission to execute protected cases.
The historical five-seed plan, 2,500-row schedule, input datasets, reference
answers and evidence remain unchanged. The separate contract is
`protocol/seed17/ablation_contract_v1.json`.

The runner uses the existing shuffled seed-17 ablation schedule, preserving all
500 historical rows and adding `system: S1` solely to route two-stage inference.
Each of 100 source cases has one initial prediction under each of five
interventions. Cases and seed are matched to main S1. Every stage retains the
Gemma model, minimal thinking with thoughts excluded, JSON schema enforcement,
seed 17 and 2,048-token output cap. Each prediction has at most two requests;
failure before the second stage remains a failed prediction in the denominator.

The registered interventions retain their existing implementation meanings:

- Goal first substitutes a context-summary intermediate and corresponding
  second-stage prompt for the explicit goal intermediate. Implicit goal
  inference cannot be excluded.
- Structured grounding removes explicit grounding instructions from the second
  prompt. It retains JSON structure, schemas and validation, so it is a prompt
  intervention rather than a removal of structured representation.
- Scene replaces the scene field with the existing fixed mask on every turn.
  Arguments cannot cite withheld scene evidence.
- Dependency checking disables only deterministic dependency-consistency checks.
  Typed arguments, evidence paths and other schema checks remain mandatory.
  Incorrect dependencies still count against evaluation correctness.
- Dialogue clears the entire dialogue field on every prediction, including
  approved simulated replies. The same strict oracle can release answers to the
  coordinator, but they remain withheld from this generation condition. Asking
  an unsupported or repeated question can therefore stop that trajectory as
  `ANSWER_UNAVAILABLE`; this outcome remains in the denominator. No alternative
  answer or relaxed matching is supplied to make the intervention succeed.

Every manifest records actual per-condition prompts, settings, masks, validation
differences and the contract hash. Original inputs are retained separately from
the transformed model-visible fields and bound by hash. The generation worker
receives only validated public inputs and opaque branch identifiers, while the
separate oracle process owns reference access. Durable oracle intent/result
receipts and turn checkpoints are shared with the main runner. Unknown sends
block the whole run; explicit resume replays durable provider responses rather
than resending them. Provider failures are preserved, with transient errors
pausing execution for explicit recovery. Malformed outputs receive no retry.

Planning and complete synthetic validation require no protected data:

```powershell
py tools/run_seed17_ablations.py
py tools/run_seed17_ablations.py --mock --output runs/mock_seed17_ablations/NEW_UNIQUE_ID
py -m unittest discover -s tests -p test_seed17_ablation.py -v
```

The synthetic command executes all 500 initial predictions and their fixture
trajectories using an explicit fake transport. Its report labels the output
`SYNTHETIC_ENGINEERING_ONLY`; semantic correctness remains `NOT_COMPUTED`.
`research.seed17_ablation_audit.audit(path, synthetic=True)` verifies the exact
grid, settings, stage prompts, masked inputs, typed tasks, request identities,
receipts, dialogue updates, stop reasons, durable oracle events, complete
denominators and immutable archive membership. It verifies sealed resume before
returning without new calls. Additions, omissions and changed files fail closed.

Protected execution requires a ready main release **and a separate actual user
ablation authorization**. The general development request and main-run
authorization do not grant this scope. The document must contain the explicit
status `EXPLICIT_USER_ABLATION_AUTHORIZATION`, exact ablation scope, technical
freeze hash, base-artifact hash, contract hash, exact 500-row schedule content
hash, fixed execution directory, actual author identity, dated timezone-aware
authorization and verbatim authorization text. No such document is created by
the engineering runner. Its provenance is documentary; identity is not claimed
to be cryptographically authenticated.

Only after separate authorization, the eventual command is:

```powershell
py tools/run_seed17_ablations.py --execute --bundle PATH_TO_MAIN_AUTHORIZED_BUNDLE --authorization PATH_TO_EXPLICIT_ABLATION_AUTHORIZATION
```

The one allowed output directory is
`runs/evaluation/seed17/gemma4-seed17-ablations-v1`. Explicit recovery adds
`--resume` with the same hashes, code, inputs and authorization. A main-only
worker refuses ablation manifests. The ablation oracle independently checks
both readiness and the separate authorization before exposing branch metadata.

The initial budget is at most 1,000 requests. A five-reply trajectory adds at most
10 requests per branch, giving at most 6,000 total requests if every case has one
branch and requires five replies. The exact branch-aware ceiling is
`1000 + 10 * sum(max(1, approved_branch_count(case)) for each scheduled condition/case)`;
multi-branch cases can increase it. Early stops and failed stages reduce actual
requests. The shared quota ledger paces both main and ablation calls.

Automated scoring uses `tools/score_single_seed.py --ablations` with the same
author-approved release, frozen isolated judge and unresolved-outcome rules as
the main evaluation. Effects pair each condition with main S1 by source case;
failures and unresolved judgments stay in the 100-case denominator. One seed
cannot estimate between-seed variability. No protected result is produced by
the synthetic engineering checks.
