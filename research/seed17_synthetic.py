"""Explicitly invented fixtures; identities below are NOT real review claims."""
import json
from research.clarification_matching import FrozenClarificationOracle, METHOD
from research.seed17_journal import content_hash

FIELDS = ["destination", "time", "speed", "container", "priority"]
ANSWERS = ["Shelf A", "09:00", "slow", "box A", "normal"]
QUESTIONS = ["Which shelf?", "When?", "What speed?", "Which container?", "What priority?"]


def cohort(count=100, *, multi_turn=False):
    inputs, references, rule_cases = {}, {}, []
    for number in range(1, count + 1):
        cid = f"SYNTHETIC-{number:03d}"
        depth = 2 if multi_turn else ((number - 1) % 5 + 1 if number <= 26 else 0)
        required = FIELDS[:depth]
        inputs[cid] = {"record_id": cid,
                       "instruction": "Move the blue cup. Required additional fields: " + ", ".join(required) + ".",
                       "scene": "A blue cup is on the desk. Shelf A and shelf B are empty.", "dialogue": [],
                       "capabilities": "move(object: object" + "".join(", " + f + ": string" for f in required) + ") requires all listed fields."}
        turns = [{"field": f, "question": q, "answer": a, "simulated": True}
                 for f, q, a in zip(required, QUESTIONS, ANSWERS)]
        branches = [{"branch_id": "branch-a", **turns[0], "turns": turns,
                     "reference_task": {"SYNTHETIC_HIDDEN_REFERENCE_SENTINEL": True}, "evidence_claims": []}] if depth else []
        reference = {"record_id": cid, "author_approved_route": "clarify" if depth else "execute",
                     "hypothetical_answer_branches": branches}
        references[cid] = {"record_id": cid, "status": "FINAL_APPROVED", "provenance": "human",
            "model_assisted": False, "revision": 1, "history_head": "SYNTHETIC_FIXTURE_ONLY",
            "contributors": ["SYNTHETIC_FIXTURE_WRITER"],
            "verification": {"actor": "SYNTHETIC_FIXTURE_VERIFIER", "revision": 1, "notes": "Invented test fixture"},
            "final_approval": {"actor": "SYNTHETIC_FIXTURE_APPROVER", "notes": "Invented test fixture"},
            "reference": reference}
        rule_cases.append({"record_id": cid, "reference_revision": 1, "branches": [
            {"branch_id": "branch-a", "turns": [{"turn": i, "field": t["field"], "question": t["question"],
                                                   "question_variants": [t["question"]]} for i, t in enumerate(turns, 1)]}
        ] if depth else []})
    export_hash = content_hash(list(references.values()))
    rules = {"reference_sha256": export_hash, "method": METHOD, "independently_verified": True,
             "independent_review": {"preparer_id": "SYNTHETIC_RULE_WRITER", "verifier_id": "SYNTHETIC_RULE_VERIFIER",
                                    "notes": "Invented fixture only"}, "cases": rule_cases}
    return inputs, references, rules, export_hash


class SyntheticOracle:
    def __init__(self, references, rules, export_hash):
        if any(not c.startswith("SYNTHETIC-") for c in references):
            raise ValueError("Synthetic oracle rejects protected IDs")
        self.references, self.rules, self.export_hash = references, rules, export_hash
        self.oracles = {}

    def index(self):
        return {cid: {"revision": row["revision"], "sha256": content_hash(row["reference"]),
                      "branches": [b["branch_id"] for b in row["reference"]["hypothetical_answer_branches"]] or ["no-answer"]}
                for cid, row in self.references.items()}

    def answer(self, *, sequence, record_id, branch_id, question, turn):
        if branch_id == "no-answer":
            return None
        key = (sequence, branch_id)
        if key not in self.oracles:
            self.oracles[key] = FrozenClarificationOracle(self.references[record_id], self.rules,
                reference_export_sha256=self.export_hash, branch_id=branch_id)
        return self.oracles[key](question, turn)


def mock_send(payload, settings):
    """The fake model uses visible text only, never the fixture reference object."""
    body = json.loads(payload["contents"][0]["parts"][0]["text"])
    visible = body["input"]
    required_text = visible["instruction"].split("Required additional fields: ")[1].rstrip(".")
    required = required_text.split(", ") if required_text else []
    replies = [s.removeprefix("User answer (simulated): ") for s in visible["dialogue"] if s.startswith("User answer (simulated): ")]
    goal = "Move the blue cup"
    stage = payload["systemInstruction"]["parts"][0]["text"]
    if "Recover the intended goal." in stage:
        value = {"intended_goal": goal}
    else:
        arguments = {"object": {"type": "object", "value": "blue cup", "evidence": ["instruction"]}}
        for field, answer in zip(required, replies):
            arguments[field] = {"type": "string", "value": answer, "evidence": ["dialogue"]}
        missing = required[len(replies):]
        value = {"intended_goal": goal, "actions": [{"action_id": "a1", "capability_id": "move", "arguments": arguments,
                  "constraints": []}], "unresolved": [{"field": f, "reason": "missing", "critical": True} for f in missing],
                 "dependencies": [], "readiness": "CLARIFY" if missing else "ACTION_READY",
                 "clarification_question": QUESTIONS[FIELDS.index(missing[0])] if missing else None}
    return {"modelVersion": "MOCK_SEED17_NOT_PROVIDER_EVIDENCE", "responseId": "SYNTHETIC_RESPONSE",
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150},
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}]}
