"""Current author correction must not rebaseline historical source data."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class SourceStatusCorrectionTests(unittest.TestCase):
    def test_author_correction_and_unchanged_cohort(self):
        protocol = json.loads((ROOT / "protocol/gemini_protocol_v1.json").read_text(encoding="utf-8"))
        amendment = json.loads((ROOT / "protocol/amendments/CA-0100_source_status_20261019.json").read_text(encoding="utf-8"))
        meta = json.loads((ROOT / "Data/DATASET_METADATA.json").read_text(encoding="utf-8"))
        self.assertEqual(protocol["dataset"]["records"], 100)
        self.assertEqual(protocol["dataset"]["route_counts"], {"execute": 74, "clarify": 26})
        self.assertEqual(protocol["dataset"]["synthetic_records"], 0)
        self.assertEqual(protocol["dataset"]["origin_counts"], {"frozen_pilot120_subset": 99, "author_confirmed_source_record": 1})
        self.assertEqual(amendment["record_id"], "CA-0100")
        self.assertEqual(amendment["corrected_current_reporting_classification"], "source_record")
        self.assertTrue(amendment["historical_origin_claim_still_retained_for_audit"])
        self.assertTrue(amendment["immutable_dataset_records_and_sha256_unchanged"])
        self.assertEqual(meta["origin_counts"]["assistant_authored_synthetic"], 1)
