"""Literature-derived, evaluator-only diagnostic scores.

This is NOT a replacement for score_semantics or an inference-time component.
All labels are explicit independent human judgments, matched to released
prediction/reference fingerprints. External signature and identity verification
is still required; this module cannot authenticate human reviewers.
"""
from collections import Counter
from statistics import mean
import re

from research.semantic_metrics import FIELDS as PRIMARY_FIELDS

SEEDS = (17, 29, 43, 71, 101)
TIER1 = ("intent", "action_names", "arguments", "parameter_complete",
         "unsupported_assumptions")
TIER3 = ("dialogue_consistent", "parameters_preserved", "task_correct")
RELATIONAL = ("referential_binding", "relational_correctness")
INDIRECT = ("appropriateness", "unambiguity", "world_understanding")
ELIGIBILITY = ("dialogue", "ambik", "codraw", "indirect", "vague", "relational")
AMBIGUITY_TYPES = ("human_preferences", "commonsense_knowledge", "safety")
QUESTION_TYPES = ("referent", "attribute", "location", "relation", "action",
                  "quantity", "time", "scope", "confirmation", "other")
VARIANTS = ("none", "full", "withheld")
HASH = re.compile(r"^[0-9a-f]{64}$")


def _fail(condition, message):
    if not condition:
        raise ValueError(message)


def _bool_fields(value, fields, title, *, nullable=False):
    _fail(isinstance(value, dict) and set(value) == set(fields), title + ": wrong fields")
    for field in fields:
        item = value[field]
        _fail(type(item) is bool or (nullable and item is None), title + ": invalid " + field)
    return value


def _strings(value, *, nonempty=False):
    _fail(isinstance(value, list) and all(isinstance(v, str) and v.strip() == v and v
                                         for v in value), "Expected normalized nonempty field identifiers")
    _fail(len(value) == len(set(value)), "Duplicate field identifiers")
    if nonempty:
        _fail(bool(value), "At least one field required")
    return set(value)


def _identity(row):
    for k in ("preparer_id", "verifier_id"):
        _fail(isinstance(row.get(k), str) and row[k].strip() == row[k]
              and row[k] and not row[k].startswith("["), "Real reviewer identities required")
    _fail(row["preparer_id"] != row["verifier_id"], "Reviewers must differ")
    _fail(row.get("review_status") == "independently_verified", "Unverified diagnostic review")


def _key(row):
    return (row["record_id"], row["seed"], row["condition"], row["branch_id"],
            row["turn"], row["context_variant"])


def _rate(bits):
    """Explicitly undefined for an empty eligible denominator."""
    values = list(bits)
    return {"numerator": sum(values), "denominator": len(values),
            "rate": mean(values) if values else None}


def _validate_reference_index(index):
    _fail(isinstance(index, dict) and bool(index), "Released reference index required")
    for case, ref in index.items():
        _fail(isinstance(case, str) and isinstance(ref, dict)
              and type(ref.get("revision")) is int and ref["revision"] >= 1
              and isinstance(ref.get("sha256"), str) and HASH.fullmatch(ref["sha256"]),
              "Versioned hashed human reference required")


def _validate_review(row, expected, ref):
    _identity(row)
    _fail(row["prediction_sha256"] == expected["sha256"]
          and row["reference_sha256"] == ref["sha256"]
          and row["reference_revision"] == ref["revision"],
          "Review does not bind exact prediction and approved reference")
    eligible = _bool_fields(row.get("eligibility"), ELIGIBILITY, "eligibility")
    tiers = row.get("tiers")
    _fail(isinstance(tiers, dict) and set(tiers) == {"single_turn", "clarification", "dialogue"},
          "All three review tiers required")
    single = _bool_fields(tiers["single_turn"], TIER1, "tier 1")
    clarify = tiers["clarification"]
    _fail(isinstance(clarify, dict) and set(clarify) == {
          "gold_critical_fields", "detected_critical_fields", "asked", "question_relevant",
          "question_information_type"}, "Tier 2 rubric incomplete")
    gold = _strings(clarify["gold_critical_fields"])
    detected = _strings(clarify["detected_critical_fields"])
    _fail(type(clarify["asked"]) is bool, "Asked flag must be explicitly judged")
    if clarify["asked"]:
        _fail(type(clarify["question_relevant"]) is bool
              and clarify["question_information_type"] in QUESTION_TYPES,
              "Actual question needs relevance and information target")
    else:
        _fail(clarify["question_relevant"] is None
              and clarify["question_information_type"] is None,
              "Unasked questions cannot receive hypothetical relevance/type")
    # In the independent review, criticality comes from the released reference,
    # not from the model's own unresolved list.
    _fail(isinstance(tiers["dialogue"], dict), "Tier 3 must be explicit")
    dialogue = _bool_fields(tiers["dialogue"], TIER3, "tier 3", nullable=True)
    if row["turn"] == 0 or not eligible["dialogue"]:
        _fail(all(dialogue[k] is None for k in TIER3),
              "Dialogue transition metrics only apply after turn zero")
    else:
        _fail(all(type(dialogue[k]) is bool for k in TIER3),
              "Eligible dialogue transitions require actual judgments")
    relations = _bool_fields(row.get("sarathy"), RELATIONAL, "Sarathy", nullable=True)
    _fail((all(type(v) is bool for v in relations.values()) if eligible["relational"]
           else all(v is None for v in relations.values())),
          "Relational labels must obey frozen eligibility")
    lit = row.get("literature")
    _fail(isinstance(lit, dict) and set(lit) == {
        "ambik_type", "appropriate_help", "codraw_information_type",
        "indirect_criteria", "vague_pair_id"}, "Literature annotation fields incomplete")
    _fail((lit["ambik_type"] in AMBIGUITY_TYPES and type(lit["appropriate_help"]) is bool)
          if eligible["ambik"] else
          (lit["ambik_type"] is None and lit["appropriate_help"] is None),
          "AmbiK category/appropriate-help labels must obey eligibility")
    _fail((clarify["asked"] and lit["codraw_information_type"] in QUESTION_TYPES)
          if eligible["codraw"] else lit["codraw_information_type"] is None,
          "CoDraw target requires a real clarification question and eligibility")
    _bool_fields(lit["indirect_criteria"], INDIRECT, "IndirectRequests", nullable=True)
    _fail((all(type(x) is bool for x in lit["indirect_criteria"].values())
           if eligible["indirect"] else
           all(x is None for x in lit["indirect_criteria"].values())),
          "IndirectRequests review must obey eligibility")
    _fail((isinstance(lit["vague_pair_id"], str) and bool(lit["vague_pair_id"])
           and row["context_variant"] in ("full", "withheld"))
          if eligible["vague"] else
          (lit["vague_pair_id"] is None and row["context_variant"] == "none"),
          "VAGUE contrast requires an explicit paired text-context intervention")
    return gold, detected


def score_literature_diagnostics(expected_predictions, reviews, reference_index, *,
                                 synthetic=False, semantic_summary=None):
    """Diagnostics only. Does not change primary S0/S1 full-task endpoint.

    expected_predictions are externally sealed descriptors containing
    record_id, seed, condition, branch_id, turn, context_variant, status, sha256.
    An error requires NO human review, and is counted only operationally.
    All OK descriptors require a one-to-one independently verified review.
    No partial review grids or invented labels can be scored.
    """
    _validate_reference_index(reference_index)
    _fail(isinstance(expected_predictions, list) and bool(expected_predictions)
          and isinstance(reviews, list), "Sealed descriptors and reviews required")
    expected = {}
    allowed = {"record_id", "seed", "condition", "branch_id", "turn",
               "context_variant", "status", "sha256"}
    for item in expected_predictions:
        _fail(isinstance(item, dict) and set(item) == allowed, "Invalid descriptor fields")
        k = _key(item)
        _fail(k not in expected and item["record_id"] in reference_index
              and type(item["seed"]) is int and type(item["turn"]) is int
              and 0 <= item["turn"] <= 5 and isinstance(item["condition"], str)
              and item["condition"] and isinstance(item["branch_id"], str)
              and item["branch_id"] and item["context_variant"] in VARIANTS
              and item["status"] in ("ok", "error") and HASH.fullmatch(item["sha256"]),
              "Duplicate, unplanned or invalid prediction")
        expected[k] = item
    if not synthetic:
        _fail(set(reference_index) == {f"CA-{i:04d}" for i in range(1, 101)},
              "Production requires exactly the protected 100 cases")
        _fail({x["seed"] for x in expected_predictions} == set(SEEDS),
              "Production requires all five locked seeds")
        for condition in ("S0", "S1"):
            for case in reference_index:
                for seed in SEEDS:
                    _fail(any(k[0] == case and k[1] == seed and k[2] == condition
                              and k[4] == 0 and k[5] == "none" for k in expected),
                          "Primary case/seed/condition initial grid incomplete")
    actual = {}
    for review in reviews:
        _fail(isinstance(review, dict), "Review must be an object")
        try:
            k = _key(review)
        except (KeyError, TypeError):
            raise ValueError("Incomplete review identity") from None
        _fail(k in expected and expected[k]["status"] == "ok" and k not in actual,
              "Unmatched, duplicate or operational-error review")
        _validate_review(review, expected[k], reference_index[k[0]])
        actual[k] = review
    _fail(set(actual) == {k for k, x in expected.items() if x["status"] == "ok"},
          "Missing independent diagnostic review; refusing partial scores")

    t1 = {name: [] for name in TIER1}
    t3 = {name: [] for name in TIER3}
    sarathy = {name: [] for name in RELATIONAL}
    indirect = {name: [] for name in INDIRECT}
    ambiguity = {name: [] for name in AMBIGUITY_TYPES}
    question = Counter()
    help_ok = []
    needed, asked, relevance = [], [], []
    critical_tp = critical_gold = critical_pred = 0
    for k, row in actual.items():
        tier = row["tiers"]
        single = tier["single_turn"]
        for name in TIER1:
            t1[name].append(not single[name] if name == "unsupported_assumptions"
                            else single[name])
        cf = tier["clarification"]
        gold = set(cf["gold_critical_fields"])
        predicted = set(cf["detected_critical_fields"])
        needed.append(bool(gold))
        asked.append(cf["asked"])
        critical_tp += len(gold & predicted)
        critical_gold += len(gold)
        critical_pred += len(predicted)
        if cf["asked"]:
            relevance.append(cf["question_relevant"])
        for name in TIER3:
            if tier["dialogue"][name] is not None:
                t3[name].append(tier["dialogue"][name])
        for name in RELATIONAL:
            if row["sarathy"][name] is not None:
                sarathy[name].append(row["sarathy"][name])
        literature = row["literature"]
        if row["eligibility"]["ambik"]:
            help_ok.append(literature["appropriate_help"])
            ambiguity[literature["ambik_type"]].append(literature["appropriate_help"])
        if row["eligibility"]["codraw"]:
            question[literature["codraw_information_type"]] += 1
        if row["eligibility"]["indirect"]:
            for name in INDIRECT:
                indirect[name].append(literature["indirect_criteria"][name])
    def ratio(num, den):
        return {"numerator": num, "denominator": den, "rate": num / den if den else None}
    diagnostics = {
        "status": "SYNTHETIC_ONLY" if synthetic else "REVIEWED_DESCRIPTORS_NOT_AUTHENTICATED",
        "primary_endpoint": "UNCHANGED: research.semantic_metrics.score_semantics",
        "expected_prediction_count": len(expected), "reviewed_output_count": len(actual),
        "operational_errors": len(expected) - len(actual),
        "tier1": {name: _rate(values) for name, values in t1.items()},
        "tier2": {
            "clarification_precision": ratio(sum(n and a for n, a in zip(needed, asked)), sum(asked)),
            "clarification_recall": ratio(sum(n and a for n, a in zip(needed, asked)), sum(needed)),
            "unnecessary_clarification": ratio(sum(not n and a for n, a in zip(needed, asked)),
                                                sum(not n for n in needed)),
            "missing_critical_field_recall": ratio(critical_tp, critical_gold),
            "missing_critical_field_precision": ratio(critical_tp, critical_pred),
            "question_relevance": _rate(relevance),
            "question_information_type_counts": dict(sorted(question.items())),
        },
        "tier3": {name: _rate(values) for name, values in t3.items()},
        "sarathy": {name: _rate(values) for name, values in sarathy.items()},
        "ambik": {"appropriate_help": _rate(help_ok),
                  "by_type": {name: _rate(v) for name, v in ambiguity.items()}},
        "indirect_requests": {name: _rate(v) for name, v in indirect.items()},
        "codraw_note": "Researcher-defined information taxonomy, not original dataset class IDs",
        "vague_text_context_contrast": "NOT_COMPUTED; use paired_vague_intent_contrast",
        "authenticity": "External released hashes, reviewer identities, and independent approval still required",
    }
    if semantic_summary is not None:
        curve = semantic_summary.get("completion_by_turn")
        _fail(isinstance(curve, dict) and set(curve) == set(range(6))
              and all(type(curve[i]) in (int, float) and 0 <= curve[i] <= 1
                      for i in range(6))
              and all(curve[i] <= curve[i + 1] for i in range(5)),
              "Cumulative outcome must come from an existing valid semantic summary")
        diagnostics["tier3"]["cumulative_completion_from_primary_scorer"] = dict(curve)
    else:
        diagnostics["tier3"]["cumulative_completion_from_primary_scorer"] = "NOT_COMPUTED"
    return diagnostics


def paired_vague_intent_contrast(reviews):
    """Per-case paired full-minus-withheld text-context intent contrast.

    Only human-scored, eligible paired review rows are accepted. Two context
    variants must share case, system, seed, branch, turn and frozen pair ID.
    Cases, not repetitions/branches, are units for the displayed effect.
    """
    _fail(isinstance(reviews, list) and bool(reviews), "Paired reviewed rows required")
    pair = {}
    for row in reviews:
        _identity(row)
        _fail(row["eligibility"]["vague"] and row["context_variant"] in ("full", "withheld")
              and type(row["tiers"]["single_turn"]["intent"]) is bool,
              "VAGUE pairs require reviewed binary intent judgments")
        key = (row["record_id"], row["condition"], row["seed"], row["branch_id"],
               row["turn"], row["literature"]["vague_pair_id"])
        slot = pair.setdefault(key, {})
        _fail(row["context_variant"] not in slot, "Duplicate context contrast variant")
        slot[row["context_variant"]] = int(row["tiers"]["single_turn"]["intent"])
    _fail(all(set(values) == {"full", "withheld"} for values in pair.values()),
          "Full/withheld comparison must be strictly paired")
    by_case = {}
    for key, values in pair.items():
        by_case.setdefault(key[0], []).append(values["full"] - values["withheld"])
    return {"status": "PAIRED_REVIEW_DESCRIPTORS_NEED_EXTERNAL_AUTHENTICATION",
            "adaptation": "TEXT_ONLY_SCENE_DESCRIPTION_NOT_VISUAL_VAGUE",
            "difference_full_minus_withheld": mean(mean(v) for v in by_case.values()),
            "independent_case_count": len(by_case), "paired_trajectory_count": len(pair),
            "unit_of_analysis": "average across paired branches/runs within case"}
