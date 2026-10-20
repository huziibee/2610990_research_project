"""Invented archives only. No provider, secrets or private study data."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from research.integrity import digest
from tools.audit_seed17_candidate_evidence import audit, ROOT
import tools.probe_seed17_wire_codec as runner


class CandidateEvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'runs/provider_diagnostics';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)/'archive'
        original=runner.WireBackend
        class FixtureBackend(original):
            def __init__(self,*a,**kw):
                super().__init__(*a,**kw)
                self.settings=replace(self.settings,model='MOCK_CODEC_ONLY')
        with patch.object(runner,'WireBackend',FixtureBackend),patch('builtins.print'):
            result=runner.run(self.directory,mock=True,attempts=1)
        self.assertTrue(result['complete'])

    def reseal(self):
        seal=self.directory/'diagnostic_seal.json'
        obj=json.loads(seal.read_text())
        obj['files']={p.relative_to(self.directory).as_posix():digest(p) for p in self.directory.rglob('*') if p.is_file() and p!=seal}
        seal.write_text(json.dumps(obj))

    def change(self,name,fn):
        p=self.directory/name;obj=json.loads(p.read_text());fn(obj);p.write_text(json.dumps(obj));self.reseal()

    def test_valid_full_mock_is_auditable_but_never_live(self):
        result=audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)
        self.assertEqual(result['actual_calls'],9)
        self.assertFalse(result['registered_study_release'])
        with self.assertRaisesRegex(ValueError,'MOCK_IS_NOT_LIVE'):
            audit(self.directory,'MOCK_CODEC_ONLY')

    def test_actual_model_cannot_be_relabelled(self):
        with self.assertRaisesRegex(ValueError,'WRONG_MODEL'):
            audit(self.directory,'different-model',require_live=False)

    def test_changed_file_hash_rejected(self):
        (self.directory/'S0/calls.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'ARCHIVE_HASH_MISMATCH'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)

    def test_resealed_modified_output_still_rejected(self):
        self.change('S0/calls.json',lambda rows: rows[0].update(output_text='{"wrong":true}'))
        with self.assertRaisesRegex(ValueError,'RAW_OUTPUT_CHANGED'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)

    def test_missing_claim_rejected_even_after_reseal(self):
        next((self.directory/'S0/requests').glob('*.claim.json')).unlink();self.reseal()
        with self.assertRaisesRegex(ValueError,'MISSING_CLAIM'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)

    def test_mismatched_dialogue_rejected(self):
        self.change('S0/calls.json',lambda rows: rows[1]['input'].update(dialogue=[]))
        with self.assertRaisesRegex(ValueError,'DIALOGUE_OR_SOURCE_CHANGED'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)

    def test_changed_summary_is_not_accepted_as_verified(self):
        self.change('summary.json',lambda row: row.update(complete=False))
        with self.assertRaisesRegex(ValueError,'SUMMARY_DISAGREES'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)

    def test_deleted_terminal_turn_rejected(self):
        self.change('S1/trajectory.json',lambda row: row['trajectory'].pop())
        with self.assertRaisesRegex(ValueError,'QUALIFICATION_FAILED'):
            audit(self.directory,'MOCK_CODEC_ONLY',require_live=False)


if __name__=='__main__':unittest.main()
