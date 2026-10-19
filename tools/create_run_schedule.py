"""Create the planned paired S0/S1 schedule without running any predictions."""
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.integrity import read_json, read_jsonl, verify_derived


def main():
    verify_derived(ROOT)
    config = read_json(ROOT / "protocol/gemini_protocol_v1.json")
    ids = [row["record_id"] for row in read_jsonl(ROOT / "research_data/model_inputs/evaluation_100.jsonl")]
    rows = []
    for seed in config["runs"]["seeds"]:
        rng = random.Random(seed)
        order = list(ids)
        rng.shuffle(order)
        for record_id in order:
            systems = ["S0", "S1"]
            rng.shuffle(systems)
            for system in systems:
                rows.append({"sequence": len(rows) + 1, "record_id": record_id,
                             "seed": seed, "system": system, "planned_only": True})
    expected = {(record_id, seed, system) for record_id in ids
                for seed in config["runs"]["seeds"] for system in ("S0", "S1")}
    assert len(rows) == len(expected) == 1000
    assert {(r["record_id"], r["seed"], r["system"]) for r in rows} == expected
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path = ROOT / "protocol/run_schedule_1000.jsonl"
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise ValueError("Existing schedule differs; explicit protocol amendment required")
    path.write_text(text, encoding="utf-8", newline="\n")
    print("PASS: 1000 planned case/system/run entries; zero predictions executed.")


if __name__ == "__main__":
    main()
