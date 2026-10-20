"""Invented-only prompt candidate for omitting unknown arguments, not repairing output.

The shared S0/S1 task prompt gets the same unrelated partial-task illustration.
Source inputs, goal stage, original model, budgets and local validator remain
unchanged. No protected cases or reference release is read.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tools.probe_seed17_canonical_json as canonical
import tools.probe_seed17_wire_codec as runner

ORIGINAL=canonical.canonical_payload
OMISSION_EXAMPLE='''
Representation rule: a required capability argument is required for ACTION_READY,
not for a partial CLARIFY task. Unknown arguments MUST NOT be present in the
arguments object. Never emit a null value, empty value, guessed default, or
empty evidence array to fill an unknown argument. Declare it in unresolved only.
Unrelated illustration (do not copy its entities into the actual task): for
paint(surface: string, colour: string), if only the surface is known, the partial
action arguments can be {"surface":{"type":"string","value":"example panel",
"evidence":["instruction"]}}. The colour key is ABSENT, while unresolved includes
{"field":"colour","reason":"Not supplied","critical":true}. Readiness is
CLARIFY. When colour is supplied, add its typed value and real evidence source.
Now answer the actual instruction, not the illustration. Before returning,
check that every present argument has a non-null value of its stated type and
nonempty supporting evidence. Keep still-unknown required fields in unresolved.
'''


def omission_payload(payload, *, json_mime=True):
    actual=ORIGINAL(payload,json_mime=json_mime)
    schema=payload['generationConfig']['responseJsonSchema']
    if 'actions' in schema.get('properties',{}):
        actual['systemInstruction']['parts'][0]['text']+=OMISSION_EXAMPLE
    return actual


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mock',action='store_true')
    parser.add_argument('--attempts',type=int,default=3)
    args=parser.parse_args()
    with patch.object(canonical,'canonical_payload',omission_payload),patch.object(runner,'WireBackend',canonical.CanonicalBackend):
        report=runner.run(args.output,mode='canonical_plain_text_lossless_fence',attempts=args.attempts,mock=args.mock)
    return 0 if report['complete'] else 2

if __name__=='__main__':raise SystemExit(main())
