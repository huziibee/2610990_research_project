# Release 1.0.1: source-count terminology

The current release supplies **100 source input records**. `source_records` now explicitly counts all release inputs. Historical origin metadata still records 99 previous-subset records and one synthetic-origin record within that total. The author requested the current-source count correction; this does not alter historical provenance. No source text, IDs, approved routes, strategy sequences or archive bytes changed. The previous 1.0.0 manifest is preserved in `protocol/provenance/Data_MANIFEST_v1.0.0.json` in the research workspace.

# Co-occurring Ambiguity Dataset: release 1.0.0

This release carries forward the **100 route and strategy-sequence decisions already explicitly approved by the author** in Pilot-100 v6. It renames the dataset and gives each active record a new sequential ID; it is **not** a fresh annotation round.

| Item | Value |
|---|---:|
| Total records | 100 |
| Execute | 74 |
| Clarify | 26 |
| Approved routes | 100 |
| Synthetic cases | 1 |
| New route-label changes relative to v6 | 0 |
| New text/context/capability changes relative to v6 | 0 |
| ID changes | 100 |

The old-to-new mapping is in `audit/ID_CROSSWALK_100.csv`. Historical v6 is preserved byte-for-byte in `archive/`. The source remains protected held-out evaluation data. The review scope is route/strategy sequence and the explicitly approved auxiliary decisions, not blanket certification of every structured gold field.
