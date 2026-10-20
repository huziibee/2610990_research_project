"""Invented filesystem fixtures only; no human reference exports are loaded."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from research.annotation_store import AnnotationStore

class PortableSourceReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.workspace=self.root/'review';self.workspace.mkdir()
        (self.workspace/'events').mkdir();(self.workspace/'exports').mkdir()
        self.paths={};pins={};records={}
        for role in ('source','routes','worksheet'):
            p=self.root/(role+'.jsonl')
            rows=[{'record_id':'SYNTHETIC-001','role':role}]
            data=(json.dumps(rows[0])+'\n').encode();p.write_bytes(data)
            self.paths[role]=p
            pins[role]={'path':str(self.root/'old_checkout'/p.name),'sha256':hashlib.sha256(data).hexdigest()}
            records[role]={'SYNTHETIC-001':rows[0]}
        self.manifest={'schema_version':1,'pins':pins,'records':records,'record_ids':['SYNTHETIC-001']}
        self.file=self.workspace/'manifest.json';self.file.write_text(json.dumps(self.manifest))
        self.before=self.file.read_bytes()

    def test_relocated_identical_bytes_replay_without_manifest_rewrite(self):
        actual=AnnotationStore(self.workspace,source_paths=self.paths)._manifest()
        self.assertEqual(actual,self.manifest)
        self.assertEqual(self.file.read_bytes(),self.before)

    def test_old_path_behavior_still_fails_when_source_absent(self):
        with self.assertRaises(OSError):AnnotationStore(self.workspace)._manifest()

    def test_modified_source_bytes_rejected(self):
        self.paths['source'].write_text('{"record_id":"SYNTHETIC-002"}\n')
        with self.assertRaises(ValueError):AnnotationStore(self.workspace,source_paths=self.paths)._manifest()
        self.assertEqual(self.file.read_bytes(),self.before)

    def test_missing_or_extra_role_rejected(self):
        for paths in ({'source':self.paths['source']},{**self.paths,'extra':self.paths['source']}):
            with self.subTest(paths=list(paths)),self.assertRaises(ValueError):
                AnnotationStore(self.workspace,source_paths=paths)._manifest()

    def test_roles_cannot_be_swapped(self):
        paths={**self.paths,'source':self.paths['routes'],'routes':self.paths['source']}
        with self.assertRaises(ValueError):AnnotationStore(self.workspace,source_paths=paths)._manifest()

    def test_manifest_record_disagreement_rejected_even_with_valid_source_hash(self):
        self.manifest['records']['source']['SYNTHETIC-001']['role']='changed'
        self.file.write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):AnnotationStore(self.workspace,source_paths=self.paths)._manifest()

    def test_mapping_is_copied_not_aliased_and_invalid_shape_rejected(self):
        mapping=dict(self.paths);store=AnnotationStore(self.workspace,source_paths=mapping)
        mapping.clear();self.assertEqual(store._manifest(),self.manifest)
        with self.assertRaises(ValueError):AnnotationStore(self.workspace,source_paths=[])

if __name__=='__main__':unittest.main()
