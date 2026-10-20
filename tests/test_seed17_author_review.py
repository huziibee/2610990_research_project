"""Synthetic-only author-method, immutable release, matching and scoring tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests import test_author_batch_review as author_fixtures
from tests import test_semantic_metrics as metric_fixtures
from tools.review_author_batch import approve_batch
from research.integrity import read_json, read_jsonl, digest
from research.seed17_journal import write_json
from research.seed17_author_review import (validate_author_release, derived_rules_and_coverage,
    load_author_release, AuthorReviewedClarificationOracle, METHOD_ID)
from research.semantic_metrics import score_semantics


class AuthorMethodTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        cls.ws,store=author_fixtures.AuthorBatchTest().make_workspace(cls.root)
        receipt=approve_batch(cls.ws,'Synthetic fixture author','Synthetic fixture approval only.',
                              reported_two_models=True,reported_review_models=['Fixture Model A','Fixture Model B'])
        archive=cls.root/'protected_reference_archive';archive.mkdir()
        (archive/'author_review_v1.enc').write_bytes(b'SYNTHETIC CIPHERTEXT')
        (archive/'author_review_v1.manifest.json').write_text('{}')
        rp=cls.ws/'author_review_export/AUTHOR_REVIEW_RECEIPT.json'
        refs=rp.parent/'author_reviewed_references_100.jsonl'
        cls.selected={'protocol_id':METHOD_ID,'author':'Synthetic fixture author','release':{
            'receipt_sha256':digest(rp),'reference_export_sha256':digest(refs),
            'source_manifest_sha256':digest(cls.ws/'manifest.json'),
            'archive_sha256':digest(archive/'author_review_v1.enc'),
            'archive_manifest_sha256':digest(archive/'author_review_v1.manifest.json')},
            'source_bindings':{name:{'path':name+'.jsonl','sha256':digest(cls.root/(name+'.jsonl'))}
                               for name in ('source','routes','worksheet')}}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def context(self):
        with patch('research.seed17_author_review.policy',return_value=self.selected):
            return validate_author_release(self.root,self.ws)

    def test_complete_exact_release_keeps_actual_provenance(self):
        release=self.context()
        self.assertEqual(release['evidence']['clarification_branches'],26)
        self.assertFalse(release['evidence']['independent_human_verification'])
        matching,coverage=derived_rules_and_coverage(release)
        self.assertEqual(len(matching['cases']),100)
        self.assertEqual(sum(r['branch_count'] for r in coverage['cases']),26)
        self.assertFalse(matching['independently_verified'])
        self.assertFalse(coverage['independently_verified'])

    def test_receipt_export_manifest_source_and_archive_changes_rejected(self):
        paths=[self.ws/'author_review_export/AUTHOR_REVIEW_RECEIPT.json',
               self.ws/'author_review_export/author_reviewed_references_100.jsonl',
               self.ws/'manifest.json',self.root/'source.jsonl',
               self.root/'protected_reference_archive/author_review_v1.enc']
        for path in paths:
            old=path.read_bytes()
            try:
                path.write_bytes(old+b' ')
                with self.assertRaises(ValueError): self.context()
            finally:
                path.write_bytes(old)

    def test_ledger_tamper_without_export_change_rejected(self):
        path=next((self.ws/'events').rglob('*.json'));old=path.read_bytes()
        try:
            event=read_json(path);event['actor']='Synthetic forged actor';path.write_text(json.dumps(event))
            with self.assertRaises(ValueError): self.context()
        finally: path.write_bytes(old)

    def test_exact_projection_rejects_rules_labels_and_missing_cases_even_rehashed(self):
        release=self.context();matching,coverage=derived_rules_and_coverage(release)
        with tempfile.TemporaryDirectory(dir=self.root) as tmp:
            folder=Path(tmp)
            paths={'clarification_matching_rules':folder/'matching.json','reviewed_coverage':folder/'coverage.json',
                   'semantic_export':self.ws/'author_review_export/AUTHOR_REVIEW_RECEIPT.json',
                   'semantic_references':self.ws/'author_review_export/author_reviewed_references_100.jsonl'}
            paths['clarification_matching_rules'].write_text(json.dumps(matching))
            paths['reviewed_coverage'].write_text(json.dumps(coverage))
            def bundle():
                return {'annotation_workspace':'workspace','artifacts':{n:{'path':p.relative_to(self.root).as_posix(),'sha256':digest(p)} for n,p in paths.items()}}
            with patch('research.seed17_author_review.policy',return_value=self.selected):
                self.assertEqual(len(load_author_release(self.root,bundle())['rows']),100)
                mutations=[('clarification_matching_rules',matching,lambda x:x['cases'].pop()),
                    ('clarification_matching_rules',matching,lambda x:x['cases'][0]['branches'][0]['turns'][0].update(canonical_question='Unapproved paraphrase?')),
                    ('clarification_matching_rules',matching,lambda x:x['cases'][0]['branches'][0]['turns'][0].update(answer_sha256='f'*64)),
                    ('reviewed_coverage',coverage,lambda x:x['cases'][0].update(source_record_sha256='f'*64)),
                    ('reviewed_coverage',coverage,lambda x:x['cases'][0].update(capability_eligibility='INVENTED_VERIFIED_SUPPORT')),
                    ('reviewed_coverage',coverage,lambda x:x['cases'][0].update(dialogue_relevant=True)),
                    ('reviewed_coverage',coverage,lambda x:x.update(independently_verified=True))]
                for name,original,mutate in mutations:
                    changed=copy.deepcopy(original);mutate(changed);paths[name].write_text(json.dumps(changed))
                    with self.assertRaises(ValueError):load_author_release(self.root,bundle())
                    paths[name].write_text(json.dumps(original))

    def test_oracle_only_releases_matching_single_use_answer(self):
        release=self.context();release['rules']=derived_rules_and_coverage(release)[0]
        oracle=AuthorReviewedClarificationOracle(release,record_id='CA-0001',branch_id='answer-a')
        self.assertEqual(oracle('  WHERE should the cup go?  ',1),'shelf A')
        paraphrase=AuthorReviewedClarificationOracle(release,record_id='CA-0001',branch_id='answer-a')
        self.assertEqual(paraphrase('Where should the cup go',1),'shelf A')
        self.assertIsNone(oracle('Where should the cup go?',2))
        oracle=AuthorReviewedClarificationOracle(release,record_id='CA-0001',branch_id='answer-a')
        self.assertIsNone(oracle('Unapproved?',1))
        self.assertIsNone(oracle('Where should the cup go?',1))
        oracle=AuthorReviewedClarificationOracle(release,record_id='CA-0001',branch_id='answer-a')
        with self.assertRaises(ValueError):oracle('Where should the cup go?',2)

    def test_rehashed_answer_or_provenance_cannot_replace_approved_ledger(self):
        from research.seed17_journal import content_hash
        rp=self.ws/'author_review_export/AUTHOR_REVIEW_RECEIPT.json'
        ep=rp.parent/'author_reviewed_references_100.jsonl'
        original_receipt,original_export=rp.read_bytes(),ep.read_bytes()
        try:
            for change in ('answer','provenance'):
                rows=read_jsonl(ep)
                if change=='answer': rows[0]['reference']['hypothetical_answer_branches'][0]['answer']='Fabricated answer'
                else: rows[0]['model_assisted']=False
                ep.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')
                receipt=json.loads(original_receipt)
                receipt['reference_export_sha256']=digest(ep)
                receipt['references'][0]['reference_sha256']=content_hash(rows[0]['reference'])
                receipt['receipt_sha256']=content_hash({k:v for k,v in receipt.items() if k!='receipt_sha256'})
                rp.write_text(json.dumps(receipt),encoding='utf-8')
                selected=copy.deepcopy(self.selected)
                selected['release'].update(receipt_sha256=digest(rp),reference_export_sha256=digest(ep))
                with patch('research.seed17_author_review.policy',return_value=selected):
                    with self.assertRaises(ValueError):validate_author_release(self.root,self.ws)
                ep.write_bytes(original_export)
                rp.write_bytes(original_receipt)
        finally:
            ep.write_bytes(original_export);rp.write_bytes(original_receipt)



if __name__=='__main__':unittest.main()
