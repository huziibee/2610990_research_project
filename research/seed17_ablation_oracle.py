"""Reference process for separately authorized ablations; worker never imports it."""
import json
from pathlib import Path
import sys

from research.integrity import read_json
from research.seed17_ablation import schedule, validate_authorization
from research.seed17_oracle_service import VerifiedOracle
from tools.run_experiment import IDS


class AblationOracle(VerifiedOracle):
    def __init__(self, root, bundle, authorization):
        validate_authorization(root, bundle, authorization)
        super().__init__(root, bundle)
        self.schedule = {row["sequence"]: row for row in schedule(IDS)}


def main():
    root = Path(__file__).resolve().parents[1]
    oracle = AblationOracle(root, read_json(sys.argv[1]), read_json(sys.argv[2]))
    for line in sys.stdin:
        try:
            query = json.loads(line)
            op = query.pop("op")
            if op == "index" and not query:
                result = {"index": oracle.index()}
            elif op == "answer" and set(query) == {"sequence", "record_id", "branch_id", "question", "turn"}:
                result = {"answer": oracle.answer(**query)}
            elif op == "restore" and set(query) == {"queries"}:
                result = {"restored": oracle.restore(query["queries"])}
            else:
                raise ValueError("Unsupported ablation oracle RPC")
        except Exception:
            result = {"rpc_error": True}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
