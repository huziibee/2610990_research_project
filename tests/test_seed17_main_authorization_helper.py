"""Synthetic documentary approvals only; never authorizes this repository's study."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.integrity import digest, read_json
from research.seed17_freeze import REQUIRED_ARTIFACTS, SCOPE, current_runtime, technical_record
from research.seed17_journal import write_json
from tools.authorize_seed17_main import authorize


class MainAuthorizationHelperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'runs/readiness/unsigned'
        self.base.mkdir(parents=True)
        for name in ('protocol/DATA_FREEZE_20261019.json', 'protocol/gemini_protocol_v1.json'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, {'synthetic': True})
        snapshot = self.base / 'snapshot.json'
        write_json(snapshot, {'files': {}, 'runtime': current_runtime()})
        entry = {'path': snapshot.relative_to(self.root).as_posix(), 'sha256': digest(snapshot)}
        bundle = {'schema_version': 5, 'status': 'TECHNICALLY_PREPARED_NOT_AUTHORIZED',
                  'artifacts': {name: dict(entry) for name in REQUIRED_ARTIFACTS}}
        freeze = self.base / 'technical_freeze.json'
        record = technical_record(self.root, bundle)
        write_json(freeze, record)
        bundle['artifacts']['technical_freeze'] = {
            'path': freeze.relative_to(self.root).as_posix(), 'sha256': digest(freeze)}
        self.bundle = self.base / 'candidate_bundle.json'
        write_json(self.bundle, bundle)
        self.auth = self.root / 'runs/readiness/synthetic_auth.json'
        self.auth_value = {'status': 'EXPLICIT_USER_LAUNCH_AUTHORIZATION', 'authorization_granted': True,
                           'authorized_by': 'SYNTHETIC UNIT TEST ACTOR',
                           'authorized_utc': '2026-10-20T00:00:00+00:00',
                           'verbatim_authorization': 'INVENTED TEST FIXTURE ONLY',
                           'study_id': 'gemma4-seed17-v1', 'scope': SCOPE,
                           'technical_freeze_sha256': digest(freeze),
                           'base_artifacts_sha256': record['base_artifacts_sha256'],
                           'freeze_sha256': digest(snapshot)}
        write_json(self.auth, self.auth_value)
        self.output = self.root / 'runs/readiness/authorized'
        # The full readiness fixture requires live evidence/private data. Only this broad
        # gate is stubbed; actual freeze/hash/scope/time authorization validators run.
        def readiness(root, value):
            approved = 'authorization_evidence' in value['artifacts']
            return {'ready': approved, 'protected_execution_authorized': approved,
                    'ready_for_authorization': not approved,
                    'failures': [] if approved else [{'gate': 'signed_off_release'}]}
        self.gate = patch('tools.authorize_seed17_main.check_readiness', side_effect=readiness)
        self.gate.start()
        self.addCleanup(self.gate.stop)

    def run_helper(self):
        return authorize(self.root, self.bundle, self.auth, self.output)

    def replace_auth(self, **changes):
        self.auth_value.update(changes)
        self.auth.unlink()
        write_json(self.auth, self.auth_value)

    def test_valid_separate_copy_preserves_all_source_bytes(self):
        before = {p: digest(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertTrue(self.run_helper()['ready'])
        self.assertEqual(before, {p: digest(p) for p in before})
        result = read_json(self.output / 'candidate_bundle.json')
        self.assertEqual(result['artifacts']['authorization_evidence']['sha256'], digest(self.auth))
        self.assertNotIn('authorization_evidence', read_json(self.bundle)['artifacts'])

    def test_rejects_each_mismatched_hash(self):
        for field in ('technical_freeze_sha256', 'base_artifacts_sha256', 'freeze_sha256'):
            with self.subTest(field=field):
                original = self.auth_value[field]
                self.replace_auth(**{field: '0' * 64})
                with self.assertRaises(ValueError):
                    self.run_helper()
                self.assertFalse(self.output.exists())
                self.replace_auth(**{field: original})

    def test_missing_authorization(self):
        self.auth.unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_helper()
        self.assertFalse(self.output.exists())

    def test_naive_timestamp(self):
        self.replace_auth(authorized_utc='2026-10-20T00:00:00')
        with self.assertRaises(ValueError):
            self.run_helper()

    def test_existing_output_is_never_overwritten(self):
        self.run_helper()
        before = digest(self.output / 'candidate_bundle.json')
        with self.assertRaises(FileExistsError):
            self.run_helper()
        self.assertEqual(before, digest(self.output / 'candidate_bundle.json'))

    def test_refuses_output_escape_and_readiness_root(self):
        for output in (self.root / 'runs/readiness', self.root / 'runs/readiness/../escape'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                authorize(self.root, self.bundle, self.auth, output)

    def test_changed_technical_artifact_is_rejected(self):
        (self.base / 'snapshot.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_helper()

    def test_unresolved_technical_or_authorized_gate_does_not_write(self):
        with patch('tools.authorize_seed17_main.check_readiness', return_value={
                'ready_for_authorization': False, 'failures': [{'gate': 'live_multi_turn'}]}):
            with self.assertRaises(ValueError):
                self.run_helper()
        self.assertFalse(self.output.exists())
        with patch('tools.authorize_seed17_main.check_readiness', side_effect=[
                {'ready_for_authorization': True, 'failures': [{'gate': 'signed_off_release'}]},
                {'ready': False, 'protected_execution_authorized': False, 'failures': []}]):
            with self.assertRaises(ValueError):
                self.run_helper()
        self.assertFalse(self.output.exists())

    def test_wrong_scope_and_absent_verbatim_approval_are_rejected(self):
        for changes in ({'scope': 'seed17_ablations'}, {'verbatim_authorization': ''},
                        {'authorization_granted': False}):
            original = dict(self.auth_value)
            with self.subTest(changes=changes):
                self.replace_auth(**changes)
                with self.assertRaises(ValueError):
                    self.run_helper()
                self.auth_value = original
                self.replace_auth()


if __name__ == '__main__':
    unittest.main()
