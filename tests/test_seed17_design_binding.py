"""Registered unsigned design must bind the exact committed protocol bytes."""
from pathlib import Path
import unittest

from research.integrity import digest, read_json

ROOT = Path(__file__).resolve().parents[1]


class Seed17DesignBindingTests(unittest.TestCase):
    def test_registered_candidate_and_unsigned_lock_bind_raw_bytes(self):
        config_path = ROOT / 'protocol/gemma4_seed17_v1.json'
        lock = read_json(ROOT / 'protocol/seed17/FREEZE.json')
        config = read_json(config_path)
        self.assertEqual(lock['config_path'], config_path.relative_to(ROOT).as_posix())
        self.assertEqual(lock['config_sha256'], digest(config_path))
        self.assertEqual(config['status'], 'CANDIDATE')
        self.assertIs(config['allow_held_out_predictions'], False)
        self.assertEqual(lock['status'], 'UNSIGNED')
        self.assertIs(lock['authorization_granted'], False)
        self.assertIsNone(lock['signed_utc'])
        self.assertEqual(lock['authorized_by'], '[Waiting for explicit authorization]')

    def test_amendment_preserves_old_lock_and_changes_only_hash(self):
        amendment = read_json(ROOT / 'protocol/amendments/GEMMA_SEED17_UNSIGNED_DESIGN_LOCK_REBIND_20261020_v1.json')
        prior_path = ROOT / amendment['preserved_lock']['path']
        current_path = ROOT / amendment['updated_lock']['path']
        self.assertEqual(digest(prior_path), amendment['preserved_lock']['sha256'])
        self.assertEqual(digest(current_path), amendment['updated_lock']['sha256'])
        self.assertEqual(digest(ROOT / amendment['protocol_path']), amendment['protocol_sha256'])
        self.assertEqual(read_json(prior_path)['config_sha256'], amendment['prior_protocol_sha256'])
        self.assertEqual(current_path.read_bytes(), prior_path.read_bytes().replace(
            amendment['prior_protocol_sha256'].encode(), amendment['protocol_sha256'].encode()))
        old, current = read_json(prior_path), read_json(current_path)
        old.pop('config_sha256')
        current.pop('config_sha256')
        self.assertEqual(old, current)


if __name__ == '__main__':
    unittest.main()
