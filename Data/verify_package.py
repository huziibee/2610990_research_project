#!/usr/bin/env python3
"""Verify the integrity, 100-case ID mapping, and route approvals of this release."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

base=Path(__file__).resolve().parent
manifest=json.loads((base/'MANIFEST.json').read_text(encoding='utf-8'))
assert manifest['dataset_name']=='Co-occurring Ambiguity Dataset'
assert manifest['record_count']==100 and manifest['label_counts']=={'execute':74,'clarify':26}
for member in manifest['files']:
    f=base/member['path']
    assert f.is_file(),member['path']
    assert f.stat().st_size==member['size_bytes'],member['path']
    assert hashlib.sha256(f.read_bytes()).hexdigest()==member['sha256'],member['path']

def load(path):
    return [json.loads(s) for s in (base/path).read_text(encoding='utf-8').splitlines() if s.strip()]

paths=['data/source_100.jsonl','data/gold_100_native_schema.jsonl','data/gold_100_with_author_review.jsonl','data/author_approved_route_gold_100.jsonl','audit/ALL_100_AUTHOR_REVIEW_STATUS.jsonl','audit/ALL_100_EXPLICIT_APPROVALS.jsonl','audit/ID_CROSSWALK_100.jsonl']
seq=['CA-%04d'%n for n in range(1,101)]
for p in paths:
    rows=load(p)
    assert len(rows)==100 and [r['record_id'] for r in rows]==seq,p
rows={p:load(p) for p in paths}
route=rows['data/author_approved_route_gold_100.jsonl']
assert Counter(x['terminal_strategy'] for x in route)==Counter({'execute':74,'clarify':26})
assert all(x['human_review_status']=='approved_by_author' for x in route)
assert all(x['human_decision']=='approve' for x in rows['audit/ALL_100_EXPLICIT_APPROVALS.jsonl'])
assert all(x['human_route_review_status']=='explicit_author_approved_route' for x in rows['audit/ALL_100_AUTHOR_REVIEW_STATUS.jsonl'])
for i in range(100):
    r=route[i]
    for p in ('data/gold_100_native_schema.jsonl','data/gold_100_with_author_review.jsonl'):
        g=rows[p][i]
        assert g['terminal_strategy']==r['terminal_strategy'] and g['strategy_sequence']==r['strategy_sequence'],(i,p)
    status=rows['audit/ALL_100_AUTHOR_REVIEW_STATUS.jsonl'][i]
    assert status['human_approved_terminal_strategy']==r['terminal_strategy']
    assert status['human_approved_strategy_sequence']==r['strategy_sequence']
with (base/'audit/ID_CROSSWALK_100.csv').open(newline='',encoding='utf-8') as f:
    cross=list(csv.DictReader(f))
assert len(cross)==100 and [x['record_id'] for x in cross]==seq
assert cross[4]['previous_v6_record_id']=='CA-0029' and cross[24]['previous_v6_record_id']=='CA-0239' and cross[50]['previous_v6_record_id']=='CA-0565' and cross[99]['previous_v6_record_id']=='CA-1001'
assert rows['audit/ID_CROSSWALK_100.jsonl']==cross
cap=json.loads((base/'audit/CA-0025_AUTHOR_CAPABILITY_ATTESTATION.json').read_text(encoding='utf-8'))
assert cap['record_id']=='CA-0025' and cap['previous_v6_record_id']=='CA-0239' and cap['human_choice']=='capable'
assert hashlib.sha256((base/manifest['source_v6_archive_path']).read_bytes()).hexdigest()==manifest['source_v6_archive_sha256']
# Verify not only labels but every original field survives remapping.
import zipfile
prior_by_current={row['record_id']:row['previous_v6_record_id'] for row in cross}
with zipfile.ZipFile(base/manifest['source_v6_archive_path']) as previous:
    comparisons={
        'data/source_100.jsonl':'data/source_100_v6.jsonl',
        'data/gold_100_native_schema.jsonl':'data/pilot_100_gold_v6_NATIVE_SCHEMA.jsonl',
        'data/gold_100_with_author_review.jsonl':'data/pilot_100_gold_v6_WITH_AUTHOR_REVIEW_STATUS.jsonl',
        'data/author_approved_route_gold_100.jsonl':'data/pilot_100_author_route_gold_v6.jsonl',
        'audit/ALL_100_AUTHOR_REVIEW_STATUS.jsonl':'human_review/ALL_100_AUTHOR_REVIEW_STATUS_v6.jsonl',
        'audit/ALL_100_EXPLICIT_APPROVALS.jsonl':'audit/ALL_100_EXPLICIT_APPROVALS_v6.jsonl',
    }
    for newpath,oldpath in comparisons.items():
        oldrows=[json.loads(line) for line in previous.read(oldpath).decode('utf-8').splitlines() if line.strip()]
        for current,prior in zip(rows[newpath],oldrows):
            assert current['record_id'] in prior_by_current
            assert prior['record_id']==prior_by_current[current['record_id']]
            without_newid=dict(current)
            without_newid['record_id']=prior['record_id']
            assert without_newid==prior,(newpath,current['record_id'])
print('PASS: 100 sequential records; 74 execute / 26 clarify; 100 approved routes; all member SHA-256 hashes; original v6 archive unchanged')
