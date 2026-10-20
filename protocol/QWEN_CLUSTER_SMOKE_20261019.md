# Qwen cluster smoke attempt

Requested scope: repeat the earlier repository's cluster approach using Qwen, keeping thinking off. This is a separate synthetic diagnostic; the Gemma experiment candidate is unchanged.

Reused and verified live: Wits account `mbangie`, cached `Qwen/Qwen3-8B` revision `b968826d9c46dd6066d109eabc6255188de91218`, the existing PyTorch 2.11/CUDA 13 Apptainer container and training-site-packages. The smoke loader requests offline NF4 double quantization with BF16 compute, as in the earlier repository. It uses `enable_thinking=False` and checks the rendered thinking-off prefill. It does not download weights, train, load an adapter or call an external API.

Only eight explicitly listed code/fixture files were uploaded into new directories below `/home-mscluster/mbangie/final-research-smokes/`. The bundle contains no protected dataset, private references, environment file or API keys. Uploaded hashes and shell syntax passed before each submission. Each allocation was exclusive, 80 GB host memory, eight requested CPU cores, and a 20-minute wall limit.

| Job | Node | Final state | Evidence |
|---|---|---|---|
| 71769 | mscluster112 | FAILED, exit 6:0, elapsed 0 s | `nvidia-smi`: no devices; GPU0 device handle returned Unknown Error. Python did not start. |
| 71770 | mscluster111 | FAILED, exit 1:0, elapsed 76 s | NVIDIA management output showed a card with error fields; the container's `torch.cuda.is_available()` returned false. Explicit GPU requirement stopped execution before model loading. |

**Completed smoke checks: 0/4.** Planned checks were S0 and S1 initial prediction, followed by a synthetic one-answer clarification/revalidation cycle for each system. Neither attempt generated a prediction. Model correctness, thinking-off rendering at runtime, inference latency, token consumption and semantic accuracy were not measured.

Local evidence directories:

- `runs/cluster_smoke/qwen3_8b_smoke_20261019T195156Z/`: submission manifest, payload hashes, job script and job-71769 logs.
- `runs/cluster_smoke/qwen3_8b_smoke_20261019T195243Z/`: retry manifest, identical payload, node-111 job script, job-71770 logs and `summary.json`.

The reusable entry point is `tools/run_cluster_qwen_smoke.py`. Local syntax compilation and `--help` passed. GPU/model execution remains unverified. JSON schema is included in the Qwen prompt and the existing goal/task validators are used; this Transformers smoke does not provide server-constrained JSON decoding.

Next prerequisite: a usable CUDA GPU allocation. Both idle biggpu nodes tested here failed. No pending smoke job was left behind, and no node settings, drivers, other jobs or existing research artifacts were modified. A healthy-node retry must use a new output directory and preserve these failed attempts.

Held-out evaluation was not run. Scientific results remain `NOT_COMPUTED`.
