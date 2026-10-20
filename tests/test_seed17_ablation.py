"""Registered interventions and crash-safe trajectories, exclusively synthetic."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.ablations import SCENE_MASK
from research.gemini_backend import InferenceError
from research.integrity import read_json
from research.seed17_ablation import prepared_input, schedule, intervention_record, validate_prediction, validate_authorization, SCOPE, EXECUTION_DIRECTORY
from research.seed17_ablation_audit import audit
from research.seed17_ablation_synthetic import mock_send
from research.seed17_ablation_worker import predict_once, validate_release
from research.seed17_engine import load
from research.seed17_journal import AmbiguousAttempt, content_hash, write_json
from research.seed17_synthetic import cohort, SyntheticOracle
from tools.run_ablations import INTERVENTIONS, planned_ablation_schedule
from tools.run_experiment import IDS
from research.integrity import digest
from tools.run_seed17_ablations import ROOT, main, make_manifest, run


class Seed17AblationTests(unittest.TestCase):
    def make_run(self, count=2):
        temp = tempfile.TemporaryDirectory(dir=ROOT / "runs")
        self.addCleanup(temp.cleanup)
        output = Path(temp.name) / "ablation"
        inputs, refs, rules, export_hash = cohort(count)
        oracle = SyntheticOracle(refs, rules, export_hash)
        manifest = make_manifest(ROOT, output, inputs, oracle.index())
        return output, inputs, oracle, manifest

    def model(self, output, manifest, send=mock_send):
        class Model:
            def predict(self, query):
                return predict_once(output, manifest, query, send=send)
        return Model()

    def test_schedule_preserves_historical_seed17_rows_and_pairing(self):
        inputs, *_ = cohort(100)
        rows = schedule(list(inputs))
        self.assertEqual([{k:v for k,v in r.items() if k != "system"} for r in rows],
                         planned_ablation_schedule(list(inputs), [17]))
        self.assertEqual(len(rows), 500)
        self.assertEqual({(r["record_id"],r["ablation"]) for r in rows},
                         {(c,a) for c in inputs for a in INTERVENTIONS})
        self.assertEqual({r["system"] for r in rows}, {"S1"})

    def test_context_interventions_remove_exact_declared_field_without_mutation(self):
        inputs, *_ = cohort(1)
        source = next(iter(inputs.values()))
        source["dialogue"] = ["User answer (simulated): Shelf A"]
        baseline = copy.deepcopy(source)
        for condition in INTERVENTIONS:
            transformed = prepared_input(source, condition)
            expected = copy.deepcopy(source)
            if condition == "scene": expected["scene"] = SCENE_MASK
            if condition == "dialogue": expected["dialogue"] = []
            self.assertEqual(transformed, expected)
        self.assertEqual(source, baseline)

    def test_registered_mechanism_differences_are_explicit(self):
        records = {a:intervention_record(ROOT,a) for a in INTERVENTIONS}
        self.assertEqual(records["goal_first"]["stages"], ["S1.context","S1.context_ground"])
        for a,r in records.items():
            self.assertEqual(r["settings"]["max_output_tokens"],2048)
            self.assertEqual(r["check_dependency_consistency"], a != "dependency_checking")
        self.assertNotEqual(records["structured_grounding"]["prompts"]["S1.ground"],
                            records["scene"]["prompts"]["S1.ground"])

    def test_complete_synthetic_trajectories_masks_and_no_duplicate_resume(self):
        output, inputs, oracle, manifest = self.make_run()
        result = run(output,manifest,inputs,self.model(output,manifest),oracle)
        self.assertEqual(result["status"],"COMPLETE")
        report, _, predictions = audit(output,synthetic=True)
        self.assertEqual(report["initial_predictions"],10)
        self.assertEqual(report["denominators"],{a:2 for a in INTERVENTIONS})
        outcomes = {}
        for planned in manifest["schedule"]:
            path=output/"trajectories"/f"{planned['sequence']:06d}"/(content_hash("branch-a")+".json")
            outcomes[(planned["record_id"],planned["ablation"])]=load(path)["termination"]
        self.assertTrue(all(v == ("ANSWER_UNAVAILABLE" if a=="dialogue" else "ACTION_READY")
                            for (c,a),v in outcomes.items()))
        for call_path in (output/"calls").glob("*.json"):
            call=read_json(call_path)
            self.assertNotIn("SYNTHETIC_HIDDEN_REFERENCE_SENTINEL",json.dumps(call))
        requests=len(list((output/"requests").glob("*.claim.json")))
        self.assertEqual(run(output,manifest,inputs,self.model(output,manifest),oracle,resume=True)["status"],"COMPLETE_ALREADY_SEALED")
        self.assertEqual(requests,len(list((output/"requests").glob("*.claim.json"))))
        with (output/"seal.json").open("a") as stream:stream.write(" ")
        # Content hashes bind all members; append a call corruption to exercise it.
        path=next((output/"calls").glob("*.json"))
        path.write_text(path.read_text()+" ")
        with self.assertRaises(ValueError):audit(output,synthetic=True)

    def test_http_failure_is_durable_and_never_retried(self):
        for status in (500, 502, 503, 504):
            with self.subTest(http_status=status):
                self.check_http_failure_is_durable_and_never_retried(status)

    def check_http_failure_is_durable_and_never_retried(self, http_status):
        output,inputs,oracle,manifest=self.make_run(1)
        sends=[]
        def failed(payload,settings):
            sends.append(payload)
            raise InferenceError("synthetic",code="HTTP_FAILURE",http_status=http_status)
        model=self.model(output,manifest,failed)
        self.assertEqual(run(output,manifest,inputs,model,oracle)["status"],"PAUSED")
        self.assertEqual(len(sends),1)
        first=load(output/"initial/000001.json")
        self.assertEqual(first["status"],"error")
        receipts=list((output/"requests").glob("*.done.json"))
        self.assertEqual(len(receipts),1)
        receipt=read_json(receipts[0])
        self.assertEqual(receipt["status"],"ERROR")
        self.assertEqual(receipt["http_status"],http_status)
        failed_receipt_hash=digest(receipts[0])
        # Explicit resume advances the remaining plan; the failed request stays in denominator.
        self.assertEqual(run(output,manifest,inputs,self.model(output,manifest),oracle,resume=True)["status"],"COMPLETE")
        self.assertEqual(len(sends),1)
        self.assertEqual(digest(receipts[0]),failed_receipt_hash)
        report=audit(output,synthetic=True)[0]
        self.assertEqual(sum(report["initial_failures"].values()),1)

    def test_unresolved_provider_claim_stops_entire_run_before_any_call(self):
        output,inputs,oracle,manifest=self.make_run(1)
        output.mkdir()
        write_json(output/"run_manifest.json",manifest)
        (output/"requests").mkdir()
        write_json(output/"requests/interrupted.claim.json",{"request_hash":"unresolved"})
        with self.assertRaises(AmbiguousAttempt):
            run(output,manifest,inputs,self.model(output,manifest),oracle,resume=True)
        self.assertFalse((output/"initial").exists())

    def test_protected_cli_requires_separate_authorization_before_reads(self):
        with patch("tools.run_seed17_ablations.read_jsonl",side_effect=AssertionError("protected read")):
            self.assertEqual(main(["--execute"]),2)

    def test_worker_requires_exact_code_inventory_before_provider_calls(self):
        _,_,_,manifest=self.make_run(1)
        validate_release(ROOT,manifest)
        missing=copy.deepcopy(manifest)
        missing["code_fingerprints"].pop("research/seed17_ablation_worker.py")
        with self.assertRaisesRegex(ValueError,"inventory"):
            validate_release(ROOT,missing)
        added=copy.deepcopy(manifest)
        added["code_fingerprints"]["research/unregistered_added_module.py"]="synthetic"
        with self.assertRaisesRegex(ValueError,"inventory"):
            validate_release(ROOT,added)

    def test_resealed_call_task_tampering_cannot_override_provider_receipt(self):
        output,inputs,oracle,manifest=self.make_run(1)
        run(output,manifest,inputs,self.model(output,manifest),oracle)
        audit(output,synthetic=True)
        seq=manifest["schedule"][0]["sequence"]
        initial_path=output/"initial"/f"{seq:06d}.json"
        original=load(initial_path)
        task=copy.deepcopy(original["task"])
        task["intended_goal"]="Invented replacement output never returned by the synthetic provider"
        def rewrite(path,value):
            path.write_text(json.dumps(value,ensure_ascii=False)+"\n",encoding="utf-8")
        def replace_task(path,*,trajectory=False):
            row=load(path)
            if trajectory:row["trajectory"][0]["task"]=task
            else:row["task"]=task
            rewrite(path,{"row":row,"sha256":content_hash(row)})
        replace_task(initial_path)
        for path in (output/"trajectories"/f"{seq:06d}").glob("*.json"):
            replace_task(path,trajectory=True)
        for path in (output/"turns"/f"{seq:06d}").rglob("000000.json"):
            replace_task(path)
        call_path=output/"calls"/(original["calls"][-1]+".json")
        call=read_json(call_path)
        call["output_text"]=json.dumps(task)
        rewrite(call_path,call)
        # Recompute every unkeyed local hash and seal, leaving durable provider
        # response bytes unchanged. Structural consistency alone must not pass.
        from research.single_seed_plan import fingerprint
        completed=load(initial_path)
        rewrite(output/"initial_journal"/f"{seq:06d}.done.json",
                {**completed,"prediction_sha256":fingerprint([completed])})
        seal=read_json(output/"seal.json")
        seal["files"]={name:digest(output/name) for name in seal["files"]}
        rewrite(output/"seal.json",seal)
        with self.assertRaises(ValueError):audit(output,synthetic=True)

    def test_second_human_is_not_invented_and_main_authorization_cannot_grant_ablations(self):
        freeze={"study_id":"gemma4-seed17-v1","base_artifacts_sha256":"synthetic-artifacts"}
        bundle={"artifacts":{"technical_freeze":{"sha256":"synthetic-freeze"}}}
        auth={"status":"EXPLICIT_USER_ABLATION_AUTHORIZATION","authorization_granted":True,
            "study_id":freeze["study_id"],"scope":SCOPE,"authorized_by":"SYNTHETIC_AUTHORIZATION_FIXTURE_NOT_REAL",
            "authorized_utc":"2026-10-20T00:00:00+00:00","verbatim_authorization":"Synthetic test fixture only",
            "technical_freeze_sha256":"synthetic-freeze","base_artifacts_sha256":"synthetic-artifacts",
            "ablation_contract_sha256":digest(ROOT/"protocol/seed17/ablation_contract_v1.json"),
            "schedule_sha256":content_hash(planned_ablation_schedule(IDS,[17])),"execution_directory":EXECUTION_DIRECTORY}
        with patch("research.seed17_gate.check_readiness",return_value={"ready":True}), \
             patch("research.seed17_freeze.validate_technical_freeze",return_value=freeze):
            self.assertEqual(validate_authorization(ROOT,bundle,auth),auth)
            for field,value in (("scope","seed17_main_with_approved_clarification_only"),
                                ("ablation_contract_sha256","tampered"),("schedule_sha256","tampered"),
                                ("execution_directory","runs/evaluation/reroll"),("authorized_by","[Waiting]")):
                altered={**auth,field:value}
                with self.assertRaises(ValueError):validate_authorization(ROOT,bundle,altered)

    def test_dependency_removal_keeps_schema_and_argument_validation(self):
        inputs,*_=cohort(1)
        item=next(iter(inputs.values()))
        from research.gemini_backend import GeminiBackend
        from research.seed17_ablation import predict
        task=predict(GeminiBackend(transport=mock_send),item,"dependency_checking")
        task["dependencies"]=[{"source":"/actions/0","target":"/actions/0","relation":"before"}]
        self.assertEqual(validate_prediction(task,item,"dependency_checking"),task)
        with self.assertRaises(ValueError):validate_prediction(task,item,"goal_first")
        task["actions"][0]["arguments"]["object"]["value"]=123
        with self.assertRaises(ValueError):validate_prediction(task,item,"dependency_checking")

    def test_crash_after_provider_receipt_replays_without_duplicate_send(self):
        output,inputs,oracle,manifest=self.make_run(1)
        sent=[]
        def send(payload,settings):
            sent.append(content_hash(payload))
            return mock_send(payload,settings)
        actual=self.model(output,manifest,send)
        class Interrupted:
            failed=False
            def predict(self,request):
                result=actual.predict(request)
                if request["turn"]==1 and not self.failed:
                    self.failed=True
                    raise RuntimeError("synthetic crash after receipt before coordinator checkpoint")
                return result
        with self.assertRaises(RuntimeError):run(output,manifest,inputs,Interrupted(),oracle)
        self.assertEqual(run(output,manifest,inputs,actual,oracle,resume=True)["status"],"COMPLETE")
        claims=list((output/"requests").glob("*.claim.json"))
        self.assertEqual(len(sent),len(claims))
        audit(output,synthetic=True)

    def test_five_answer_limit_preserves_valid_unresolved_terminal_tasks(self):
        output,all_inputs,oracle,_=self.make_run(5)
        inputs={"SYNTHETIC-005":all_inputs["SYNTHETIC-005"]}
        index={"SYNTHETIC-005":oracle.index()["SYNTHETIC-005"]}
        manifest=make_manifest(ROOT,output,inputs,index)
        def unresolved(payload,settings):
            response=mock_send(payload,settings)
            part=response["candidates"][0]["content"]["parts"][0]
            value=json.loads(part["text"])
            if value.get("readiness")=="ACTION_READY":
                value.update(readiness="CLARIFY",clarification_question="What priority?",
                    unresolved=[{"field":"priority","reason":"synthetic model uncertainty persists","critical":True}])
                part["text"]=json.dumps(value)
            return response
        self.assertEqual(run(output,manifest,inputs,self.model(output,manifest,unresolved),oracle)["status"],"COMPLETE")
        for row in manifest["schedule"]:
            result=load(output/"trajectories"/f"{row['sequence']:06d}"/(content_hash("branch-a")+".json"))
            if row["ablation"]!="dialogue":
                self.assertEqual(result["termination"],"TURN_LIMIT")
                self.assertEqual(len(result["trajectory"]),6)
        audit(output,synthetic=True)


if __name__ == "__main__":
    unittest.main()
