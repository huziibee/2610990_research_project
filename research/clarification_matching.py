"""Evaluator-only frozen simulated-answer oracle; never import in model prompts.

Callers must load a verified export through the readiness/ledger checks first.
The supplied export digest binds the rule manifest, but is not by itself proof
that an arbitrary in-memory row belongs to that export. This object returns only
the next single simulated answer after an approved question match. Task gold,
future answers, canonical questions and matching rules never enter the callback
return value or the model input.
"""
import copy
import re
from research.reference_schema import clarification_turns

METHOD = "exact_normalized_approved_question_variants_v1"


def normalize_question(value):
    """Frozen matching rule: collapse whitespace, then Unicode casefold only."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Question must be a nonempty string")
    return " ".join(value.split()).casefold()


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _verified_wrapper(row):
    if not isinstance(row, dict):
        raise ValueError("Verified exported reference wrapper required")
    contributors = row.get("contributors")
    verification = row.get("verification")
    approval = row.get("final_approval")
    human_reviewed_provenance = (row.get("provenance") == "human"
        or (row.get("provenance") == "model_candidate" and row.get("adopted") is True and row.get("model_assisted") is True))
    if (row.get("status") != "FINAL_APPROVED" or not human_reviewed_provenance
            or type(row.get("revision")) is not int or row["revision"] < 1
            or not _nonempty(row.get("history_head"))
            or not isinstance(contributors, list) or not contributors or not all(_nonempty(x) for x in contributors)
            or not isinstance(verification, dict) or not _nonempty(verification.get("actor"))
            or verification["actor"] in contributors or verification.get("revision") != row["revision"]
            or not _nonempty(verification.get("notes"))
            or not isinstance(approval, dict) or not _nonempty(approval.get("actor"))
            or not _nonempty(approval.get("notes")) or not isinstance(row.get("reference"), dict)):
        raise ValueError("Reference must have exact-revision independent verification and final human approval")


class FrozenClarificationOracle:
    def __init__(self, verified_reference, rule_manifest, *, reference_export_sha256, branch_id):
        _verified_wrapper(verified_reference)
        if not isinstance(rule_manifest, dict):
            raise ValueError("Frozen matching rule manifest required")
        if (not isinstance(reference_export_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", reference_export_sha256)
                or rule_manifest.get("reference_sha256") != reference_export_sha256
                or rule_manifest.get("method") != METHOD or rule_manifest.get("independently_verified") is not True):
            raise ValueError("Matching rules must bind the exact verified reference export and frozen method")
        review = rule_manifest.get("independent_review")
        if (not isinstance(review, dict) or not _nonempty(review.get("preparer_id"))
                or not _nonempty(review.get("verifier_id")) or review["preparer_id"] == review["verifier_id"]
                or not _nonempty(review.get("notes"))):
            raise ValueError("Independent human matching-rule review required")
        cases = rule_manifest.get("cases")
        if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
            raise ValueError("Matching cases must be a list of objects")
        ids = [case.get("record_id") for case in cases]
        if not all(_nonempty(value) for value in ids) or len(ids) != len(set(ids)):
            raise ValueError("Matching case IDs must be unique")
        matching = [case for case in cases if case["record_id"] == verified_reference.get("record_id")]
        if len(matching) != 1 or matching[0].get("reference_revision") != verified_reference["revision"]:
            raise ValueError("Missing or stale case matching rules")
        reference = verified_reference["reference"]
        if (reference.get("record_id") != verified_reference.get("record_id")
                or reference.get("author_approved_route") != "clarify"):
            raise ValueError("Only approved clarification cases have simulated-answer branches")
        branches = reference.get("hypothetical_answer_branches")
        rules = matching[0].get("branches")
        if (not isinstance(branches, list) or not branches or not isinstance(rules, list)
                or any(not isinstance(b, dict) or not _nonempty(b.get("branch_id")) for b in [*branches, *rules])):
            raise ValueError("Explicit reference branches and rules required")
        branch_ids = [b["branch_id"] for b in branches]
        rule_ids = [b["branch_id"] for b in rules]
        if len(branch_ids) != len(set(branch_ids)) or len(rule_ids) != len(set(rule_ids)) or set(branch_ids) != set(rule_ids):
            raise ValueError("Matching rules must cover exactly the unique verified branches")
        paths = {}
        for branch in branches:
            turns = clarification_turns(branch)
            branch_rules = next(r for r in rules if r["branch_id"] == branch["branch_id"])
            turn_rules = branch_rules.get("turns")
            if not isinstance(turn_rules, list) or len(turn_rules) != len(turns):
                raise ValueError("Matching rules must cover every verified branch turn")
            path = []
            for number, (turn, rule) in enumerate(zip(turns, turn_rules), 1):
                if (not isinstance(rule, dict) or set(rule) != {"turn", "field", "question", "question_variants"}
                        or type(rule["turn"]) is not int or rule["turn"] != number
                        or rule["question"] != turn["question"] or rule["field"] != turn["field"]):
                    raise ValueError("Matching rule changed verified question, field or turn order")
                variants = rule["question_variants"]
                if not isinstance(variants, list) or not variants:
                    raise ValueError("Human-approved question variants required")
                normalized = {normalize_question(value) for value in variants}
                if normalize_question(turn["question"]) not in normalized:
                    raise ValueError("Verified canonical question must be an accepted variant")
                path.append({"answer": turn["answer"], "variants": normalized})
            paths[branch["branch_id"]] = path
        if branch_id not in paths:
            raise ValueError("Unknown simulated-answer branch")
        self._path = copy.deepcopy(paths[branch_id])
        self._next = 1
        self._closed = False
        self.audit = []

    def __call__(self, question, turn):
        entry = {"turn": turn, "question": question, "simulated": True, "status": "unavailable"}
        self.audit.append(entry)
        if self._closed:
            return None
        if type(turn) is not int or turn != self._next:
            self._closed = True
            entry["status"] = "invalid_sequence"
            raise ValueError("Simulated answers require sequential, single-use clarification turns")
        if self._next > len(self._path):
            self._closed = True
            return None
        try:
            normalized = normalize_question(question)
        except ValueError:
            self._closed = True
            return None
        step = self._path[self._next - 1]
        if normalized not in step["variants"]:
            self._closed = True
            return None
        self._next += 1
        entry["status"] = "matched"
        return step["answer"]


def author_approved_oracle(release, *, record_id, branch_id):
    """Selected AUTHOR_APPROVED_AGENT_ASSISTED pathway; legacy class above unchanged.

    release must come from load_author_release, which checks exact source,
    receipt, export, ledger, branch and matching/eligibility bindings.
    """
    from research.seed17_author_review import AuthorReviewedClarificationOracle
    return AuthorReviewedClarificationOracle(release,record_id=record_id,branch_id=branch_id)
