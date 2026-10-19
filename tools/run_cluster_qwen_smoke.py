"""Offline GPU smoke on synthetic inputs only; never releases held-out evaluation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from research.gemini_backend import _unique_object, _validate_context
from research.generation_schema import response_schema
from research.input_contract import model_visible_context
from research.systems import ResearchSystem

MODEL = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"


class QwenSmokeBackend:
    def __init__(self, snapshot, output):
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA required; no CPU fallback")
        if snapshot.name != REVISION:
            raise ValueError("Expected pinned Qwen3-8B snapshot")
        self.torch, self.output, self.records = torch, output, []
        self.tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_compute_dtype=torch.bfloat16,
                                  bnb_4bit_use_double_quant=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            snapshot, local_files_only=True, quantization_config=quant, device_map={"": 0})
        self.model.eval()
        self.runtime = {"model": MODEL, "revision": REVISION, "snapshot": str(snapshot),
                        "torch": torch.__version__, "transformers": transformers.__version__,
                        "python": platform.python_version(), "gpu": torch.cuda.get_device_name(0),
                        "quantization": "bitsandbytes_nf4_double_quant_bfloat16_compute",
                        "enable_thinking": False, "schema_constrained_decoding": False,
                        "schema_in_prompt_and_strict_local_validation": True,
                        "cuda_model_placement": str(next(self.model.parameters()).device)}

    def generate(self, system_prompt, model_input, *, seed, stage, context=None, direct=False):
        visible = model_visible_context(model_input)
        if not model_input["record_id"].startswith("SYNTHETIC-"):
            raise ValueError("Cluster smoke rejects protected IDs")
        _validate_context(stage, context, model_input, direct)
        schema = response_schema(model_input, stage)
        prompt = system_prompt + "\nReturn one JSON object matching this schema: " + json.dumps(schema)
        messages = [{"role": "system", "content": prompt}, {"role": "user", "content":
            json.dumps({"input": visible, "stage_context": context}, ensure_ascii=False)}]
        rendered = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        expected_suffix = "<think>\n\n</think>\n\n"
        if not rendered.endswith(expected_suffix):
            raise RuntimeError("Thinking-off chat template prefill was not verified")
        tokens = self.tokenizer(rendered, return_tensors="pt").to("cuda")
        count = tokens.input_ids.shape[1]
        cap = 4096 if direct or stage == "S2.adjudicate" else 2048
        record = {"record_id": model_input["record_id"], "stage": stage, "seed": seed,
                  "model": MODEL, "revision": REVISION, "enable_thinking": False,
                  "thinking_off_template_suffix_verified": True,
                  "rendered_prompt_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                  "max_new_tokens": cap, "temperature": 0.7, "top_p": 0.95,
                  "input": visible, "stage_context": context, "system_prompt": prompt,
                  "status": "ERROR", "execution": "LIVE_CLUSTER_SYNTHETIC_SMOKE"}
        self.torch.manual_seed(seed)
        self.torch.cuda.manual_seed_all(seed)
        self.torch.cuda.synchronize()
        start = time.perf_counter()
        try:
            with self.torch.inference_mode():
                generated = self.model.generate(
                    **tokens, max_new_tokens=cap, do_sample=True, temperature=0.7, top_p=0.95,
                    pad_token_id=self.tokenizer.eos_token_id)
            self.torch.cuda.synchronize()
            answer_tokens = generated[0, count:]
            text = self.tokenizer.decode(answer_tokens, skip_special_tokens=True)
            record["tokens"] = {"input": count, "output": len(answer_tokens), "reasoning": None}
            if "<think>" in text or "</think>" in text:
                record["unexpected_thinking_output"] = True
                raise ValueError("Unexpected thinking output withheld")
            record["output_text"] = text
            eos = self.model.generation_config.eos_token_id
            eos = eos if isinstance(eos, list) else [eos]
            if int(answer_tokens[-1]) not in eos:
                raise ValueError("Generation did not reach EOS; no repair or retry")
            parsed = json.loads(text, object_pairs_hook=_unique_object,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(parsed, dict):
                raise ValueError("Response must be a JSON object")
            record["status"] = "OK"
            return parsed
        except Exception as exc:
            record["error_type"] = type(exc).__name__
            raise
        finally:
            record["latency_seconds"] = time.perf_counter() - start
            self.records.append(record)
            with (self.output / "calls.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    summary = {"execution": "LIVE_CLUSTER_SYNTHETIC_SMOKE", "benchmark_executed": False,
               "semantic_correctness": "NOT_COMPUTED", "enable_thinking": False,
               "model": MODEL, "revision": REVISION, "seed": 17, "expected_tests": 4,
               "tests": [], "status": "ERROR"}
    try:
        backend = QwenSmokeBackend(args.snapshot.resolve(), args.output)
        summary["runtime"] = backend.runtime
        print(json.dumps({"event": "MODEL_LOADED", **backend.runtime}), flush=True)
        case = json.loads((ROOT / "development/synthetic_case.json").read_text())
        variants = {"which shelf?", "which shelf should i move the blue cup to?",
                    "where should i move the blue cup?", "which shelf should the blue cup be moved to?",
                    "which shelf would you like me to move the blue cup to?",
                    "should i move the blue cup to shelf a or shelf b?"}
        for system in ("S0", "S1"):
            for clarify in (False, True):
                item = copy.deepcopy(case)
                label = system + (".clarification" if clarify else ".initial")
                start_calls = len(backend.records)
                result = {"test": label, "status": "ERROR"}
                try:
                    runner = ResearchSystem(backend)
                    if clarify:
                        item.update(record_id="SYNTHETIC-002", instruction="Move the blue cup to a shelf.",
                                    scene="A blue cup is on the desk. Shelf A and shelf B are empty.")
                        def answer(question, turn):
                            return "Shelf A" if turn == 1 and " ".join(question.split()).casefold() in variants else None
                        trajectory = runner.clarify(item, answer, system=system, seed=17)
                        result["clarification"] = trajectory
                        if (trajectory["termination"] != "ACTION_READY" or len(trajectory["turns"]) != 1
                                or trajectory["trajectory"][0]["task"]["readiness"] != "CLARIFY"):
                            raise ValueError("Required synthetic clarification cycle not completed")
                    else:
                        result["task"] = runner.predict(item, system=system, seed=17)
                        if result["task"]["readiness"] != "ACTION_READY":
                            raise ValueError("Explicit synthetic task should be ready")
                    result["status"] = "PASS"
                except Exception as exc:
                    result["error_type"] = type(exc).__name__
                    # Local errors only; no provider credentials or private thought text.
                    result["error"] = str(exc)[:300]
                result["calls"] = len(backend.records) - start_calls
                summary["tests"].append(result)
                print(json.dumps({k: v for k, v in result.items() if k not in ("task", "clarification")}), flush=True)
        summary["status"] = "PASS" if all(t["status"] == "PASS" for t in summary["tests"]) else "FAIL"
    except Exception as exc:
        summary["error_type"] = type(exc).__name__
        summary["error"] = str(exc)[:300]
        raise
    finally:
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": summary["status"], "tests_completed": len(summary["tests"]),
                          "expected_tests": 4, "benchmark_executed": False}), flush=True)
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
