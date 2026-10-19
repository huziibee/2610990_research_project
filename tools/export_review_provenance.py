"""Export the author-corrected historical model-label view without changing freeze."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.review_provenance import corrected_review_provenance, export_corrected_review_provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only audit the source and correction")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "runs" / "historical_review_provenance" / "annotator_b_author_corrected_100.jsonl",
        help="New non-overwriting JSONL export path under runs/",
    )
    args = parser.parse_args()
    if args.check:
        _, metadata = corrected_review_provenance(ROOT)
    else:
        metadata = export_corrected_review_provenance(ROOT, args.output)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
