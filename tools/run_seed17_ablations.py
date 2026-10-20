"""Seed-17 five-ablation runner. Default plans; --mock uses synthetic fixtures only."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import digest, read_json, read_jsonl
from research.seed17_ablation import (schedule, validate_prediction, intervention_record,
                                     validate_authorization, EXECUTION_DIRECTORY, SCOPE)
from research.seed17_ablation_audit import audit
from research.seed17_engine import execute
from research.seed17_journal import content_hash, write_json
from research.seed17_processes import ProcessClient
from tools.run_ablations import INTERVENTIONS
from tools.run_experiment import IDS
from tools.run_single_seed import fingerprints


class ModelProcess(ProcessClient):
    def __init__(self, root, directory):
        super().__init__(root, "research.seed17_ablation_worker", [directory], session=True)
    def predict(self, query):
        return self.call(query)


class OracleProcess(ProcessClient):
    def __init__(self, root, bundle, authorization):
        super().__init__(root, "research.seed17_ablation_oracle", [bundle, authorization])
    def index(self):
        return self.call({"op": "index"})["index"]
    def answer(self, **query):
        return self.call({"op": "answer", **query})["answer"]
    def restore(self, queries):
        if self.call({"op": "restore", "queries": queries}).get("restored") is not True:
            raise ValueError("Ablation oracle restoration rejected")


def make_manifest(root, output, inputs, index, *, release=None):
    root = Path(root).resolve()
    return {"schema_version": 1, "phase": "SEED17_ABLATIONS", "seed": 17,
        "execution": "LIVE_SEED17" if release else "MOCK_SEED17",
        "durability_contract": "oracle_and_turn_receipts_v1",
        "schedule": schedule(list(inputs)), "cohort_order": list(inputs),
        "execution_id": Path(output).resolve().relative_to(root).as_posix(),
        "inputs": inputs, "input_sha256": content_hash(inputs), "reference_index": index,
        "interventions": {a: intervention_record(root, a) for a in INTERVENTIONS},
        "ablation_contract_sha256": digest(root / "protocol/seed17/ablation_contract_v1.json"),
        "code_fingerprints": fingerprints(root),
        "protocol_sha256": digest(root / "protocol/gemma4_seed17_v1.json"),
        "evaluation_fingerprints": {name: digest(root / name) for name in (
            "protocol/seed17/judge_v1.json", "protocol/seed17/judge_rubric_v1.json",
            "protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json")},
        **(release or {"release_checked": False})}


def run(directory, manifest, inputs, model, oracle, *, resume=False):
    return execute(directory, manifest, inputs, model, oracle, resume=resume,
        validate_prediction=lambda task, current, planned: validate_prediction(task, current, planned["ablation"]),
        sealed_audit=lambda directory, manifest: audit(directory, synthetic=manifest["execution"] == "MOCK_SEED17")[0])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--mock", action="store_true")
    modes.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    clients = []
    try:
        if not args.mock and not args.execute:
            print(json.dumps({"status": "REGISTERED_PLAN_ONLY", "benchmark_executed": False,
                "initial_predictions": 500, "initial_requests": 1000, "maximum_requests_with_five_replies": 6000,
                "scope": SCOPE, "interventions": INTERVENTIONS, "requires_separate_ablation_authorization": True,
                "execution_directory": EXECUTION_DIRECTORY}, indent=2))
            return 0
        if args.mock:
            if args.bundle or args.authorization or not args.output:
                raise ValueError("Mock requires fresh synthetic output; no protected bundle or authorization")
            output = args.output.resolve()
            parent = ROOT / "runs/mock_seed17_ablations"
            if not output.is_relative_to(parent) or output == parent:
                raise ValueError("Mock output outside designated parent")
            from research.seed17_synthetic import cohort, SyntheticOracle
            inputs, refs, rules, export_hash = cohort(100)
            oracle = SyntheticOracle(refs, rules, export_hash)
            manifest = make_manifest(ROOT, output, inputs, oracle.index())
            from research.seed17_ablation_worker import predict_once
            from research.seed17_ablation_synthetic import mock_send
            class Model:
                def predict(self, request):
                    return predict_once(output, manifest, request, send=mock_send)
            model = Model()
        else:
            if not args.bundle or not args.authorization:
                raise ValueError("Protected ablations require separate explicit authorization and main bundle")
            for path in (args.bundle, args.authorization):
                if not path.resolve().is_relative_to(ROOT):
                    raise ValueError("Authorization or bundle outside workspace")
            bundle, auth = read_json(args.bundle), read_json(args.authorization)
            validate_authorization(ROOT, bundle, auth)
            output = ROOT / EXECUTION_DIRECTORY
            if args.output and args.output.resolve() != output.resolve():
                raise ValueError("No reroll: fixed ablation execution directory")
            oracle = OracleProcess(ROOT, args.bundle.resolve(), args.authorization.resolve())
            clients.append(oracle)
            index = oracle.index()
            from research.seed17_author_review import policy
            selected = policy(ROOT)
            # Protected inputs are read only after complete main and separate ablation gates.
            source = ROOT / "research_data/model_inputs/evaluation_100.jsonl"
            expected_source = read_json(ROOT / "research_data/MANIFEST.json")["derived_files"]["model_inputs/evaluation_100.jsonl"]["sha256"]
            if digest(source) != expected_source:
                raise ValueError("Ablation source differs from frozen model inputs")
            inputs = {r["record_id"]: r for r in read_jsonl(source)}
            if digest(source) != expected_source:
                raise ValueError("Ablation source changed while reading")
            if set(inputs) != set(IDS):
                raise ValueError("Protected source cohort differs")
            manifest = make_manifest(ROOT, output, inputs, index, release={"release_checked": True,
                "bundle_path": args.bundle.resolve().relative_to(ROOT).as_posix(), "bundle_sha256": digest(args.bundle),
                "input_file_sha256": expected_source,
                "review_protocol": {"review_protocol": selected["protocol_id"], "author": selected["author"],
                                    "receipt_sha256": selected["release"]["receipt_sha256"]},
                "ablation_authorization": auth, "ablation_authorization_sha256": content_hash(auth)})
            model = ModelProcess(ROOT, output)
            clients.append(model)
        result = run(output, manifest, inputs, model, oracle, resume=args.resume)
        if result["status"].startswith("COMPLETE"):
            result["audit"] = audit(output, synthetic=args.mock)[0]
            if args.mock:
                evidence = output.parent / (output.name + "_evidence")
                evidence.mkdir(exist_ok=True)
                if not (evidence / "ablation_audit.json").exists():
                    write_json(evidence / "ablation_audit.json", result["audit"])
        print(json.dumps(result, indent=2))
        return 0 if result["status"].startswith("COMPLETE") else 2
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "BLOCKED", "benchmark_executed": None if args.execute and clients else False,
            "error_type": type(exc).__name__, "reason": str(exc)[:250]}, indent=2))
        return 2
    finally:
        for client in reversed(clients):
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
