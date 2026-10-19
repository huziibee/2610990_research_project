"""Evaluator process: only branch metadata or one matched reply leaves this process."""
import json
from pathlib import Path
import sys
from research.seed17_author_review import load_author_release
from research.clarification_matching import author_approved_oracle
from research.integrity import read_json, read_jsonl
from research.seed17_journal import content_hash
from research.single_seed_plan import schedules


class VerifiedOracle:
    def __init__(self, root, bundle):
        from research.seed17_gate import check_readiness
        if not check_readiness(root, bundle)["ready"]:
            raise ValueError("No signed-off reference release")
        self.release = load_author_release(root, bundle)
        self.rows = {r["record_id"]: r for r in self.release["rows"]}
        self.rules = read_json(root / bundle["artifacts"]["clarification_matching_rules"]["path"])
        self.export_hash = bundle["artifacts"]["semantic_references"]["sha256"]
        self.active = {}
        self.schedule = {row["sequence"]: row for row in schedules()[0]}

    def index(self):
        return {cid: {"revision": row["revision"], "sha256": content_hash(row["reference"]),
                      "branches": [b["branch_id"] for b in row["reference"]["hypothetical_answer_branches"]] or ["no-answer"]}
                for cid, row in self.rows.items()}

    def answer(self, sequence, record_id, branch_id, question, turn):
        if (type(sequence) is not int or sequence not in self.schedule
                or self.schedule[sequence]["record_id"] != record_id
                or branch_id not in self.index()[record_id]["branches"]
                or type(turn) is not int or not 1 <= turn <= 5):
            raise ValueError("Unplanned oracle query")
        if branch_id == "no-answer":
            return None
        key = (sequence, branch_id)
        if key not in self.active:
            self.active[key] = author_approved_oracle(self.release, record_id=record_id, branch_id=branch_id)
        return self.active[key](question, turn)


def main():
    root = Path(__file__).resolve().parents[1]
    bundle = read_json(sys.argv[1])
    oracle = VerifiedOracle(root, bundle)
    for line in sys.stdin:
        try:
            query = json.loads(line)
            op = query.pop("op")
            if op == "index" and not query:
                result = {"index": oracle.index()}
            elif op == "answer" and set(query) == {"sequence", "record_id", "branch_id", "question", "turn"}:
                result = {"answer": oracle.answer(**query)}
            else:
                raise ValueError("Unsupported reference RPC")
        except Exception:
            result = {"rpc_error": True}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
