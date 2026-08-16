from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _require_dir(value: str, name: str) -> Path:
    p = Path(value).expanduser().resolve()
    if not p.is_dir():
        raise SystemExit(f"{name} must be an existing local directory: {p}")
    return p


def _read_model_config(base: Path) -> dict[str, Any]:
    path = base / "config.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_loader_type(base: Path, requested: str) -> str:
    req = requested.strip().lower()
    if req in {"causal_lm", "causal", "text", "text_only"}:
        return "causal_lm"
    if req in {"image_text_to_text", "image", "ittt", "multimodal"}:
        return "image_text_to_text"
    if req != "auto":
        raise SystemExit(f"Unsupported loader type: {requested}")

    # This application is a TEXT agent. A composite Qwen checkpoint may contain a
    # vision encoder, but auto mode must not pull AutoProcessor / image backends just
    # because vision_config exists. Explicit image_text_to_text remains available for
    # future multimodal work.
    return "causal_lm"


def _dtype(torch: Any, value: str):
    v = value.strip().lower()
    if v == "auto":
        return torch.bfloat16 if torch.cuda.is_available() else torch.float32
    mapping = {
        "bfloat16": torch.bfloat16,
        "float16": torch.float16,
        "float32": torch.float32,
    }
    if v not in mapping:
        raise SystemExit(f"Unsupported dtype: {value}")
    return mapping[v]


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()


def _resolve_device_map(value: str):
    """Normalize the human config value to a Transformers device_map value.

    `auto` explicitly permits Accelerate to place modules on CPU/disk. A concrete
    CUDA device means GPU-only placement; if it does not fit, loading should fail
    instead of silently consuming system RAM.
    """
    v = value.strip().lower()
    if v == "auto":
        return "auto"
    if v == "cpu":
        return "cpu"
    if v == "cuda":
        return 0
    if v.startswith("cuda:"):
        try:
            return int(v.split(":", 1)[1])
        except ValueError as exc:
            raise SystemExit(f"Invalid CUDA device_map: {value}") from exc
    try:
        return int(v)
    except ValueError:
        raise SystemExit(f"Unsupported device_map: {value}")


def _cuda_probe(torch: Any) -> dict[str, Any]:
    available = bool(torch.cuda.is_available())
    devices: list[dict[str, Any]] = []
    if available:
        for index in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(index)
            devices.append({
                "index": index,
                "name": str(props.name),
                "total_bytes": int(props.total_memory),
            })
    return {
        "available": available,
        "torch_version": str(getattr(torch, "__version__", "unknown")),
        "torch_cuda_version": str(getattr(getattr(torch, "version", None), "cuda", None)),
        "devices": devices,
    }


def _device_token(value: Any) -> str:
    if isinstance(value, int):
        return f"cuda:{value}"
    text = str(value)
    if text.isdigit():
        return f"cuda:{text}"
    return text


def _placement_info(torch: Any, model: Any) -> dict[str, Any]:
    raw_map = getattr(model, "hf_device_map", None)
    if isinstance(raw_map, dict) and raw_map:
        device_map = {str(k): _device_token(v) for k, v in raw_map.items()}
        devices = sorted(set(device_map.values()))
    else:
        device_map = {}
        devices = []
        try:
            devices = sorted({str(param.device) for param in model.parameters()})
        except Exception:
            device = getattr(model, "device", None)
            if device is not None:
                devices = [str(device)]
    cuda_memory: list[dict[str, Any]] = []
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            cuda_memory.append({
                "index": index,
                "allocated_bytes": int(torch.cuda.memory_allocated(index)),
                "reserved_bytes": int(torch.cuda.memory_reserved(index)),
            })
    return {
        "devices": devices,
        "hf_device_map": device_map,
        "uses_cpu_or_disk": any(d == "cpu" or d == "disk" for d in devices),
        "cuda_memory": cuda_memory,
    }


def _input_device(model: Any):
    try:
        embeddings = model.get_input_embeddings()
        weight = getattr(embeddings, "weight", None)
        if weight is not None and str(weight.device) != "meta":
            return weight.device
    except Exception:
        pass
    try:
        for param in model.parameters():
            if str(param.device) != "meta":
                return param.device
    except Exception:
        pass
    return getattr(model, "device", "cpu")


def _generation_config_values(
    *, max_new: int, temperature: float, top_p: float, top_k: int,
    repetition_penalty: float, no_repeat_ngram_size: int, use_cache: bool = True,
    pad_token_id: int | None, eos_token_id: Any, bos_token_id: Any = None,
) -> dict[str, Any]:
    """Build request-local GenerationConfig kwargs without invalid greedy flags."""
    do_sample = temperature > 0
    values: dict[str, Any] = {
        "max_new_tokens": max_new,
        "do_sample": do_sample,
        "repetition_penalty": repetition_penalty,
        "no_repeat_ngram_size": no_repeat_ngram_size,
        "pad_token_id": pad_token_id,
        "eos_token_id": eos_token_id,
        "bos_token_id": bos_token_id,
        "use_cache": use_cache,
    }
    if do_sample:
        values.update(temperature=temperature, top_p=top_p, top_k=top_k)
    return values


def load_runtime(args: argparse.Namespace) -> dict[str, Any]:
    emit({"event": "status", "stage": "importing", "detail": "torch / transformers"})
    try:
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig
    except Exception as exc:
        raise SystemExit(f"LLM extras are not installed: {exc}")

    version = str(getattr(transformers, "__version__", "unknown"))
    emit({"event": "status", "stage": "transformers", "detail": version})

    cuda = _cuda_probe(torch)
    cuda_desc = "; ".join(
        f"cuda:{d['index']}={d['name']} ({d['total_bytes'] / 2**30:.1f} GiB)"
        for d in cuda["devices"]
    ) or "no CUDA devices"
    emit({
        "event": "status", "stage": "cuda_probe",
        "detail": f"available={cuda['available']}; torch_cuda={cuda['torch_cuda_version']}; {cuda_desc}",
        "cuda": cuda,
    })
    requested_device_map = _resolve_device_map(args.device_map)
    gpu_only_requested = isinstance(requested_device_map, int)
    if gpu_only_requested and not cuda["available"]:
        raise SystemExit(
            "CUDA-only loading was requested, but torch.cuda.is_available() is False. "
            f"torch={cuda['torch_version']}; torch.version.cuda={cuda['torch_cuda_version']}. "
            "Install a CUDA-enabled PyTorch build before starting the LLM."
        )
    if isinstance(requested_device_map, int) and requested_device_map >= len(cuda["devices"]):
        raise SystemExit(f"Requested cuda:{requested_device_map}, but only {len(cuda['devices'])} CUDA device(s) are visible")

    base = _require_dir(args.model_dir, "model_dir")
    tokenizer_dir = _require_dir(args.tokenizer_dir, "tokenizer_dir") if args.tokenizer_dir else base
    loader_type = _resolve_loader_type(base, args.loader_type)

    emit({"event": "status", "stage": "loading_tokenizer", "detail": str(tokenizer_dir)})
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_dir,
        use_fast=True,
        local_files_only=args.local_files_only,
        trust_remote_code=args.trust_remote_code,
    )
    processor = None

    if getattr(tokenizer, "pad_token_id", None) is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    kwargs: dict[str, Any] = {
        "local_files_only": args.local_files_only,
        "trust_remote_code": args.trust_remote_code,
        "device_map": requested_device_map,
        "dtype": _dtype(torch, args.dtype),
        "low_cpu_mem_usage": True,
    }
    model_file_config = _read_model_config(base)
    checkpoint_quantization = model_file_config.get("quantization_config")
    effective_4bit = bool(args.use_4bit and not checkpoint_quantization)
    if checkpoint_quantization:
        emit({"event": "status", "stage": "quantization", "detail": "checkpoint already declares quantization; external NF4 disabled"})
    if effective_4bit:
        try:
            from transformers import BitsAndBytesConfig
            import bitsandbytes as bnb
        except Exception as exc:
            raise SystemExit(
                "llm.use_4bit=true requires bitsandbytes. Run pip install -U bitsandbytes. "
                f"Original error: {exc}"
            ) from exc
        emit({"event": "status", "stage": "quantization", "detail": f"bitsandbytes={getattr(bnb, '__version__', 'unknown')}; NF4 4-bit"})
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )

    emit({"event": "status", "stage": "loading_model", "detail": f"{loader_type}: {base}"})
    if loader_type == "causal_lm":
        try:
            # Modern Transformers unwraps the text sub-config from composite Qwen
            # checkpoints. This intentionally skips the vision encoder and therefore
            # does not require Pillow/torchvision for our text-only runtime.
            model = AutoModelForCausalLM.from_pretrained(base, **kwargs)
        except Exception as exc:
            raise SystemExit(
                "Text-only AutoModelForCausalLM loading failed. "
                "Qwen3.6 requires a recent Transformers build; run "
                "pip install -U 'transformers>=5.14.1,<6'. "
                f"Original error: {type(exc).__name__}: {exc}"
            ) from exc
    else:
        try:
            from transformers import AutoModelForMultimodalLM, AutoProcessor
        except Exception as exc:
            raise SystemExit(f"multimodal loader requires a recent transformers version: {exc}") from exc
        try:
            processor = AutoProcessor.from_pretrained(
                base,
                local_files_only=args.local_files_only,
                trust_remote_code=args.trust_remote_code,
            )
        except Exception as exc:
            raise SystemExit(
                "Multimodal processor loading failed. Install the model's image "
                f"dependencies (typically torchvision and Pillow): {exc}"
            ) from exc
        model = AutoModelForMultimodalLM.from_pretrained(base, **kwargs)
        tokenizer = getattr(processor, "tokenizer", None) or tokenizer

    model.eval()

    if args.adapter_dir:
        emit({"event": "status", "stage": "loading_adapter", "detail": str(args.adapter_dir)})
        from peft import PeftModel
        adapter = _require_dir(args.adapter_dir, "adapter_dir")
        model = PeftModel.from_pretrained(model, adapter)
        model.eval()

    placement = _placement_info(torch, model)
    placement_desc = ", ".join(placement["devices"]) or "unknown"
    mem_desc = "; ".join(
        f"cuda:{m['index']} allocated={m['allocated_bytes']/2**30:.2f} GiB reserved={m['reserved_bytes']/2**30:.2f} GiB"
        for m in placement["cuda_memory"]
    )
    emit({
        "event": "status", "stage": "placement",
        "detail": f"devices={placement_desc}" + (f"; {mem_desc}" if mem_desc else ""),
        "placement": placement,
        "effective_4bit": effective_4bit,
    })
    if gpu_only_requested and placement["uses_cpu_or_disk"]:
        raise SystemExit(
            "GPU-only loading was requested, but the loaded model contains CPU/disk-offloaded modules: "
            f"{placement_desc}. Disable auto/offload or use quantization that fits in VRAM."
        )

    cfg = getattr(model, "config", None)
    ctx_total = int(
        args.ctx_total
        or getattr(cfg, "max_position_embeddings", 0)
        or getattr(cfg, "seq_length", 0)
        or 4096
    )
    text_cfg = getattr(cfg, "text_config", None)
    if not args.ctx_total and text_cfg is not None:
        ctx_total = int(
            getattr(text_cfg, "max_position_embeddings", 0)
            or getattr(text_cfg, "seq_length", 0)
            or ctx_total
        )

    emit({"event": "status", "stage": "model_loaded", "detail": f"context={ctx_total}; transformers={version}"})
    return {
        "torch": torch,
        "model": model,
        "tokenizer": tokenizer,
        "processor": processor,
        "ctx_total": ctx_total,
        "loader_type": loader_type,
        "transformers_version": version,
        "GenerationConfig": GenerationConfig,
        "cuda": cuda,
        "placement": placement,
        "input_device": _input_device(model),
        "effective_4bit": effective_4bit,
        "checkpoint_quantized": bool(checkpoint_quantization),
        "strip_thinking": bool(args.strip_thinking),
        "enable_thinking": bool(args.enable_thinking),
    }


def _encode_prompt(runtime: dict[str, Any], system: str, user: str) -> dict[str, Any]:
    """Apply the checkpoint chat template and tokenize it exactly once.

    Hugging Face chat templates already insert the model's special tokens. The
    old worker rendered the template to text and then called the tokenizer with
    its default ``add_special_tokens=True``, which can duplicate BOS/EOS/control
    tokens and materially hurt instruction following. Prefer direct tokenized
    chat-template output; keep an explicit ``add_special_tokens=False`` fallback
    for older/custom tokenizers.
    """
    tok = runtime["tokenizer"]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    if hasattr(tok, "apply_chat_template"):
        kwargs = {
            "tokenize": True,
            "add_generation_prompt": True,
            "return_tensors": "pt",
            "return_dict": True,
        }
        try:
            encoded = tok.apply_chat_template(
                messages,
                enable_thinking=runtime["enable_thinking"],
                **kwargs,
            )
            if isinstance(encoded, dict) or hasattr(encoded, "items"):
                return dict(encoded)
        except TypeError:
            pass

        try:
            encoded = tok.apply_chat_template(messages, **kwargs)
            if isinstance(encoded, dict) or hasattr(encoded, "items"):
                return dict(encoded)
        except TypeError:
            pass

        # Compatibility path for templates/tokenizers that cannot return a
        # BatchEncoding directly. Never add special tokens a second time.
        try:
            rendered = tok.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=runtime["enable_thinking"],
            )
        except TypeError:
            rendered = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        return dict(tok(rendered, return_tensors="pt", add_special_tokens=False))

    rendered = (f"[SYSTEM]\n{system}\n\n" if system else "") + f"[USER]\n{user}\n\n[ASSISTANT]\n"
    return dict(tok(rendered, return_tensors="pt", add_special_tokens=False))

def _score_exact_continuations(
    runtime: dict[str, Any],
    inputs: dict[str, Any],
    choices: list[str],
) -> dict[str, float]:
    """Return length-normalized log-likelihood for each exact continuation.

    The scored strings are literal continuations, not semantic class labels.  This
    primitive is intentionally context-agnostic: callers may compare the same
    continuations under multiple prompts to remove continuation-specific priors.
    """
    if not choices or any(not str(choice).strip() for choice in choices):
        raise ValueError("choice_outputs must contain non-empty strings")
    if len(set(choices)) != len(choices):
        raise ValueError("choice_outputs must be unique")

    torch = runtime["torch"]
    tok = runtime["tokenizer"]
    model = runtime["model"]
    input_device = runtime.get("input_device", getattr(model, "device", "cpu"))
    base_ids = inputs["input_ids"].to(input_device)
    base_mask = inputs.get("attention_mask")
    if base_mask is None:
        base_mask = torch.ones_like(base_ids)
    else:
        base_mask = base_mask.to(input_device)

    scores: dict[str, float] = {}
    for choice in choices:
        encoded = tok(str(choice), return_tensors="pt", add_special_tokens=False)
        choice_ids = encoded["input_ids"].to(input_device)
        if choice_ids.shape[-1] <= 0:
            raise ValueError(f"choice tokenized to an empty continuation: {choice!r}")
        full_ids = torch.cat((base_ids, choice_ids), dim=-1)
        full_mask = torch.cat((base_mask, torch.ones_like(choice_ids)), dim=-1)
        output = None
        logits = None
        selected = None
        token_log_probs = None
        try:
            with torch.inference_mode():
                output = model(input_ids=full_ids, attention_mask=full_mask, use_cache=False)
                logits = output.logits
                start = base_ids.shape[-1] - 1
                stop = start + choice_ids.shape[-1]
                selected = logits[:, start:stop, :].float().log_softmax(dim=-1)
                token_log_probs = selected.gather(-1, choice_ids.unsqueeze(-1)).squeeze(-1)
                scores[str(choice)] = float(token_log_probs.mean().item())
        finally:
            del token_log_probs
            del selected
            del logits
            del output
            del full_mask
            del full_ids
            del choice_ids
            del encoded
    return scores


def _rank_choice_scores(scores: dict[str, float]) -> tuple[str, float]:
    if not scores:
        raise RuntimeError("fixed-choice scoring produced no result")
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_choice, best_score = ranked[0]
    margin = float("inf") if len(ranked) == 1 else float(best_score - ranked[1][1])
    return best_choice, margin


def _score_fixed_choice_details(
    runtime: dict[str, Any],
    inputs: dict[str, Any],
    choices: list[str],
) -> dict[str, Any]:
    """Score exact continuations and expose the winner plus separation margin.

    The margin is parser evidence only.  It is never AH truth confidence and is
    never written to ``w``.  Returning it lets deterministic perception reject a
    nearly-tied fixed-choice decision without asking the SLM for confidence prose.
    """
    scores = _score_exact_continuations(runtime, inputs, choices)
    best_choice, margin = _rank_choice_scores(scores)
    return {
        "choice": best_choice,
        "choice_scores": scores,
        "choice_margin": margin,
        "choice_scoring_mode": "raw_exact_continuation",
    }


def _score_calibrated_choice_details(
    runtime: dict[str, Any],
    inputs: dict[str, Any],
    calibration_inputs: dict[str, Any],
    choices: list[str],
) -> dict[str, Any]:
    """Score semantic continuations after subtracting content-free priors.

    Each continuation is evaluated under the real lexical context and under a
    structurally identical neutral context.  Deterministic perception uses only
    the difference.  This removes stable token/phrase priors such as a model's
    preference for ``SECOND`` or for one longer semantic class name.
    """
    actual = _score_exact_continuations(runtime, inputs, choices)
    baseline = _score_exact_continuations(runtime, calibration_inputs, choices)
    calibrated = {choice: float(actual[choice] - baseline[choice]) for choice in choices}
    best_choice, calibrated_margin = _rank_choice_scores(calibrated)
    _raw_best, raw_margin = _rank_choice_scores(actual)
    return {
        "choice": best_choice,
        "choice_scores": actual,
        "calibration_choice_scores": baseline,
        "calibrated_choice_scores": calibrated,
        "raw_choice_margin": raw_margin,
        "choice_margin": calibrated_margin,
        "choice_scoring_mode": "content_free_calibrated_semantic_completion",
    }


def _score_fixed_choices(
    runtime: dict[str, Any],
    inputs: dict[str, Any],
    choices: list[str],
) -> str:
    """Select one exact continuation by model likelihood."""
    return str(_score_fixed_choice_details(runtime, inputs, choices)["choice"])


def generate(runtime: dict[str, Any], request: dict[str, Any], defaults: argparse.Namespace) -> str | dict[str, Any]:
    tok = runtime["tokenizer"]
    model = runtime["model"]
    inputs = _encode_prompt(runtime, str(request.get("system") or ""), str(request.get("prompt") or ""))
    override = request.get("override") or {}
    max_new = int(override.get("max_new_tokens", defaults.max_new_tokens))
    temperature = float(override.get("temperature", defaults.temperature))
    top_p = float(override.get("top_p", defaults.top_p))
    top_k = int(override.get("top_k", defaults.top_k))
    repetition_penalty = float(override.get("repetition_penalty", defaults.repetition_penalty))
    no_repeat_ngram_size = int(override.get("no_repeat_ngram_size", defaults.no_repeat_ngram_size))
    use_cache = bool(override.get("use_cache", True))

    input_ids = inputs["input_ids"]
    budget = max(1, runtime["ctx_total"] - max_new)
    if input_ids.shape[-1] > budget:
        input_ids = input_ids[:, -budget:]
        inputs["input_ids"] = input_ids
        if "attention_mask" in inputs:
            inputs["attention_mask"] = inputs["attention_mask"][:, -budget:]
    choice_outputs_raw = override.get("choice_outputs")
    if choice_outputs_raw is not None:
        if not isinstance(choice_outputs_raw, list):
            raise ValueError("choice_outputs must be a JSON list")
        choices = [str(item) for item in choice_outputs_raw]
        calibration_inputs = None
        try:
            calibration_prompt = override.get("choice_calibration_prompt")
            if calibration_prompt is not None:
                calibration_system = str(
                    override.get("choice_calibration_system", request.get("system") or "")
                )
                calibration_inputs = _encode_prompt(
                    runtime, calibration_system, str(calibration_prompt)
                )
                calibration_ids = calibration_inputs["input_ids"]
                if calibration_ids.shape[-1] > budget:
                    calibration_inputs["input_ids"] = calibration_ids[:, -budget:]
                    if "attention_mask" in calibration_inputs:
                        calibration_inputs["attention_mask"] = calibration_inputs["attention_mask"][:, -budget:]
                details = _score_calibrated_choice_details(
                    runtime, inputs, calibration_inputs, choices
                )
            else:
                details = _score_fixed_choice_details(runtime, inputs, choices)
            if bool(override.get("return_choice_scores", False)):
                return {"text": str(details["choice"]), **details}
            return str(details["choice"])
        finally:
            del calibration_inputs
            del inputs

    inputs = {k: v.to(runtime.get("input_device", getattr(model, "device", "cpu"))) for k, v in inputs.items()}

    # Construct a fresh request-local GenerationConfig. For greedy decoding we do
    # not set temperature/top_p/top_k at all; Transformers 5.x correctly warns when
    # sampling-only flags are explicitly present while do_sample=False.
    values = _generation_config_values(
        max_new=max_new,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        no_repeat_ngram_size=no_repeat_ngram_size,
        use_cache=use_cache,
        pad_token_id=(tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id),
        eos_token_id=tok.eos_token_id,
        bos_token_id=getattr(tok, "bos_token_id", None),
    )
    gc = runtime["GenerationConfig"](**values)

    out = None
    generated = None
    try:
        with runtime["torch"].inference_mode():
            out = model.generate(**inputs, generation_config=gc)
        generated = out[0, inputs["input_ids"].shape[-1]:]
        text = tok.decode(generated, skip_special_tokens=True).strip()
        return _strip_thinking(text) if runtime["strip_thinking"] else text
    finally:
        # Generation caches and request tensors are strictly request-local.  Drop
        # all references before the next JSONL request; on CUDA also return unused
        # allocator blocks so WDDM cannot keep a large transient generation working
        # set resident as shared system memory across many independent probes.
        del generated
        del out
        del inputs
        del gc
        torch = runtime["torch"]
        cuda = getattr(torch, "cuda", None)
        if use_cache and cuda is not None and cuda.is_available():
            cuda.empty_cache()


def serve(runtime: dict[str, Any], args: argparse.Namespace) -> None:
    emit({
        "ok": True,
        "ready": True,
        "loader_type": runtime["loader_type"],
        "ctx_total": runtime["ctx_total"],
        "model_dir": str(Path(args.model_dir).expanduser().resolve()),
        "transformers_version": runtime.get("transformers_version"),
        "cuda": runtime.get("cuda"),
        "placement": runtime.get("placement"),
        "effective_4bit": runtime.get("effective_4bit"),
        "checkpoint_quantized": runtime.get("checkpoint_quantized"),
    })
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            emit({"ok": False, "error": f"invalid_json: {exc}"})
            continue
        if req.get("req") == "shutdown":
            break
        req_id = str(req.get("req_id") or "")
        try:
            if req.get("req") != "generate":
                raise ValueError(f"unsupported request: {req.get('req')}")
            generated = generate(runtime, req, args)
            if isinstance(generated, dict):
                payload = dict(generated)
                payload["text"] = str(payload.get("text", ""))
            else:
                payload = {"text": generated}
            emit({"req_id": req_id, "ok": True, "final": True, "role": req.get("role", "generic"), **payload})
        except Exception as exc:
            emit({"req_id": req_id, "ok": False, "final": True, "text": "", "error": str(exc)})


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--model-dir", required=True)
    p.add_argument("--tokenizer-dir", default="")
    p.add_argument("--adapter-dir", default="")
    p.add_argument("--loader-type", default="auto")
    p.add_argument("--device-map", default="auto")
    p.add_argument("--dtype", default="auto")
    p.add_argument("--ctx-total", type=int, default=0)
    p.add_argument("--use-4bit", action="store_true")
    p.add_argument("--local-files-only", action="store_true")
    p.add_argument("--trust-remote-code", action="store_true")
    p.add_argument("--enable-thinking", action="store_true")
    p.add_argument("--strip-thinking", action="store_true")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--max-new-tokens", type=int, default=256)
    p.add_argument("--temperature", type=float, default=0.2)
    p.add_argument("--top-p", type=float, default=0.9)
    p.add_argument("--top-k", type=int, default=40)
    p.add_argument("--repetition-penalty", type=float, default=1.05)
    p.add_argument("--no-repeat-ngram-size", type=int, default=0)
    return p.parse_args()


def main() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    args = parse_args()
    runtime = load_runtime(args)
    if not args.serve:
        raise SystemExit("worker requires --serve")
    serve(runtime, args)


if __name__ == "__main__":
    main()
