"""Invented-only alternate-backbone feasibility test; NOT the registered model.

All calls explicitly request gemma-4-31b-it and record actual provider metadata.
No source references or protected cases, no automatic model fallback in research.
"""
import argparse
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tools.probe_seed17_wire_codec as runner
from tools.probe_seed17_canonical_json import CanonicalBackend

MODEL='gemma-4-31b-it'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--transport',choices=['schema','canonical'],default='schema')
    p.add_argument('--mock',action='store_true')
    a=p.parse_args()
    parent=runner.WireBackend if a.transport=='schema' else CanonicalBackend
    class AlternateBackend(parent):
        def __init__(self,root,output,registration,*,mode,attempts,mock=False):
            super().__init__(root,output,registration,
                mode='modern' if a.transport=='schema' else 'canonical_json_local_validation',
                attempts=attempts,mock=mock)
            self.settings=replace(self.settings,model=MODEL,timeout_seconds=120)
    print('ALTERNATE_MODEL_CANDIDATE='+MODEL+'; REGISTERED_MODEL_UNCHANGED=True',flush=True)
    with patch.object(runner,'WireBackend',AlternateBackend):
        result=runner.run(a.output,mode='ALTERNATE_GEMMA31_'+a.transport,attempts=1,mock=a.mock)
    print('ALTERNATE_MODEL_CANDIDATE_COMPLETE='+str(result['complete']),flush=True)
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
