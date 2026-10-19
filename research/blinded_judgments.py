"""Evaluator-only, system-blinded semantic review candidates.

Never imported by inference. Reviewer identities are self-attested, not authenticated.
No review record alone authorizes publication of a semantic score.
"""
from __future__ import annotations
import hashlib
import hmac
import json

FIELDS = ("goal", "actions", "order", "arguments", "constraints", "dependencies", "evidence_supported")


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _identity(actor):
    if not isinstance(actor, str) or not actor.strip() or actor != actor.strip() or actor.startswith("["):
        raise ValueError("Actual reviewer identity is required")
    return actor


def _record_id(row):
    return (row["record_id"], row["seed"], row["branch_id"], row["turn"])


def build_blinded_packet(predictions, references, source_contexts, *, secret):
    """Prepare blinded packets only after predictions/gold have been externally sealed.

    External ledger/snapshot authentication is mandatory: this pure function
    does not know whether its input is genuinely frozen or human approved.
    Never send the private linkage file to reviewers or model generators.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Use an independent private 32+ byte blinding secret")
    if not isinstance(predictions, list) or not predictions:
        raise ValueError("Nonempty committed prediction list required")
    if not isinstance(references, dict) or not references or not isinstance(source_contexts, dict):
        raise ValueError("Approved reference and source snapshots required")
    review, mapping, seen = [], [], set()
    for row in predictions:
        if not isinstance(row, dict) or row.get("status") not in ("ok", "error"):
            raise ValueError("Invalid prediction")
        key = _record_id(row)
        case, seed, branch, turn = key
        if (not isinstance(case, str) or type(seed) is not int or not isinstance(branch, str)
                or type(turn) is not int or not 0 <= turn <= 5 or key in seen):
            raise ValueError("Missing, duplicate or invalid trajectory identity")
        seen.add(key)
        if case not in references or case not in source_contexts:
            raise ValueError("Unknown case; no gold may be invented")
        ref = references[case]
        if (type(ref.get("revision")) is not int or ref["revision"] < 1
                or not isinstance(ref.get("sha256"), str) or len(ref["sha256"]) != 64
                or not isinstance(ref.get("branches"), dict) or branch not in ref["branches"]):
            raise ValueError("Incomplete approved branch reference index")
        if row["status"] == "error":
            continue  # An operational failure remains a denominator failure, not a human judgment.
        if not isinstance(row.get("task"), dict):
            raise ValueError("Successful prediction lacks task")
        digest = canonical_hash(row)
        assignment_id = hmac.new(secret, (digest + "|" + "/".join(map(str, key))).encode("utf-8"),
                                 hashlib.sha256).hexdigest()[:24]
        mapping.append({"assignment_id": assignment_id, "record_id": case, "seed": seed,
                        "branch_id": branch, "turn": turn, "prediction_sha256": digest,
                        "reference_sha256": ref["sha256"], "reference_revision": ref["revision"]})
        review.append({"assignment_id": assignment_id,
                       "source_context": source_contexts[case],
                       "reference_task": ref["branches"][branch],
                       "predicted_task": row["task"],
                       "reviewer_id": None, "notes": None,
                       "fields": {field: None for field in FIELDS},
                       "unsupported_detail": None,
                       "initial_clarification_appropriate": None})
    if len({item["assignment_id"] for item in review}) != len(review):
        raise ValueError("Blinded assignment collision")
    return {"packet_status": "UNREVIEWED", "system_blinded": True,
            "benchmark_executed": False, "semantic_correctness": "NOT_COMPUTED",
            "human_review_items": review}, {"private_linkage": mapping}


def _validate_review(item, assignment_id, *, turn):
    if not isinstance(item, dict) or set(item) != {
            "assignment_id", "reviewer_id", "notes", "fields", "unsupported_detail",
            "initial_clarification_appropriate"}:
        raise ValueError("Unexpected review fields")
    if item["assignment_id"] != assignment_id or not isinstance(item["notes"], str) or not item["notes"].strip():
        raise ValueError("Unmatched assignment or missing substantive review notes")
    _identity(item["reviewer_id"])
    fields = item["fields"]
    if (not isinstance(fields, dict) or set(fields) != set(FIELDS)
            or any(type(fields[field]) is not bool for field in FIELDS)
            or type(item["unsupported_detail"]) is not bool):
        raise ValueError("Explicit boolean semantic judgments required for every field")
    decision = item["initial_clarification_appropriate"]
    if (turn == 0 and type(decision) is not bool) or (turn != 0 and decision is not None):
        raise ValueError("Initial clarification appropriateness belongs to turn zero only")
    return item


def combine_independent_reviews(linkage, first, second):
    """Require independent, exact pairwise agreement or record a dispute.

    A human third reviewer must separately adjudicate disagreements. Output
    is only a candidate for an authenticated release, not a final score.
    """
    mapping = linkage.get("private_linkage")
    if not isinstance(mapping, list) or not mapping:
        raise ValueError("Nonempty private sealed linkage required")
    ids = [r.get("assignment_id") for r in mapping]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate blinded linkage ID")
    if (not isinstance(first, list) or not isinstance(second, list)
            or set(ids) != {r.get("assignment_id") for r in first}
            or set(ids) != {r.get("assignment_id") for r in second}
            or len(first) != len(ids) or len(second) != len(ids)):
        raise ValueError("Both independent complete review grids required")
    left = {r["assignment_id"]: r for r in first}
    right = {r["assignment_id"]: r for r in second}
    judged, disputed = [], []
    for assignment in mapping:
        aid = assignment["assignment_id"]
        a = _validate_review(left[aid], aid, turn=assignment["turn"])
        b = _validate_review(right[aid], aid, turn=assignment["turn"])
        if a["reviewer_id"] == b["reviewer_id"]:
            raise ValueError("Independent reviewer identities must differ")
        decisions = ("fields", "unsupported_detail", "initial_clarification_appropriate")
        if any(a[field] != b[field] for field in decisions):
            disputed.append({"assignment_id": aid, "status": "NEEDS_INDEPENDENT_ADJUDICATION"})
            continue
        result = {name: assignment[name] for name in (
            "record_id", "seed", "branch_id", "turn", "prediction_sha256",
            "reference_sha256", "reference_revision")}
        result.update(status="independently_verified", preparer_id=a["reviewer_id"],
                      verifier_id=b["reviewer_id"], fields=dict(a["fields"]),
                      unsupported_detail=a["unsupported_detail"])
        if assignment["turn"] == 0:
            result["initial_clarification_appropriate"] = a["initial_clarification_appropriate"]
        judged.append(result)
    return {"review_status": "DISPUTED" if disputed else "AGREED_REVIEW_CANDIDATES",
            "semantic_correctness": "NOT_COMPUTED", "judgments": judged,
            "unresolved_disputes": disputed, "pairwise_agreement_complete": not disputed,
            "reviewer_identities_authenticated": False, "final_score_release_authorized": False}
