"""Crash and tampering tests for durable invented oracle/worker trajectories."""
import json
from pathlib import Path
import tempfile
import unittest
from research.integrity import read_json
from research.seed17_engine import execute,load
from research.seed17_journal import content_hash,AmbiguousAttempt
from research.seed17_synthetic import cohort,SyntheticOracle,mock_send
from research.seed17_worker import predict_once
from research.seed17_audit import audit
from tools.run_experiment import planned_schedule


def setup(folder, send=None):
    inputs,refs,rules,sha=cohort(1,multi_turn=True)
    oracle=SyntheticOracle(refs,rules,sha)
    directory=Path(folder)/'run'
    manifest={'schema_version':1,'execution':'MOCK_SEED17','phase':'SEED17_MAIN',
        'durability_contract':'oracle_and_turn_receipts_v1','seed':17,
        'schedule':planned_schedule(list(inputs),[17]),'cohort_order':list(inputs),'inputs':inputs,
        'input_sha256':content_hash(inputs),'reference_index':oracle.index()}
    class Model:
        def predict(self,request):return predict_once(directory,manifest,request,send=send or mock_send)
    return directory,manifest,inputs,Model(),oracle


class DurableOracleTests(unittest.TestCase):
    def test_new_code_inventory_member_invalidates_worker_release(self):
        from research.seed17_worker import validate_code_inventory
        from research.integrity import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'research').mkdir();p=root/'research/worker.py';p.write_text('pass')
            manifest={'code_fingerprints':{'research/worker.py':digest(p)}}
            validate_code_inventory(root,manifest)
            (root/'research/new_module.py').write_text('pass')
            with self.assertRaises(ValueError):validate_code_inventory(root,manifest)

    def test_complete_two_answer_paths_bind_all_turns_and_oracle_events(self):
        with tempfile.TemporaryDirectory() as folder:
            args=setup(folder);execute(*args)
            report,_,rows=audit(args[0],synthetic=True)
            self.assertEqual(report['unique_calls'],9)
            self.assertEqual(len(list((args[0]/'turns').rglob('*.json'))),6)
            self.assertEqual(len(list((args[0]/'oracle').rglob('*.result.json'))),4)
            self.assertTrue(all(r[-1]['task']['readiness']=='ACTION_READY' for r in rows.values()))

    def test_pause_after_release_reuses_reply_and_restores_prefix_without_duplicate_provider_call(self):
        with tempfile.TemporaryDirectory() as folder:
            sent=[]
            def send(p,s):sent.append(1);return mock_send(p,s)
            directory,manifest,inputs,model,oracle=setup(folder,send)
            class PausingModel:
                def predict(self,request):
                    if request['system']=='S0' and request['turn']==1:return {'status':'paused'}
                    return model.predict(request)
            self.assertEqual(execute(directory,manifest,inputs,PausingModel(),oracle)['status'],'PAUSED')
            self.assertEqual(len(sent),1)
            saved=next((directory/'oracle').rglob('*.result.json'));original=saved.read_bytes()
            fresh=SyntheticOracle(oracle.references,oracle.rules,oracle.export_hash)
            self.assertEqual(execute(directory,manifest,inputs,model,fresh,resume=True)['status'],'COMPLETE')
            self.assertEqual(saved.read_bytes(),original)
            self.assertEqual(len(sent),9)
            self.assertEqual(len(list((directory/'oracle_replays').glob('*.result.json'))),1)
            audit(directory,synthetic=True)

    def test_interrupted_oracle_rpc_blocks_entire_run_without_releasing_again(self):
        with tempfile.TemporaryDirectory() as folder:
            args=setup(folder);original=args[4].answer;seen=[]
            def interrupted(**query):seen.append(query);original(**query);raise KeyboardInterrupt()
            args[4].answer=interrupted
            with self.assertRaises(KeyboardInterrupt):execute(*args)
            self.assertEqual(len(seen),1)
            self.assertEqual(len(list((args[0]/'calls').glob('*.json'))),1)
            with self.assertRaisesRegex(AmbiguousAttempt,'ORACLE_INTERRUPTED'):
                execute(*args,resume=True)
            self.assertEqual(len(seen),1)

    def test_sealed_resume_rejects_changed_result_even_when_its_self_hash_is_recomputed(self):
        with tempfile.TemporaryDirectory() as folder:
            args=setup(folder);execute(*args)
            p=next((args[0]/'initial').glob('*.json'));obj=read_json(p)
            obj['row']['task']['intended_goal']='TAMPERED';obj['sha256']=content_hash(obj['row']);p.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):execute(*args,resume=True)

    def test_oracle_event_or_turn_cannot_be_removed_from_seal_and_still_audit(self):
        for target in ('oracle','turns'):
            with self.subTest(target=target),tempfile.TemporaryDirectory() as folder:
                args=setup(folder);execute(*args)
                p=next((args[0]/target).rglob('*.result.json' if target=='oracle' else '*.json'))
                p.unlink()
                seal=args[0]/'seal.json';data=read_json(seal);data['files'].pop(p.relative_to(args[0]).as_posix());seal.write_text(json.dumps(data))
                with self.assertRaises((ValueError,AmbiguousAttempt)):
                    audit(args[0],synthetic=True)


if __name__=='__main__':unittest.main()
