# Slice 9.2 — deterministic generation config + explicit CUDA placement

## Why

Two runtime ambiguities were removed:

1. Transformers 5.x warns when sampling-only flags (`top_p`, `top_k`, `temperature`) are explicitly present while `do_sample=false`.
2. `device_map="auto"` is allowed to offload model modules to CPU/disk. That is useful for generic large-model inference, but it hides whether the local agent is actually running on the GPU.

## Generation

Each request now creates a fresh `GenerationConfig` from explicit role settings.

- Perception (`temperature=0`) uses greedy decoding and does **not** set `temperature`, `top_p`, or `top_k` at all.
- Agent sampling includes these fields only when `temperature > 0`.
- No generation-related kwargs are mixed with `generation_config` in `model.generate()`.

This also prevents checkpoint `generation_config.json` sampling values from leaking into the deterministic parser role.

## CUDA / placement

The default project config is now tuned for the local 27B model:

```toml
[llm]
device_map = "cuda:0"
use_4bit = true
```

`cuda:0` is normalized to a concrete GPU-only device map. The worker fails explicitly if CUDA is unavailable or if GPU-only placement somehow results in CPU/disk modules; it no longer silently accepts CPU offload for this configuration.

NF4 4-bit is loaded with bitsandbytes unless the checkpoint already declares its own quantization.

The worker reports:

- `torch.cuda.is_available()`;
- PyTorch CUDA runtime version;
- visible GPU names and VRAM totals;
- final `hf_device_map` devices;
- CUDA allocated/reserved memory after load;
- effective 4-bit status.

The LLM GUI panel shows `Device policy`, `CUDA`, and `Placement / VRAM` fields.

## RAM behavior

Some host RAM may still be used transiently while loading checkpoint shards. `low_cpu_mem_usage=true` is requested. The important invariant for `device_map="cuda:0"` is that the **loaded model modules** end on the selected CUDA device rather than remaining CPU-offloaded.

## Install

`bitsandbytes` is now included in the `llm` extra because the default local 27B configuration uses NF4:

```powershell
pip install -U -e ".[gui,llm]"
```
