"""Budget-matched invented Gemini control; never adopts a new study model.

Uses S0=4096 and S1=2x2048 output caps, one attempt per call and the existing
lossless wire codec. All actual model identities and request settings remain
visible in immutable records. The original Gemma protocol is not changed.
"""
from __future__ import annotations
import argparse
from dataclasses import replace as dataclass_replace
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.probe_seed17_gemini_control import ControlSettings,MODEL
import tools.probe_seed17_wire_codec as runner
import research.gemini_backend as backend_module


def matched_replace(settings, **changes):
    # GeminiBackend's legacy direct default is 8192. Restrict this diagnostic
    # subclass to the registered 4096 total output budget, without model aliases.
    if isinstance(settings,ControlSettings) and settings.model==MODEL and changes.get('max_output_tokens')==8192:
        changes={**changes,'max_output_tokens':4096}
    return dataclass_replace(settings,**changes)


def run(output, *, mock=False):
    Parent=runner.WireBackend
    class MatchedBackend(Parent):
        def __init__(self,root,output,registration,*,mode,attempts,mock=False):
            super().__init__(root,output,registration,mode='modern',attempts=1,mock=mock)
            self.settings=ControlSettings(model=MODEL,timeout_seconds=90)
            self.journal.allow_reasoning_tokens=True
    print('DIAGNOSTIC_MODEL='+MODEL+'; S0_CAP=4096; S1_CAPS=2048+2048; STUDY_MODEL_CHANGED=False')
    with patch.object(backend_module,'replace',matched_replace),patch.object(runner,'WireBackend',MatchedBackend):
        return runner.run(output,mode='GEMINI35_MATCHED_CONTROL_MODERN_CODEC',attempts=1,mock=mock)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mock',action='store_true')
    a=p.parse_args();return 0 if run(a.output,mock=a.mock)['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
