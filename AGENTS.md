# Current research execution instructions

Read `docs/FIVE_SEED_EXECUTION.md` first. The current authorized task is the
Gemini 3.5 Flash-Lite **five-seed ambiguity study**, including main S0/S1, all five
ablations, isolated semantic judging, numerical analysis and figures. **Do not
write the paper.** Older seed-17/Gemma runbooks are preserved history, not the
current execution command or authority.

Current entrypoint: `python tools/finish_five_seed.py --execute-all` in an
appropriately credentialed environment. Without `--execute-all` it is read-only.
The actual user has delegated both scopes and the final verified hash binding;
`protocol/five_seed/session_delegation_v1.json` records their words. No new blanket
approval loop is required, and no signature or user signing timestamp may be
invented. Authorization still cannot replace technical verification.

Invariant: unchanged original 100 author-reviewed references/26 branches,
seeds 17/29/43/71/101, 1000 main and 2500 ablation initial predictions, up to five
approved replies, no automatic retries of protected failed or unknown sends.
No mandatory safety capability catalog. Keep typed schema, evidence, dependency
checks (except the precise dependency ablation), conservative approved-question
matching, and all failures/unknowns in denominators. Preserve all raw receipts.

Independent code audits/tests may run in parallel, but only one coordinator owns
provider requests, quota, private-oracle state and protected journal. Do not edit
frozen code after observing results. Use current tests and actual immutable
archives, never summaries or mock values, to certify results. Secrets and private
references stay out of Git, issues, public logs and downloadable public artifacts.
