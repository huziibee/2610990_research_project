# Literature-grounded evaluation handoff — 2026-10-19

**Scope**: evaluator-only diagnostics; no change to the frozen main S0-versus-S1 complete-task endpoint, 100 case IDs, five seeds (17, 29, 43, 71, 101), frozen routes, architecture files, or held-out inference.

## Audit and reuse

| Existing component | Implemented before this branch | This branch |
| --- | --- | --- |
| \`research/semantic_metrics.py\` | Seven independently reviewed semantic dimensions; unsupported detail; 0–5-turn cumulative correctness, branch-averaged task success; paired case-level bootstrap | Reused, never overwritten |
| \`research/metrics.py\` | Route matrix, error denominators, paired route bootstrap | Reused, not conflated with task correctness |
| \`research/clarification_matching.py\` | Frozen exact normalized human-approved question variants, sequential simulated answers | Untouched; question relevance evaluated separately |
| \`research/reference_schema.py\` | Versioned task, critical unknowns, alternatives, evidence claims, up to five simulated turns | Additional external diagnostic reference metadata still needs genuine human review |
| \`research/blinded_judgments.py\` | Independent system-blind candidates; unresolved disputes; external identity authentication required | No auto-upgrade of candidate records |
| \`research/ablations.py\` | Scene/dialogue removal and limited dependency consistency intervention | Only matched human-scored text context differences are eligible |
| \`tools/render_paper_results.py\` | Verified-scoring candidate tables, latency, stability, failure categories, ablations, turn curves | Separate diagnostics JSON interface; preserve renderer contract and manuscript artifact |

## Metric definitions and eligibility

Use \`research.literature_evaluation.score_literature_diagnostics(expected_predictions, reviews, reference_index, synthetic=False)\` **only after** authenticated prediction seals, reference exports, annotation lineage, review approvals, independent reviewer checks, and external release are completed. It validates shapes, joins, unique keys and self-declared reviewer provenance; it cannot authenticate people or release evidence.

Each \`expected_predictions\` descriptor has exactly: \`record_id\`, \`seed\`, \`condition\`, \`branch_id\`, \`turn\` (0–5), \`context_variant\` (\`none\`, \`full\`, \`withheld\`), \`status\` (\`ok\`/\`error\`), \`sha256\`. For successful outputs, SHA-256 must be the exact canonical serialized prediction hash, as in the existing semantic scorer; the exporter must verify it, not just copy a label. Review entries use the same six-part key and must include \`prediction_sha256\`, \`reference_sha256\`, \`reference_revision\`, \`preparer_id\`, \`verifier_id\`, \`review_status: independently_verified\`, six explicitly judged applicability booleans, and the tiers, Sarathy, and literature rubrics. The reference index is \`case -> {revision:int, sha256:hex}\`. No review is permitted for an operational error. Missing review of a successful output fails closed.

**Tier 1:** binary \`intent\`, \`action_names\`, \`arguments\`, \`parameter_complete\`, \`unsupported_assumptions\`. The first four are correctness rates. For the last, the evaluator reports **absence of unsupported assumptions** (\`not unsupported_assumptions\`) as a desirable success rate; incidence = 1 - absence. Denominator: all successfully predicted, independently reviewed outputs; not equivalent to primary task success.

**Tier 2:** \`gold_critical_fields\` and \`detected_critical_fields\` are explicit human-reviewed lists; \`asked\` is an observed binary; question relevance and information target are required only if actually asked. Let N=reference critical-field set nonempty, A=question asked. Clarification precision = count(N and A)/count(A), recall = count(N and A)/count(N), unnecessary clarification = count(not N and A)/count(not N). Field precision = sum |gold intersect detected| / sum |detected| and recall = sum |gold intersect detected| / sum |gold|. Relevance = relevant observed questions / all reviewed observed questions. CoDraw information-target counts use only explicitly eligible, actually asked questions; the taxonomy is researcher-defined, not borrowed label IDs. Empty denominators return null.

**Tier 3:** \`dialogue_consistent\`, \`parameters_preserved\`, \`task_correct\` are reviewed on eligible observed turns 1–5. At turn 0 or for dialogue-ineligible outputs each value is null. These are transition diagnostics; **cumulative completion** uses only the original \`research.semantic_metrics.score_semantics\` result, which counts fully correct action-ready tasks at or before turn t, averaged over alternate approved branches and repeated seeds. Do not derive cumulative correctness from the transition field or from route labels. Zero through five inclusive; no claim of observed human interaction when replies are simulated.

**Sarathy:** tier-one intent/action names plus separately eligible human judgments on referential binding and relational correctness. A relation requires the correct source, target, type, direction and semantic task meaning, including cross-action dependencies, not just syntactically valid pointers. The reference/schema must record relation applicability and expected typed edges. Until Chat A supplies those reviewed items, relational scores are ineligible (null) rather than inferred from absence of dependencies.

**AmbiK:** annotate applicability and a category (\`human_preferences\`, \`commonsense_knowledge\`, \`safety\`) and independent binary appropriate-help judgment; calculate category-specific frequencies with eligible denominators. This is an analytic adaptation, not an automatic import of the original kitchen gold.

**IndirectRequests:** on eligible indirect commands, three independent binary ratings: \`appropriateness\`, \`unambiguity\`, \`world_understanding\`. This compresses source rating concepts into project binary rubrics and should not be called a reproduced benchmark rating scale.

**VAGUE:** \`paired_vague_intent_contrast\` accepts matching full-vs-withheld *textual scene description* pairs with same case, condition, seed, branch, turn, and human-reviewed pair ID. Difference is full minus withheld intent accuracy; average repeated pairs within each independent case before taking the final mean. Without both paired variants there is no result. No images, visual models, or VAGUE original-task scores.

## Review rubric and evidence boundaries

For each field the reviewer records a yes/no decision and substantive prose notes in an external ledger. Intent: did the intended communicative act match supported task purpose? Action names: did the action sequence use the correct robot-relevant verbs/capabilities? Arguments: are entity/value bindings and roles correct? Parameter completeness: are all required execution-critical parameters present, or explicitly pending if not ready? Unsupported assumption: any guessed object, property, time, capability or relation not established by input/user reply? Critical unknowns: use human-approved reference, not an LLM's own uncertainty. Question relevance: would answering this specific observed question eliminate an execution-critical uncertainty, without diverting to unrelated details? Dialogue consistency: is the current interpretation compatible with the dialogue so far? Parameter preservation: have confirmed values remained unchanged except for explicit correction? Relation: are ordered endpoints, relation labels, directions, and dependencies semantically correct?

Where labels are inapplicable, use null and record a frozen eligibility decision. **Do not silently assign false or true** to inapplicable items. Multiple error tags may coexist. Existing authored route decisions are neither changed nor adjudicated by this branch.

## Precise handoff to Chat A: optional relational diagnostics

Chat A architecture remains the sole owner of generating any runtime relational representation. Proposed **evaluator-side** export per predicted case/seed/branch/turn:

\`\`\`json
{
  "schema_version": 1,
  "record_id": "CA-0001",
  "seed": 17,
  "condition": "S1",
  "branch_id": "branch-A",
  "turn": 0,
  "prediction_sha256": "<canonical actual prediction digest>",
  "task_schema_version": "<actual existing schema release>",
  "relations": [
    {
      "source_pointer": "/actions/0/arguments/source/value",
      "target_pointer": "/actions/1/arguments/destination/value",
      "relation_type": "<human-reviewed relationship vocabulary>",
      "direction": "source_to_target",
      "supporting_evidence_pointers": ["<visible source citation pointer>"]
    }
  ]
}
\`\`\`

This is an **interface proposal**, not an assertion that existing outputs contain these keys. Chat A should supply exactly the existing task's JSON-pointer identities (not edit a protected schema), formally define relation vocabulary, maintain order, distinguish absent edges from unavailable data, and avoid exposing reference gold in model prompts. The evaluator independently checks pointers and human-approved relational-gold endpoints, label, direction, and meaning. A syntactic validator passing is not sufficient. Owners must agree the immutable JSON schema and release hash before deriving actual metrics.

## Human semantic-gold export handoff

Prerequisites: 100 individually prepared tasks with evidence support and acceptable alternatives, exact capability evidence, explicit critical unknown sets, confirmed route preservation, approved answer branches for clarify cases, dependent-field relevance decisions, two genuine independent human reviews and separately documented adjudication. Store each record's revision, SHA-256, preparation/review identities, notes, source snapshot hashes, and final approval history. Freeze that export *before* a held-out run. Match prediction hashes and reference revision in every diagnostic judgment. Initial question matching requires separately verified approved variants. A successful output without reviewed fields blocks scoring. Error predictions count as operational failures but receive no fabricated reviewer answers. Reviewer identities, gold release, and integrity must be verified by an external gate; names and hashes by themselves are not evidence of independence.

## Reporting and provenance

Literature diagnostics remain separate from existing \`render_paper_results\` primary publication interface. Synthetic unit fixtures use \`SYNTHETIC-*\` records and \`synthetic=True\` and never produce manuscript values. For real release: compare S0/S1 over the same 100 cases and five seeds; report numerator/denominator, eligibility, missingness, per-category differences, operational errors, and whether replies were simulated. No diagnostic score is a replacement for complete task correctness. LaTeX tables are marked TBD until all release conditions are met.

## Literature-to-method mapping (no outside literature)

| Manuscript source | What is adapted | What is explicitly not claimed |
| --- | --- | --- |
| ClarifyVC (Zhou et al., 2026) | Three-tier parsing/clarification/multi-turn evaluator categories | Vehicle protocol compliance, trained model, or recreated benchmark |
| Sarathy et al. (2025) | Intent, action, referential and relational diagnostic dimensions | Their robotic integration paradigm or parser implemented here |
| AmbiK (Ivanova et al., 2025) | Ambiguity-type stratification and appropriate help | Original kitchen benchmark results transferred to new cases |
| CoDraw-iCR (Madureira & Schlangen, 2023) | Content of instruction clarification requests | Native CoDraw taxonomy or multimodal interaction replicated |
| IndirectRequests (Mannekote et al., 2025) | Appropriateness, unambiguity, world-understanding rubric | Original scale/annotation reliability reproduced |
| VAGUE (Nam et al., 2025) | Matched scene-context dependency in intent interpretation | Any visual-image or multimodal benchmark claim |
| Grice (1975), Searle (1975), Zhang et al. (CHI 2025) | Indirect intent, conversational relevance and HRI theoretical motivation | Implemented Gricean or speech-act rule system; human trust study |

## Outstanding blockers

1. Independently reviewed and approved semantic-gold action/argument/critical-field/branch references across all 100 cases.
2. Real independently reviewed diagnostic judgments, disagreement adjudication and externally authenticated reviewer identities.
3. Matched, appropriately eligible scene-withheld runs, separate from protected primary evaluation and frozen before running.
4. Chat A's formally agreed relational edge vocabulary, validity/provenance and reference eligibility annotations.
5. Gemini API access, exact model/config compatibility, runtime observations and a sealed hosted evaluation run.
6. LaTeX compilation and visual column-fit inspection after reviewed result insertion.
