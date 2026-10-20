"""Synthetic-only regression tests for versioned, unsigned technical release binding."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.integrity import digest
from research.seed17_freeze import (REQUIRED_ARTIFACTS, current_runtime, technical_record,
                                    validate_technical_freeze)
from research.seed17_gate import check_readiness
from research.seed17_journal import write_json

ROOT = Path(__file__).resolve().parents[1]


class ReadinessIntegrityTests(unittest.TestCase):
    def fixture(self, root):
        files = {}
        for name in ('research/synthetic_worker.py', 'protocol/DATA_FREEZE_20261019.json',
                     'protocol/gemini_protocol_v1.json', 'protocol/amendments/synthetic.json'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('SYNTHETIC ENGINEERING FIXTURE ONLY', encoding='utf-8')
            files[name] = digest(path)
        snapshot = root / 'snapshot.json'
        write_json(snapshot, {'files': files, 'runtime': current_runtime()})
        artifacts = {name: {'path': 'snapshot.json', 'sha256': digest(snapshot)}
                     for name in REQUIRED_ARTIFACTS}
        return {'schema_version': 5, 'artifacts': artifacts}

    def freeze(self, root, bundle):
        record = technical_record(root, bundle)
        write_json(root / 'technical.json', record)
        bundle['artifacts']['technical_freeze'] = {'path': 'technical.json', 'sha256': digest(root/'technical.json')}
        return record

    def test_unsigned_schema2_excludes_manuscript_and_pdf_but_binds_engineering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); bundle = self.fixture(root)
            record = self.freeze(root, bundle)
            self.assertEqual(record['schema_version'], 2)
            self.assertFalse(record['authorization_granted'])
            self.assertIsNone(record['signed_by'])
            self.assertFalse(any(name.startswith(('Report/', 'output/pdf/')) for name in record['files']))
            self.assertEqual(validate_technical_freeze(root, bundle), record)

    def test_each_missing_required_evidence_artifact_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); bundle = self.fixture(root)
            for name in REQUIRED_ARTIFACTS:
                bad = copy.deepcopy(bundle); del bad['artifacts'][name]
                with self.subTest(name=name), self.assertRaises(ValueError): technical_record(root, bad)

    def test_changed_runtime_is_not_merely_recorded_as_nonempty(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); bundle = self.fixture(root)
            self.freeze(root, bundle)
            for mutation in (lambda value: value.update(python='DIFFERENT'),
                             lambda value: value['dependencies'].update(websockets='0.0')):
                runtime = current_runtime(); mutation(runtime)
                with patch('research.seed17_freeze.current_runtime', return_value=runtime):
                    with self.assertRaises(ValueError): validate_technical_freeze(root, bundle)

    def test_added_or_changed_amendment_invalidates_freeze(self):
        for change in ('added', 'changed'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); bundle = self.fixture(root); self.freeze(root, bundle)
                name = 'new.json' if change == 'added' else 'synthetic.json'
                (root/'protocol/amendments'/name).write_text('CHANGED SYNTHETIC', encoding='utf-8')
                with self.assertRaises(ValueError): validate_technical_freeze(root, bundle)

    def test_changed_artifact_or_unknown_freeze_schema_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); bundle = self.fixture(root); self.freeze(root, bundle)
            bad = copy.deepcopy(bundle); bad['artifacts']['analysis_contract']['sha256'] = '0'*64
            with self.assertRaises(ValueError): validate_technical_freeze(root, bad)
            with self.assertRaises(ValueError): technical_record(root, bundle, schema_version=99)

    def test_timeout_receipt_and_unknown_interruption_never_duplicate_provider_send(self):
        from research.seed17_journal import RequestJournal, AmbiguousAttempt
        from research.gemini_backend import InferenceError, GenerationSettings
        for known in (True, False):
            with self.subTest(known=known), tempfile.TemporaryDirectory() as folder:
                sent = []
                def send(*args):
                    sent.append(1)
                    if known:
                        raise InferenceError('Synthetic timeout', code='TIMEOUT')
                    raise TimeoutError('Unclassified synthetic timeout after possible send')
                journal = RequestJournal(folder, 'SYNTHETIC_TIMEOUT_ONLY')
                with self.assertRaises(InferenceError if known else TimeoutError):
                    journal.transport('same-call', send)({}, GenerationSettings())
                before = {p.name: digest(p) for p in Path(folder).glob('*.json')}
                replay = RequestJournal(folder, 'SYNTHETIC_TIMEOUT_ONLY')
                with self.assertRaises(InferenceError if known else AmbiguousAttempt):
                    replay.transport('same-call', send)({}, GenerationSettings())
                self.assertEqual(sent, [1])
                self.assertEqual(before, {p.name: digest(p) for p in Path(folder).glob('*.json')})

    def test_malformed_readiness_bundle_never_raises_or_authorizes(self):
        with patch('research.gemini_backend.GeminiBackend._request', side_effect=AssertionError('No network')):
            for value in ('not-a-bundle', [], 123, {'schema_version':5, 'artifacts':None}):
                with self.subTest(value=value):
                    report = check_readiness(ROOT, value)
                    self.assertFalse(report['ready'])
                    self.assertFalse(report['protected_execution_authorized'])


if __name__ == '__main__': unittest.main()
