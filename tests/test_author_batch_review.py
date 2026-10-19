"""Synthetic-only author-signoff regression; no protected dataset is annotated."""
import json
from pathlib import Path
import tempfile
import unittest
import shutil
import zipfile
import subprocess
import sys
from hashlib import sha256
from unittest.mock import patch

from research.annotation_store import AnnotationStore
from research.reference_schema import reference_template
from tools.review_author_batch import approve_batch, preflight, _hash, _html_page, read_author_attestation
from tools.start_author_review import bootstrap


def task(ready, destination="shelf A", branch=False):
    actions=[{"action_id":"a1","capability_id":"move",
              "arguments":{"object":{"type":"object","value":"blue cup","evidence":["scene"]}},
              "constraints":[]}]
    if ready:
        actions[0]["arguments"]["destination"]={
            "type":"location","value":destination,
            "evidence":["dialogue/0"] if branch else ["instruction"]}
    return {"intended_goal":"Move the blue cup to shelf A",
            "actions":actions,
            "unresolved":[] if ready else [{"field":"destination","reason":"Not provided","critical":True}],
            "dependencies":[],
            "readiness":"ACTION_READY" if ready else "CLARIFY",
            "clarification_question":None if ready else "Where should the cup go?"}


def claims(ready, branch=False):
    values=[{"target":"/intended_goal","source":"instruction","quote":"Move the blue cup"},
            {"target":"/actions/0/capability_id","source":"capabilities",
             "quote":"move(object: object, destination: location)"},
            {"target":"/actions/0/arguments/object/value","source":"scene",
             "quote":"A blue cup"}]
    if ready:
        values.append({"target":"/actions/0/arguments/destination/value",
                       "source":"hypothetical_answer" if branch else "instruction",
                       "quote":"shelf A"})
    return values


class AuthorBatchTest(unittest.TestCase):
    def make_workspace(self, tmp):
        root=Path(tmp); ws=root/"workspace"
        files={name:root/(name+".jsonl") for name in ("source","routes","worksheet")}
        rows={name:[] for name in files}
        for i in range(1,101):
            cid=f"CA-{i:04d}";clarify=i<=26
            route={"record_id":cid,"terminal_strategy":"clarify" if clarify else "execute",
                   "strategy_sequence":["clarify"] if clarify else ["execute"]}
            rows["source"].append({"record_id":cid,"command":"Move the blue cup to shelf A" if not clarify else "Move the blue cup",
                                  "scene_context":"A blue cup is on the desk.","dialogue_history":[],
                                  "capability_context":"move(object: object, destination: location) is supported"})
            rows["routes"].append(route)
            rows["worksheet"].append(reference_template(cid,route))
        for name,file in files.items():
            file.write_text("".join(json.dumps(r)+"\n" for r in rows[name]),encoding="utf-8")
        store=AnnotationStore(ws)
        store.initialize(files["source"],files["routes"],files["worksheet"])
        for i in range(1,101):
            cid=f"CA-{i:04d}";clarify=i<=26
            ref=reference_template(cid,rows["routes"][i-1])
            if clarify:
                ref.update(reference_task=task(False),critical_unknowns=[{"field":"destination","reason":"Not provided"}],
                           evidence_claims=claims(False),
                           hypothetical_answer_branches=[{
                               "branch_id":"answer-a","question":"Where should the cup go?",
                               "field":"destination","answer":"shelf A","simulated":True,
                               "reference_task":task(True,branch=True),"evidence_claims":claims(True,True)}])
            else:
                ref.update(reference_task=task(True,"shelf A"),critical_unknowns=[],
                           evidence_claims=claims(True),
                           hypothetical_answer_branches=[])
                # Execute version uses instruction for destination, not dialogue.
            ref.update(dialogue_relevant=False,explicit_linked_dependencies=False,
                       verification_evidence="Human must confirm correct source evidence and full task")
            # Branch expected goal mentions shelf A not supported by initial instruction;
            # validation only checks source substring, semantic review remains required.
            state=store.show(cid)
            envelope={"document_type":"UNVERIFIED_HUMAN_EDITABLE_DRAFT",
                      "record_id":cid,"expected_head":state["head"],"reference":ref}
            (ws/"drafts").mkdir(exist_ok=True)
            (ws/"drafts"/(cid+".json")).write_text(json.dumps(envelope),encoding="utf-8")
        return ws,store

    def test_batch_attestation_preserves_model_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws,store=self.make_workspace(tmp)
            _,rows=preflight(ws)
            self.assertEqual((len(rows),sum(x["route"]=="clarify" for x in rows)),(100,26))
            release=approve_batch(ws,"Actual human researcher",
                                  "I inspected all model-assisted references against source.")
            self.assertEqual(release["case_count"],100)
            self.assertEqual(release["status"],"AUTHOR_REVIEWED_NOT_INDEPENDENTLY_VERIFIED")
            self.assertIs(release["independent_human_verification"],False)
            self.assertIs(release["human_author_approval_attested"],True)
            self.assertIs(release["reviewer_identity_self_attested"],True)
            self.assertIs(release["reviewer_identity_authenticated_externally"],False)
            self.assertIs(release["two_model_adjudication_reported_by_author"],False)
            self.assertIs(release["two_model_review_logs_authenticated"],False)
            self.assertEqual(len(release["references"]),100)
            self.assertTrue((ws/"author_review_export"/"author_reviewed_references_100.jsonl").exists())
            state=store.show("CA-0001")
            self.assertEqual(state["status"],"CANDIDATE")
            self.assertIs(state["adopted"],True)
            self.assertIs(state["model_assisted"],True)
            self.assertIsNone(state["verification"])
            self.assertIsNone(state["final_approval"])
            with self.assertRaisesRegex(ValueError,"Existing author approval"):
                approve_batch(ws,"Actual human researcher",
                              "I inspected all model-assisted references against source.")

    def test_two_model_report_recorded_without_fake_authentication(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws,_=self.make_workspace(tmp)
            report=approve_batch(
                ws,"Actual human researcher",
                "I independently checked all proposed interpretations against sources.",
                reported_two_models=True)
            self.assertTrue(report["two_model_adjudication_reported_by_author"])
            self.assertFalse(report["two_model_review_logs_authenticated"])
            self.assertTrue(report["human_author_approval_attested"])
            self.assertFalse(report["independent_human_verification"])


    def test_unreviewed_and_fake_identity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws,_=self.make_workspace(tmp)
            with self.assertRaises(ValueError):
                approve_batch(ws,"[Waiting for reviewer]","This is my actual review of all references")
            with self.assertRaises(ValueError):
                approve_batch(ws,"Researcher","ok")
            self.assertFalse((ws/"author_review_export").exists())

    def test_edits_are_not_overwritten_and_html_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws,store=self.make_workspace(tmp)
            _,rows=preflight(ws)
            page=_html_page(ws,rows,"synthetic-token")
            self.assertIn("I have reviewed all 100",page)
            self.assertIn('name="confirm"',page)
            self.assertIn("NOT two independent human reviews",page)
            source=ws/"drafts"/"CA-0001.json"
            draft=json.loads(source.read_text())
            draft["reference"]["author_approved_route"]="execute"
            source.write_text(json.dumps(draft),encoding="utf-8")
            with self.assertRaises(ValueError):
                preflight(ws)
            self.assertEqual(store.show("CA-0001")["revision"],0)


    def test_one_command_bootstrap_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            existing,_=self.make_workspace(tmp)
            data=root/"Data/data"
            data.mkdir(parents=True)
            (root/"annotation").mkdir()
            files={"source":"data/source_100.jsonl",
                   "routes":"data/author_approved_route_gold_100.jsonl",
                   "worksheet":"annotation/semantic_reference_template_100.jsonl"}
            paths={}
            for name,relative in files.items():
                path=root/("Data/"+relative if name!="worksheet" else relative)
                shutil.copyfile(root/(name+".jsonl"),path)
                paths[name]=path
            metadata={"case_count":100,"frozen_routes":{"execute":74,"clarify":26},
                      "sources":{
                          "data/source_100.jsonl":{"sha256":sha256(paths["source"].read_bytes()).hexdigest()},
                          "data/author_approved_route_gold_100.jsonl":{"sha256":sha256(paths["routes"].read_bytes()).hexdigest()}
                      },"files":[]}
            archive=root/"private_candidates.zip"
            with zipfile.ZipFile(archive,"w") as z:
                for i in range(1,101):
                    cid=f"CA-{i:04d}";name=f"candidates/{cid}.json"
                    content=(existing/"drafts"/(cid+".json")).read_bytes()
                    z.writestr(name,content)
                    metadata["files"].append({"path":name,"sha256":sha256(content).hexdigest()})
                z.writestr("PROVENANCE.json",json.dumps(metadata))
            destination=root/"runs/human_review_20261019"
            with patch("tools.start_author_review.verify_release"):
                first=bootstrap(archive,destination,root=root)
                second=bootstrap(archive,destination,root=root)
            self.assertEqual(first["new_drafts"],100)
            self.assertEqual(second["new_drafts"],0)
            self.assertEqual(len(preflight(destination)[1]),100)
            self.assertEqual(AnnotationStore(destination).show("CA-0001")["revision"],0)


    def test_exact_attestation_fingerprints_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws,store=self.make_workspace(tmp)
            _,rows=preflight(ws)
            att={
                "schema_version":1,
                "attestation_type":"ONE_HUMAN_AUTHOR_REVIEW_OF_MODEL_ASSISTED_CANDIDATES",
                "recorded_from":"user_explicit_statement_in_chat",
                "actor":"Actual human researcher",
                "statement":"I reviewed all one hundred candidate references and accept their suggestions.",
                "review_date":"2026-10-19",
                "approved_count":100,"clarification_count":26,
                "source_candidate_archive_sha256":"a"*64,
                "original_source_sha256":"b"*64,
                "approved_reference_sha256":{r["record_id"]:r["reference_sha256"] for r in rows},
                "model_assisted":True,"independently_human_verified":False,
                "reviewer_identity_authenticated_externally":False,
                "two_model_review_logs_authenticated":False,
                "frozen_route_changes":0,"benchmark_executed":False,
                "status":"AUTHOR_ATTESTATION_SUPPLIED_LEDGER_APPLICATION_PENDING",
                "note":"Self-attestation for synthetic test only."
            }
            path=Path(tmp)/"approval.json"
            path.write_text(json.dumps(att),encoding="utf-8")
            who,note=read_author_attestation(path,rows)
            self.assertEqual(who,"Actual human researcher")
            self.assertIn("reviewed",note)
            tampered=att.copy()
            tampered["approved_reference_sha256"]=dict(att["approved_reference_sha256"])
            tampered["approved_reference_sha256"]["CA-0001"]="0"*64
            path.write_text(json.dumps(tampered),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"differs"):
                read_author_attestation(path,rows)


    def test_direct_script_entrypoint_imports_from_outside_repo(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as elsewhere:
            proc=subprocess.run(
                [sys.executable,str(root/"tools"/"review_author_batch.py"),"--help"],
                cwd=elsewhere,text=True,capture_output=True,check=False,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn("--approval-file",proc.stdout)


if __name__=="__main__":
    unittest.main()
