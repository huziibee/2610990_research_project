"""No implicit launch, secret propagation, result fabrication or checkpoint overwrite."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
from tools import finish_five_seed as pipeline
from research.five_seed_delivery import verify_results
from research.seed17_journal import write_json
from research.seed17_processes import ProcessClient


class FiveSeedPipelineTests(unittest.TestCase):
    def test_default_cli_is_read_only_without_key_or_network(self):
        with patch.object(sys,'argv',['finish_five_seed.py']),patch.object(pipeline,'preflight',side_effect=AssertionError('not allowed')),patch('sys.stdout',new_callable=io.StringIO) as out:
            self.assertEqual(pipeline.main(),0)
            self.assertEqual(json.loads(out.getvalue())['status'],'READ_ONLY')

    def test_missing_model_credential_stops_before_private_staging(self):
        with patch.dict(os.environ,{},clear=True),patch('gemini_prompt.load_local_env'),patch('tools.stage_seed17_private_release.stage') as stage:
            with self.assertRaisesRegex(ValueError,'MODEL_CREDENTIAL_NOT_AVAILABLE'):pipeline.preflight()
            stage.assert_not_called()

    def test_missing_private_release_never_constructs_model(self):
        with patch.object(pipeline,'preflight',side_effect=ValueError('REFERENCE_KEY_NOT_AVAILABLE')),patch.object(pipeline,'run_protected') as launch:
            with self.assertRaises(ValueError):pipeline.finish()
            launch.assert_not_called()

    def test_invalid_budget_never_enters_preflight(self):
        with patch.object(pipeline,'preflight') as preflight:
            for value in (-1,True,1.2):
                with self.assertRaises(ValueError):pipeline.finish(checkpoint_requests=value)
            preflight.assert_not_called()

    def test_progress_state_is_atomic_and_contains_no_secret(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';pipeline.save_state(p,{'stage':'MAIN'})
            pipeline.save_state(p,{'stage':'ABLATIONS'})
            self.assertEqual(json.loads(p.read_text()),{'stage':'ABLATIONS'})
            self.assertFalse(p.with_suffix('.pending').exists())

    def test_changed_code_checkpoint_never_restarts_protected_scope(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);write_json(directory/'state.json',{'binding':{'stale':True},'stage':'MAIN'})
            with patch.object(pipeline,'STATE_ROOT',directory),patch.object(pipeline,'preflight',return_value={}),patch.object(pipeline,'run_protected') as launch:
                with self.assertRaisesRegex(ValueError,'PIPELINE_CODE_OR_RUNTIME_CHANGED'):pipeline.finish()
                launch.assert_not_called()
                self.assertTrue((directory/'state.json').exists())

    def test_model_rpc_excludes_private_archive_key(self):
        child=MagicMock();child.stdout.readline.return_value='{"status":"ok"}\n'
        with patch.dict(os.environ,{'AUTHOR_REVIEW_AES_KEY_BASE64':'SYNTHETIC_SECRET_DO_NOT_LOG','GEMINI_API_KEY':'SYNTHETIC_GENERATOR_KEY'}),patch('subprocess.Popen',return_value=child) as popen:
            c=ProcessClient(pipeline.ROOT,'research.five_seed_runtime',[],session=True,excluded_env=('AUTHOR_REVIEW_AES_KEY_BASE64',))
            c.call({'x':1})
            env=popen.call_args.kwargs['env']
            self.assertNotIn('AUTHOR_REVIEW_AES_KEY_BASE64',env)
            self.assertEqual(env['GEMINI_API_KEY'],'SYNTHETIC_GENERATOR_KEY')
            c.close()

    def test_five_seed_model_imports_no_reference_or_semantic_modules(self):
        code="import sys; import research.five_seed_runtime; bad=[x for x in sys.modules if x.startswith('research.') and any(y in x for y in ('reference','oracle','semantic','annotation','judge'))]; assert not bad,bad"
        result=subprocess.run([sys.executable,'-c',code],cwd=pipeline.ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_synthetic_results_cannot_be_reported_as_protected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'runs/readiness/fake';out.mkdir(parents=True)
            write_json(out/'analysis_seal.json',{'synthetic':True})
            with self.assertRaisesRegex(ValueError,'Synthetic output'):verify_results(root,out,root/'none')

if __name__=='__main__':unittest.main()
