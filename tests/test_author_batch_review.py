"""Synthetic-only author-signoff regression; no protected dataset is annotated."""
import json
from pathlib import Path
import tempfile
import unittest

from research.annotation_store import AnnotationStore
from research.reference_schema import reference_template
from tools.review_author_batch import approve_batch, preflight, _hash, _html_page


def task(ready, destination="shelf A"):
    actions=[{"action_id":"a1","capability_id":"move",
              "arguments":{"object":{"type":"object","value":"blue cup","evidence":["scene"]}},
              "constraints":[]}]
    if ready:
        actions[0]["arguments"]["destination"]={
            "type":"location","value":destination,
            "evidence":["dialogue/0"] if destination=="shelf A" else ["instruction"]}
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
                               "reference_task":task(True),"evidence_claims":claims(True,True)}])
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


if __name__=="__main__":
    unittest.main()
