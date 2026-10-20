"""Invented-only Gemini control; never changes registered Gemma experiment.

The purpose is to distinguish generator-host compatibility from orchestration
bugs. Real study use would need a new registered model/budget/thinking contract.
"""
import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from research.gemini_backend import GenerationSettings
import tools.probe_seed17_wire_codec as runner

MODEL='gemini-3.5-flash-lite'

@dataclass(frozen=True)
class ControlSettings(GenerationSettings):
    def thinking_config(self):
        return {'thinkingLevel':'minimal','includeThoughts':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mock',action='store_true')
    a=p.parse_args()
    Parent=runner.WireBackend
    class ControlBackend(Parent):
        def __init__(self,root,output,registration,*,mode,attempts,mock=False):
            super().__init__(root,output,registration,mode='modern',attempts=attempts,mock=mock)
            self.settings=ControlSettings(model=MODEL,timeout_seconds=90)
            # Minimal on this different model need not be zero reasoning.
            # Strip thought text as usual; retain actual reported token counts.
            # This is diagnostic only and does not qualify Gemma no-thinking.
            self.journal.allow_reasoning_tokens=True
    print('CONTROL_MODEL='+MODEL+'; REGISTERED_EXPERIMENT_UNCHANGED=True',flush=True)
    with patch.object(runner,'WireBackend',ControlBackend):
        result=runner.run(a.output,mode='GEMINI35_CONTROL_MODERN_CODEC',attempts=1,mock=a.mock)
    return 0 if result['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
