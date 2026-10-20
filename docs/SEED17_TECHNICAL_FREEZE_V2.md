# Seed-17 engineering freeze, version 2

This is an unsigned content freeze, not experimental launch authorization. The selected methodology remains `AUTHOR_APPROVED_AGENT_ASSISTED`; neither semantic truth nor a second human review is claimed.

`research/seed17_freeze.py` writes schema-2 technical records. Schema-1 records remain verifiable with their original rules. New records exclude manuscript and PDF production and bind:

- Every required readiness artifact, including the author receipt and reference export, canonical clarification matching and eligibility manifests, live initial/multi-turn evidence, live judge calibration and the complete test snapshot.
- All implementation snapshot members, historical source anchors and amendment JSON files.
- The exact current Python, operating-system/platform description, cryptography and websockets versions.
- Registered ablation and analysis contracts and sealed complete synthetic 200-prediction main and 500-prediction ablation execution evidence.

The readiness checker independently verifies the release/source/ledger/reference bindings, strict generation contract, schedules, judge calibration and test evidence. It re-audits the synthetic archives and requires their code fingerprints to equal all current research, tool and test Python files. The complete current code inventory must also match live multi-turn evidence. Existing failures and older configurations are retained; a historic pass does not validate modified code.

Prepare a fresh candidate after all code is stable:

```powershell
py tools/validate_seed17_safe.py --output runs/readiness/<fresh-candidate> --live-smoke-evidence runs/development/<successful-current-smoke>_evidence --judge-calibration runs/judgments/<successful-current-calibration>/calibration.json
py tools/check_seed17_readiness.py --bundle runs/readiness/<fresh-candidate>/candidate_bundle.json
```

Only if every technical gate has passed may the unsigned freeze be prepared:

```powershell
py tools/prepare_seed17_freeze.py --bundle runs/readiness/<fresh-candidate>/candidate_bundle.json --output runs/readiness/<fresh-unsigned-release>
```

Preparation rejects any failure except the two pending technical-freeze gates and the explicit-authorization gate. Its final report must have only `signed_off_release` outstanding. It never creates launch authorization, populates a signer, changes frozen ground truth or launches predictions. The main and ablation execution scopes remain separately authorized; preparing ablation infrastructure does not grant ablation execution permission.

Local raw-byte reference bindings are deliberate. Do not normalize or regenerate frozen release members to make hashes match. Private references, derived matching/eligibility projections and execution logs stay under ignored local evidence paths.
