"""Build UNVERIFIED review artifacts from a complete, approved annotation export.

This is a clerical transformation, not an oracle, a semantic grader or proof
that an approval was genuine. Every candidate still requires independent review.
"""
from __future__ import annotations

from collections import Counter

MATCHING_METHOD = "anchored_question_intent_v2"


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _turns(branch):
    envelope = {name: branch.get(name) for name in ("question", "field", "answer", "simulated")}
    turns = branch.get("turns", [envelope])
    if not isinstance(turns, list) or not 1 <= len(turns) <= 5:
        raise ValueError("Each clarification branch needs between one and five turns")
    seen = set()
    for number, turn in enumerate(turns, 1):
        if not isinstance(turn, dict) or set(turn) != set(envelope):
            raise ValueError("Invalid clarification turn structure")
        if not all(_nonempty(turn[name]) for name in ("question", "field", "answer")):
            raise ValueError("Missing clarification question, field or answer")
        if turn["simulated"] is not True or turn["field"] in seen:
            raise ValueError("Clarification turns must be simulated and address distinct fields")
        seen.add(turn["field"])
        if number == 1 and turn != envelope:
            raise ValueError("First turn differs from the reviewed branch envelope")
    return turns


def build_review_bundle(export_manifest, rows, *, reference_sha256, expected_ids=None):
    """Return coverage/matching CANDIDATES, omitting answers and semantic tasks.

    The CLI separately binds an export to the ledger, verifies file hashes and
    source integrity. This function validates the export's shape and creates
    clerical candidate rows; it cannot promote them to independently reviewed.
    """
    if (not isinstance(export_manifest, dict) or export_manifest.get("complete") is not True
            or not isinstance(rows, list) or not rows or not _nonempty(reference_sha256)
            or len(reference_sha256) != 64 or any(c not in "0123456789abcdef" for c in reference_sha256)):
        raise ValueError("A complete, fingerprinted export is required")
    count = len(rows)
    if (export_manifest.get("record_count") != count or export_manifest.get("verified_count") != count
            or export_manifest.get("files", {}).get("verified_references.jsonl") != reference_sha256):
        raise ValueError("Export manifest count or digest mismatch")
    ids = [row.get("record_id") for row in rows if isinstance(row, dict)]
    if len(ids) != count or any(not _nonempty(case) for case in ids) or len(set(ids)) != count:
        raise ValueError("Export has malformed or repeated IDs")
    if expected_ids is not None and ids != list(expected_ids):
        raise ValueError("Export does not contain the complete ordered frozen cohort")
    heads = export_manifest.get("heads")
    if not isinstance(heads, dict) or set(heads) != set(ids):
        raise ValueError("Export ledger heads do not cover exactly the cases")
    coverage_rows, matching_rows = [], []
    routes = Counter()
    turn_count = 0
    for row in rows:
        case = row["record_id"]
        ref = row.get("reference")
        verification = row.get("verification")
        approval = row.get("final_approval")
        contributors = row.get("contributors")
        revision = row.get("revision")
        provenance = row.get("provenance")
        if (row.get("status") != "FINAL_APPROVED" or type(revision) is not int or revision < 1
                or not isinstance(ref, dict) or not isinstance(verification, dict)
                or verification.get("revision") != revision
                or not _nonempty(verification.get("actor")) or not isinstance(approval, dict)
                or not _nonempty(approval.get("actor")) or not isinstance(contributors, list)
                or not contributors or verification["actor"] in contributors
                or provenance not in ("human", "model_candidate")
                or (provenance == "model_candidate" and (row.get("model_assisted") is not True
                                                         or row.get("adopted") is not True))
                or heads[case] != row.get("history_head") or not _nonempty(row.get("history_head"))):
            raise ValueError("Unapproved, stale or incompletely reviewed annotation export")
        if ref.get("record_id") != case or not isinstance(ref.get("reference_task"), dict):
            raise ValueError("No completed semantic task for exported case")
        route = ref.get("author_approved_route")
        if route not in ("execute", "clarify"):
            raise ValueError("Unknown author-approved route")
        routes[route] += 1
        if (type(ref.get("dialogue_relevant")) is not bool
                or type(ref.get("explicit_linked_dependencies")) is not bool):
            raise ValueError("Subgroup eligibility must be decided explicitly")
        branches = ref.get("hypothetical_answer_branches")
        if not isinstance(branches, list) or (route == "clarify") != bool(branches):
            raise ValueError("Reviewed clarification branches do not match the route")
        branch_ids, branch_rules = [], []
        for branch in branches:
            if (not isinstance(branch, dict) or not _nonempty(branch.get("branch_id"))
                    or branch["branch_id"] in branch_ids or not isinstance(branch.get("reference_task"), dict)):
                raise ValueError("Invalid, duplicate or incomplete clarification branch")
            branch_ids.append(branch["branch_id"])
            rule_turns = []
            for number, turn in enumerate(_turns(branch), 1):
                turn_count += 1
                rule_turns.append({"turn": number, "field": turn["field"],
                                   "question": turn["question"],
                                   "canonical_question": turn["question"]})
            branch_rules.append({"branch_id": branch["branch_id"], "turns": rule_turns})
        item = {"record_id": case, "semantic_reference_revision": revision,
                "approved_route": route, "dialogue_relevant": ref["dialogue_relevant"],
                "explicit_dependency": ref["explicit_linked_dependencies"],
                "branch_count": len(branch_ids), "branch_ids": branch_ids}
        if route == "clarify":
            item.update(answer_branches_verified=False, question_matching_rules_verified=False)
        coverage_rows.append(item)
        matching_rows.append({"record_id": case, "reference_revision": revision,
                              "branches": branch_rules})
    coverage = {"reference_sha256": reference_sha256, "independently_verified": False,
                "cases": coverage_rows}
    matching = {"reference_sha256": reference_sha256, "method": MATCHING_METHOD,
                "independently_verified": False,
                "independent_review": {"preparer_id": None, "verifier_id": None, "notes": None},
                "cases": matching_rows}
    summary = {"type": "UNVERIFIED_REVIEW_CANDIDATES", "benchmark_executed": False,
               "semantic_correctness": "NOT_COMPUTED", "case_count": count,
               "route_counts": dict(sorted(routes.items())),
               "clarification_answer_turns": turn_count,
               "independent_review_required": True}
    return {"coverage_candidate": coverage, "matching_candidate": matching, "summary": summary}
