# Co-occurring Ambiguity Dataset

**Version:** 1.0.0 (ID-renumbering and dataset-name release)  
**Date:** 2026-10-19  
**Records:** 100  
**Author-approved routing:** 100/100  
**Routes:** 74 execute, 26 clarify  
**Evaluation-only, protected:** no training, prompt tuning, or model selection.

## Change in this release

The dataset previously named Pilot-100 (author-adjudicated v6) is now called the **Co-occurring Ambiguity Dataset**. Every **active record ID** has been reassigned sequentially from `CA-0001` to `CA-0100`, in increasing numeric order of the previous v6 ID. This is a breaking change for joins to older files.

- Former `CA-0029` (library display stand) => `CA-0005` (clarify).
- Former `CA-0239` (train-station cleaning cart) => `CA-0025` (clarify, human capability attestation: capable).
- Former `CA-0565` (airport sign board) => `CA-0051` (clarify).
- Former `CA-1001` (museum plinth, originally `NEW-0100`) => `CA-0100` (execute).

**Important ID collision warning:** Some of these new IDs also occur with *different meanings* in the original frozen Pilot-120. They are NOT interchangeable. Keep this release in its own dataset namespace and join across releases only using `audit/ID_CROSSWALK_100.csv`.

## Current data files

- `data/source_100.jsonl`: command, scene, dialogue history, robot capability context.
- `data/gold_100_native_schema.jsonl`: source annotation fields, unchanged apart from top-level `record_id`.
- `data/gold_100_with_author_review.jsonl`: prior annotation fields and explicit author route-review status; IDs updated at top level only. Older references in nested `current_author_review_v6` remain **historical** references to previous versions.
- `data/author_approved_route_gold_100.jsonl`: authoritative, author-approved routing and strategy sequence for this release. Original `source_record_id_in_v4` is kept intentionally for provenance.

## Audit and provenance

- `audit/ID_CROSSWALK_100.csv` and `.jsonl`: exhaustive current-ID/previous-ID links.
- `audit/ALL_100_AUTHOR_REVIEW_STATUS.jsonl`: route approval statuses; historical v4 IDs kept explicitly as `v4_record_id`.
- `audit/ALL_100_EXPLICIT_APPROVALS.jsonl`: exactly 100 explicit author route approvals, with historical submission IDs and original evidence hashes preserved.
- `audit/CA-0025_AUTHOR_CAPABILITY_ATTESTATION.json`: author attestation that the cleaning-cart robot is capable. This is **not** an assertion that the original capability description independently establishes that skill.
- `audit/ROUTE_CORRECTION_HISTORY.json`: prior three author-approved route corrections, mapped to new IDs.
- `archive/Pilot_100_Author_Human_Adjudicated_Routes_v6.zip`: unchanged source archive, including earlier provenance and audit history.
- `MANIFEST.json`: SHA-256 hashes and counts. `verify_package.py` validates mapping, records, label distributions, cross-file consistency, and file hashes.

## Meaning of human adjudication

The author explicitly approved all 100 **terminal routes and strategy sequences**, approved synthetic inclusion, and affirmed the CA-0025 cart-moving capability. This does **not** imply that every other structured annotation field was newly human-adjudicated, that a second blinded annotator approved each record, or that the synthetic case originated from a frozen source corpus. Historical annotation statuses are retained, even where their old status wording describes the origin of a field rather than its current route approval.

## Renumbering reproducibility

All six main JSONL source/gold/review/audit files had only their top-level `record_id` changed. Original text and other fields remain byte-equivalent in value after parsing; JSON serialization may differ. `audit/ID_CROSSWALK_100.csv` is the complete 100-row deterministic mapping. The v6 archive is byte-preserved.
