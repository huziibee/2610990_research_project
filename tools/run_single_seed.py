"""Seed-17 coordinator. Default is read-only readiness; protected launch is gated."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import read_json, read_jsonl, digest
from research.seed17_engine import execute
from research.seed17_journal import content_hash, write_json
from research.single_seed_plan import schedules


def fingerprints(root=ROOT):
    return {p.relative_to(root).as_posix(): digest(p) for folder in ("research", "tools", "tests")
            for p in (root / folder).rglob("*.py")}


def readiness(bundle=None):
    args = [sys.executable, str(ROOT / "tools/check_seed17_readiness.py")]
    if bundle:
        args += ["--bundle", str(bundle)]
    process = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    result = json.loads(process.stdout)
    if process.returncode != (0 if result.get("ready") else 2) or result.get("benchmark_executed") is not False:
        raise ValueError("Invalid isolated readiness reply")
    return result


def export_smoke(directory, manifest, oracle_audit=None):
    """Create reviewable live development evidence, without manufacturing success."""
    from research.seed17_engine import load
    directory = Path(directory)
    exports = directory.parent / (directory.name + "_evidence")
    exports.mkdir(exist_ok=True)
    for item in manifest["schedule"]:
        path = directory / "initial" / f"{item['sequence']:06d}.json"
        if not path.exists():
            continue
        row = load(path)
        calls = [read_json(directory / "calls" / (cid + ".json")) for cid in row["calls"]]
        evidence = exports / ("evidence_" + item["system"])
        evidence.mkdir(exist_ok=True)
        prediction = {**row, "execution": "LIVE_DEVELOPMENT", "original_execution": manifest["execution"],
                      "inference_calls": len(calls), "phase": "INITIAL_PREDICTION"}
        if not (evidence / "prediction.json").exists():
            write_json(evidence / "prediction.json", prediction)
            from research.single_seed_plan import write_exclusive
            write_exclusive(evidence / "calls.jsonl", "".join(json.dumps({**c, "execution": "LIVE_DEVELOPMENT",
                "original_execution": manifest["execution"]}) + "\n" for c in calls))
    if (directory / "seal.json").is_file() and not (exports / "live_multi_turn.json").exists():
        detail={"directory":directory.relative_to(ROOT).as_posix(),"seal_sha256":digest(directory/"seal.json"),"code_fingerprints":manifest["code_fingerprints"]}
        if manifest.get("durability_contract") == "oracle_and_turn_receipts_v1":
            # Original per-query receipts survive process restarts; a fresh
            # process's in-memory audit is not the complete conversation.
            events = [load(p) for p in sorted((directory/"oracle").rglob("*.result.json"))]
            oracle_audit = {"events":events,"fixture_only":True}
            detail["oracle_audit_source"] = "durable_per_query_receipts"
        if oracle_audit is not None:
            write_json(exports/"oracle_audit.json",oracle_audit)
            detail["oracle_audit"]={"path":(exports/"oracle_audit.json").relative_to(ROOT).as_posix(),"sha256":digest(exports/"oracle_audit.json")}
        write_json(exports/"live_multi_turn.json",detail)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="Run 200 synthetic predictions and all fixture trajectories")
    mode.add_argument("--live-smoke", action="store_true", help="Synthetic only: S0/S1 plus two approved fixture replies")
    mode.add_argument("--execute", action="store_true", help="Future protected launch; requires signed-off release and authorization")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    clients = []
    try:
        if not (args.mock or args.live_smoke or args.execute):
            report = readiness(args.bundle)
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 2
        if args.execute:
            if not args.bundle or not readiness(args.bundle)["ready"]:
                raise ValueError("Protected release not ready; no model process created")
            from research.seed17_processes import OracleProcess
            oracle = OracleProcess(ROOT, args.bundle.resolve())
            clients.append(oracle)
            index = oracle.index()
            config = read_json(ROOT / "protocol/gemma4_seed17_v1.json")
            output = ROOT / config["execution_directory"]
            if args.output and args.output.resolve() != output.resolve():
                raise ValueError("No reroll: freeze fixes one execution directory")
            inputs = {r["record_id"]: r for r in read_jsonl(ROOT / "research_data/model_inputs/evaluation_100.jsonl")}
            schedule = schedules()[0]
            execution = "LIVE_SEED17"
            from research.seed17_author_review import policy
            selected = policy(ROOT)
            release = {"bundle_sha256": digest(args.bundle), "release_checked": True,
                "review_protocol": {"review_protocol":selected["protocol_id"], "author":selected["author"],
                                    "receipt_sha256":selected["release"]["receipt_sha256"]}}
        else:
            if args.bundle:
                raise ValueError("Development does not consume protected bundles")
            from research.seed17_synthetic import cohort, SyntheticOracle
            from tools.run_experiment import planned_schedule
            if args.live_smoke:
                from research.seed17_smoke_fixture import fixture
                from research.seed17_processes import SmokeOracleProcess
                inputs,_ = fixture()
                oracle=SmokeOracleProcess(ROOT);clients.append(oracle)
            else:
                inputs, refs, rules, export_hash = cohort(100)
                oracle = SyntheticOracle(refs, rules, export_hash)
            index = oracle.index()
            schedule = planned_schedule(list(inputs), [17])
            execution = "LIVE_SEED17_SMOKE" if args.live_smoke else "MOCK_SEED17"
            if not args.output:
                raise ValueError("Development requires a fresh explicit output directory")
            output = args.output.resolve()
            parent = ROOT / ("runs/development" if args.live_smoke else "runs/mock_seed17")
            if not output.is_relative_to(parent) or output == parent:
                raise ValueError("Development output outside designated directory")
            release = {"release_checked": False}
        manifest = {"schema_version": 1, "execution": execution, "phase":"SEED17_MAIN",
                    "durability_contract":"oracle_and_turn_receipts_v1", "seed": 17, "schedule": schedule,
                    "execution_id": output.resolve().relative_to(ROOT).as_posix(),
                    "cohort_order": list(inputs), "inputs": inputs, "input_sha256": content_hash(inputs),
                    "reference_index": index, "code_fingerprints": fingerprints(),
                    "protocol_sha256": digest(ROOT / "protocol/gemma4_seed17_v1.json"),
                    "evaluation_fingerprints":{name:digest(ROOT/name) for name in (
                        "protocol/seed17/judge_v1.json", "protocol/seed17/judge_rubric_v1.json",
                        "protocol/seed17/AUTHOR_APPROVED_AGENT_ASSISTED_v1.json")}, **release}
        if args.mock:
            from research.seed17_worker import predict_once
            from research.seed17_synthetic import mock_send
            class Model:
                def predict(self, request):
                    return predict_once(output, manifest, request, send=mock_send)
            model = Model()
        else:
            from research.seed17_processes import ModelProcess
            model = ModelProcess(ROOT, output)
            clients.append(model)
        result = execute(output, manifest, inputs, model, oracle, resume=args.resume)
        if args.live_smoke:
            export_smoke(output, manifest, oracle.audit())
        if result["status"].startswith("COMPLETE"):
            from research.seed17_audit import audit
            result["audit"] = audit(output, synthetic=not args.execute)[0]
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
