from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from transformers import AutoModelForMultimodalLM, AutoProcessor, TextIteratorStreamer


# ============================================================================
# Configuration
# ============================================================================

MODEL_PATH = r"C:\AI\qwen3.8_27b_fp8"
SERVED_MODEL_NAME = "qwen3.8-27b"

HOST = "127.0.0.1"
PORT = 8000

# Qwen3.8's official default is xhigh. Medium is a better default for an
# interactive agent UI; Vellium can still override it by sending
# "reasoning_effort" in the request.
DEFAULT_REASONING_EFFORT = os.getenv("QWEN_REASONING_EFFORT", "medium").strip() or "medium"

# Keep thinking enabled so Vellium can display it separately.
DEFAULT_ENABLE_THINKING = os.getenv("QWEN_ENABLE_THINKING", "1").strip().lower() not in {
    "0", "false", "no", "off"
}

# Old reasoning does not need to be re-injected into every prompt. This is
# especially useful in long agent/tool loops. It also avoids context bloat.
PRESERVE_OLD_THINKING = os.getenv("QWEN_PRESERVE_OLD_THINKING", "0").strip().lower() in {
    "1", "true", "yes", "on"
}

# One Transformers model object + one GPU should not run multiple generate()
# calls concurrently. Vellium can launch subagents concurrently, so requests
# are serialized here for stability rather than causing duplicate KV caches/OOM.
generation_lock = threading.Lock()

app = FastAPI(title="Qwen3.8-27B Vellium Local Server")


# ============================================================================
# Startup
# ============================================================================

model_dir = Path(MODEL_PATH)

print("=" * 80)
print("Qwen3.8-27B local server for Vellium")
print(f"Model path: {MODEL_PATH}")
print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
    print(f"VRAM: {total_gb:.2f} GiB")

print(f"Default reasoning effort: {DEFAULT_REASONING_EFFORT}")
print(f"Thinking enabled: {DEFAULT_ENABLE_THINKING}")
print(f"Preserve old thinking: {PRESERVE_OLD_THINKING}")
print("=" * 80)

print("Loading processor...")

processor = AutoProcessor.from_pretrained(
    MODEL_PATH,
    local_files_only=True,
)

# Always use the local chat template. This lets you keep the fixed Qwen3.8
# chat_template.jinja directly next to the model.
chat_template_path = model_dir / "chat_template.jinja"

if chat_template_path.exists():
    processor.chat_template = chat_template_path.read_text(encoding="utf-8")
    first_line = processor.chat_template.splitlines()[0] if processor.chat_template else ""
    print(f"Chat template: {chat_template_path}")
    print(f"Chat template first line: {first_line}")
elif not getattr(processor, "chat_template", None):
    raise RuntimeError(
        f"No chat template found. Expected: {chat_template_path}"
    )
else:
    print("Chat template: loaded by Transformers")

config_path = model_dir / "config.json"
quantization_config = None

if config_path.exists():
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        quantization_config = raw_config.get("quantization_config")
        print(f"Checkpoint dtype: {raw_config.get('torch_dtype')}")
        print(f"Quantization config: {quantization_config}")
    except Exception as exc:
        print(f"Warning: could not inspect config.json: {exc}")

print("Loading model...")

# Do not force BF16. If the checkpoint is FP8/quantized, forcing BF16 defeats
# the purpose and can push a 27B model into CPU offload.
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype="auto",
    device_map="cuda",
    local_files_only=True,
)

model.eval()

print("Model loaded.")
print(f"model.device: {model.device}")

device_map = getattr(model, "hf_device_map", None)
if device_map is not None:
    print("hf_device_map:")
    for index, (name, device) in enumerate(device_map.items()):
        if index >= 80:
            print(f"... ({len(device_map) - 80} more entries)")
            break
        print(f"  {name or '<root>'}: {device}")

meta_params = [
    name
    for name, param in model.named_parameters()
    if param.device.type == "meta"
]

print(f"Parameters currently on meta device: {len(meta_params)}")
for name in meta_params[:30]:
    print(f"  META: {name}")
if len(meta_params) > 30:
    print(f"  ... and {len(meta_params) - 30} more")

print("=" * 80)


# ============================================================================
# API request models
# ============================================================================

class GenerateRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 512
    temperature: float = 0.9
    top_p: float = 0.95


class ChatRequest(BaseModel):
    # Vellium sends additional OpenAI-compatible fields. Keep them instead of
    # silently rejecting/losing them.
    model_config = ConfigDict(extra="allow")

    model: str = SERVED_MODEL_NAME
    messages: list[dict[str, Any]]
    stream: bool = False

    max_tokens: int | None = None
    max_completion_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: str | list[str] | None = None

    tools: list[dict[str, Any]] | None = None
    tool_choice: Any = None
    response_format: dict[str, Any] | None = None

    reasoning_effort: str | None = None
    enable_thinking: bool | None = None


# ============================================================================
# Message normalization
# ============================================================================

def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" or "text" in item:
                text = item.get("text")
                if text is not None:
                    parts.append(str(text))
            elif item.get("type") in {"image", "image_url"} or "image_url" in item:
                parts.append("[Image attachment]")
        return "\n".join(parts).strip()
    return str(content)


def _normalize_tool_history(message: dict[str, Any]) -> dict[str, Any]:
    """
    Qwen's template wants historical tool-call arguments as a mapping.
    Vellium/OpenAI-compatible history normally stores them as a JSON string.
    Convert string JSON back to an object before feeding the Jinja template.
    """
    result = copy.deepcopy(message)
    tool_calls = result.get("tool_calls")
    if not isinstance(tool_calls, list):
        return result

    normalized_calls: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        call_copy = copy.deepcopy(call)
        function = call_copy.get("function")
        if isinstance(function, dict):
            args = function.get("arguments")
            if isinstance(args, str):
                try:
                    decoded = json.loads(args)
                    if isinstance(decoded, dict):
                        function["arguments"] = decoded
                except Exception:
                    # Keep malformed/non-JSON arguments as-is. The fixed
                    # Qwen template can still handle strings.
                    pass
        normalized_calls.append(call_copy)

    result["tool_calls"] = normalized_calls
    return result


def _response_format_instruction(response_format: dict[str, Any] | None) -> str:
    if not isinstance(response_format, dict):
        return ""

    format_type = str(response_format.get("type") or "").strip().lower()

    if format_type == "json_object":
        return (
            "OUTPUT FORMAT REQUIREMENT:\n"
            "Return ONLY one valid JSON object. Do not wrap it in Markdown or "
            "code fences. Do not add any text before or after the JSON object."
        )

    if format_type == "json_schema":
        schema_box = response_format.get("json_schema")
        schema: Any = None
        if isinstance(schema_box, dict):
            schema = schema_box.get("schema")

        if schema is None:
            return (
                "OUTPUT FORMAT REQUIREMENT:\n"
                "Return ONLY one valid JSON object. Do not use Markdown."
            )

        return (
            "OUTPUT FORMAT REQUIREMENT:\n"
            "Return ONLY one valid JSON object that matches the following JSON "
            "Schema. Do not wrap it in Markdown or code fences. Do not add any "
            "text before or after the object.\n\nJSON SCHEMA:\n"
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        )

    return ""


def _tool_choice_instruction(tool_choice: Any, tools: list[dict[str, Any]] | None) -> str:
    if not tools:
        return ""

    if tool_choice == "required":
        return (
            "TOOL REQUIREMENT:\n"
            "You MUST call at least one of the provided tools in this turn."
        )

    if isinstance(tool_choice, dict):
        function = tool_choice.get("function")
        if isinstance(function, dict):
            name = str(function.get("name") or "").strip()
            if name:
                return (
                    "TOOL REQUIREMENT:\n"
                    f"You MUST call the tool named {name!r} in this turn."
                )

    return ""


def _normalize_messages(
    messages: list[dict[str, Any]],
    response_format: dict[str, Any] | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
) -> list[dict[str, Any]]:
    """
    Vellium can insert system/developer messages during tool/agent loops.
    Qwen's official template historically required system to be first, so
    coalesce all system/developer instructions into one first system message.
    """
    source = [_normalize_tool_history(m) for m in copy.deepcopy(messages)]

    system_parts: list[str] = []
    normal_messages: list[dict[str, Any]] = []

    for message in source:
        role = str(message.get("role") or "user").strip().lower()

        if role in {"system", "developer"}:
            text = _content_to_text(message.get("content")).strip()
            if text:
                system_parts.append(text)
            continue

        message["role"] = role

        # Qwen handles None poorly in some template branches.
        if role == "assistant" and message.get("content") is None:
            message["content"] = ""

        normal_messages.append(message)

    structured_instruction = _response_format_instruction(response_format)
    if structured_instruction:
        system_parts.append(structured_instruction)

    tool_instruction = _tool_choice_instruction(tool_choice, tools)
    if tool_instruction:
        system_parts.append(tool_instruction)

    normalized: list[dict[str, Any]] = []
    if system_parts:
        normalized.append({
            "role": "system",
            "content": "\n\n".join(system_parts),
        })

    normalized.extend(normal_messages)

    if not normalized:
        normalized = [{"role": "user", "content": ""}]

    return normalized


def _resolve_tools(req: ChatRequest) -> list[dict[str, Any]] | None:
    if req.tool_choice == "none":
        return None
    return req.tools if req.tools else None


# ============================================================================
# Qwen prompt + generation
# ============================================================================

def _reasoning_effort(req: ChatRequest | None) -> str:
    raw = (req.reasoning_effort if req is not None else None) or DEFAULT_REASONING_EFFORT
    raw = str(raw).strip().lower()

    # Qwen3.8 currently documents xhigh / medium / low.
    aliases = {
        "high": "xhigh",
        "x-high": "xhigh",
        "normal": "medium",
        "default": "medium",
    }
    raw = aliases.get(raw, raw)

    if raw not in {"xhigh", "medium", "low"}:
        raw = DEFAULT_REASONING_EFFORT if DEFAULT_REASONING_EFFORT in {"xhigh", "medium", "low"} else "medium"

    return raw


def _thinking_enabled(req: ChatRequest | None) -> bool:
    if req is not None and req.enable_thinking is not None:
        return bool(req.enable_thinking)
    return DEFAULT_ENABLE_THINKING


def _prepare_inputs(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    reasoning_effort: str,
    enable_thinking: bool,
):
    template_kwargs: dict[str, Any] = {
        "add_generation_prompt": True,
        "tokenize": True,
        "return_dict": True,
        "return_tensors": "pt",
        "reasoning_effort": reasoning_effort,
        "enable_thinking": enable_thinking,
        "preserve_thinking": PRESERVE_OLD_THINKING,
    }

    if tools:
        template_kwargs["tools"] = tools

    # ProcessorMixin.apply_chat_template() expects the conversation as its
    # first positional argument in current Transformers versions.
    inputs = processor.apply_chat_template(
        messages,
        **template_kwargs,
    )
    return inputs.to(model.device)


def _generation_args(req: ChatRequest | None = None, *, max_new_tokens: int | None = None,
                     temperature: float | None = None, top_p: float | None = None) -> dict[str, Any]:
    if req is not None:
        requested_max = req.max_completion_tokens or req.max_tokens or 2048
        requested_temperature = 0.9 if req.temperature is None else float(req.temperature)
        requested_top_p = 0.95 if req.top_p is None else float(req.top_p)
        requested_top_k = 20 if req.top_k is None else int(req.top_k)
        stop = req.stop
    else:
        requested_max = max_new_tokens or 512
        requested_temperature = 0.9 if temperature is None else float(temperature)
        requested_top_p = 0.95 if top_p is None else float(top_p)
        requested_top_k = 20
        stop = None

    requested_max = max(1, min(int(requested_max), 32768))
    do_sample = requested_temperature > 0

    args: dict[str, Any] = {
        "max_new_tokens": requested_max,
        "do_sample": do_sample,
    }

    if do_sample:
        args["temperature"] = max(0.01, requested_temperature)
        args["top_p"] = max(0.01, min(1.0, requested_top_p))
        args["top_k"] = max(0, requested_top_k)

    if stop:
        stop_strings = [stop] if isinstance(stop, str) else [str(x) for x in stop if str(x)]
        if stop_strings:
            args["stop_strings"] = stop_strings
            args["tokenizer"] = processor.tokenizer

    return args


# ============================================================================
# Output parsing: reasoning + native Qwen tool XML
# ============================================================================

THINK_END = "</think>"


def _split_reasoning(text: str, enable_thinking: bool) -> tuple[str, str]:
    raw = str(text or "")

    if not enable_thinking:
        # Some templates may still produce empty think tags even when disabled.
        raw = re.sub(r"^\s*<think>\s*</think>\s*", "", raw, count=1)
        return "", raw.strip()

    # Depending on streamer/decode boundaries, <think> can either be part of
    # the prompt or appear in generated text.
    raw = re.sub(r"^\s*<think>\s*", "", raw, count=1)

    if THINK_END in raw:
        reasoning, content = raw.split(THINK_END, 1)
        return reasoning.strip(), content.strip()

    # If the model exhausted max tokens while still thinking, expose that as
    # reasoning rather than pretending it is a final answer.
    return raw.strip(), ""


def _maybe_json_value(text: str) -> Any:
    value = text.strip()
    if value == "":
        return ""

    # Preserve ordinary strings; decode explicit JSON values/numbers/objects.
    first = value[:1]
    if first in {'{', '[', '"'} or value in {"true", "false", "null"} or re.fullmatch(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", value):
        try:
            return json.loads(value)
        except Exception:
            pass
    return value


def _parse_qwen_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Convert Qwen3.8's native:
        <tool_call>
        <function=name>
        <parameter=x>...</parameter>
        </function>
        </tool_call>

    into standard OpenAI-compatible message.tool_calls.
    Also accepts JSON inside <tool_call> for fixed-template JSON mode.
    """
    source = str(text or "")
    tool_calls: list[dict[str, Any]] = []

    block_pattern = re.compile(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", re.IGNORECASE)

    for block_index, match in enumerate(block_pattern.finditer(source)):
        body = match.group(1).strip()

        # JSON-style fixed-template output.
        if body.startswith("{"):
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = None

            if isinstance(parsed, dict):
                name = str(
                    parsed.get("name")
                    or parsed.get("tool")
                    or parsed.get("tool_name")
                    or (
                        parsed.get("function", {}).get("name")
                        if isinstance(parsed.get("function"), dict)
                        else ""
                    )
                    or ""
                ).strip()

                arguments = (
                    parsed.get("arguments")
                    if "arguments" in parsed
                    else parsed.get("args", parsed.get("input", {}))
                )

                if isinstance(parsed.get("function"), dict) and "arguments" in parsed["function"]:
                    arguments = parsed["function"]["arguments"]

                if name:
                    if isinstance(arguments, str):
                        args_string = arguments
                    else:
                        args_string = json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)

                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:16]}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": args_string,
                        },
                    })
                    continue

        # Native Qwen XML function format.
        function_match = re.search(
            r"<function=([^>\r\n]+)>\s*([\s\S]*?)\s*</function>",
            body,
            re.IGNORECASE,
        )
        if not function_match:
            continue

        name = function_match.group(1).strip()
        function_body = function_match.group(2)

        args: dict[str, Any] = {}
        param_pattern = re.compile(
            r"<parameter=([^>\r\n]+)>\s*([\s\S]*?)\s*</parameter>",
            re.IGNORECASE,
        )

        for parameter in param_pattern.finditer(function_body):
            param_name = parameter.group(1).strip()
            param_value = parameter.group(2)
            if param_name:
                args[param_name] = _maybe_json_value(param_value)

        if name:
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:16]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            })

    visible = block_pattern.sub("", source).strip()
    return visible, tool_calls


def _normalize_structured_content(content: str, response_format: dict[str, Any] | None) -> str:
    if not response_format:
        return content

    format_type = str(response_format.get("type") or "").lower()
    if format_type not in {"json_object", "json_schema"}:
        return content

    text = str(content or "").strip()

    # Strip a Markdown JSON fence if the model ignored the instruction.
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()

    # Prefer a real JSON object and canonicalize it. This makes Vellium's
    # structured planner materially more reliable.
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[index:])
        except Exception:
            continue
        if isinstance(parsed, dict):
            return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    return text


def _build_nonstream_result(req: ChatRequest) -> dict[str, Any]:
    tools = _resolve_tools(req)
    enable_thinking = _thinking_enabled(req)
    effort = _reasoning_effort(req)

    messages = _normalize_messages(
        req.messages,
        response_format=req.response_format,
        tools=tools,
        tool_choice=req.tool_choice,
    )

    inputs = _prepare_inputs(
        messages=messages,
        tools=tools,
        reasoning_effort=effort,
        enable_thinking=enable_thinking,
    )

    input_len = int(inputs["input_ids"].shape[-1])

    with generation_lock:
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                **_generation_args(req),
            )

    generated_ids = output[0][input_len:]
    raw_text = processor.decode(generated_ids, skip_special_tokens=True)

    reasoning, content = _split_reasoning(raw_text, enable_thinking)
    visible_content, tool_calls = _parse_qwen_tool_calls(content)
    visible_content = _normalize_structured_content(visible_content, req.response_format)

    message: dict[str, Any] = {
        "role": "assistant",
        "content": visible_content,
    }

    # Vellium explicitly understands reasoning_content for local providers.
    if reasoning:
        message["reasoning_content"] = reasoning

    if tool_calls:
        message["tool_calls"] = tool_calls

    finish_reason = "tool_calls" if tool_calls else ("stop" if visible_content else "length")

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }


# ============================================================================
# True token streaming
# ============================================================================

class _ThinkingStreamSplitter:
    """
    Qwen's generation prompt normally already contains '<think>\\n', so the
    first generated tokens are reasoning and the generated stream later emits
    '</think>'. This splitter handles the marker even when it is split across
    streamer chunks.
    """

    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.in_reasoning = enabled
        self.buffer = ""
        self.at_start = True

    def feed(self, chunk: str) -> tuple[str, str]:
        if not chunk:
            return "", ""

        if not self.in_reasoning:
            return "", chunk

        self.buffer += chunk

        # Defensive support for a generated opening tag.
        if self.at_start:
            self.at_start = False
            self.buffer = re.sub(r"^\s*<think>\s*", "", self.buffer, count=1)

        marker_index = self.buffer.find(THINK_END)

        if marker_index >= 0:
            reasoning = self.buffer[:marker_index]
            content = self.buffer[marker_index + len(THINK_END):]
            self.buffer = ""
            self.in_reasoning = False
            return reasoning, content

        # Retain enough suffix characters to recognize a marker split across
        # adjacent TextIteratorStreamer chunks.
        keep = max(0, len(THINK_END) - 1)
        if len(self.buffer) <= keep:
            return "", ""

        safe = self.buffer[:-keep]
        self.buffer = self.buffer[-keep:]
        return safe, ""

    def flush(self) -> tuple[str, str]:
        if not self.buffer:
            return "", ""
        remaining = self.buffer
        self.buffer = ""
        if self.in_reasoning:
            return remaining, ""
        return "", remaining


def _sse(payload: Any) -> str:
    if payload == "[DONE]":
        return "data: [DONE]\n\n"
    return "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _stream_chunk(
    request_id: str,
    model_name: str,
    *,
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    delta: dict[str, Any] = {}

    if content is not None:
        delta["content"] = content
    if reasoning is not None:
        delta["reasoning_content"] = reasoning
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls

    return {
        "id": request_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }


def _stream_completion(req: ChatRequest) -> Iterator[str]:
    request_id = f"chatcmpl-{uuid.uuid4().hex}"
    tools = _resolve_tools(req)
    enable_thinking = _thinking_enabled(req)
    effort = _reasoning_effort(req)

    messages = _normalize_messages(
        req.messages,
        response_format=req.response_format,
        tools=tools,
        tool_choice=req.tool_choice,
    )

    try:
        inputs = _prepare_inputs(
            messages=messages,
            tools=tools,
            reasoning_effort=effort,
            enable_thinking=enable_thinking,
        )
    except Exception as exc:
        yield _sse({
            "error": {
                "message": f"Prompt/template error: {exc}",
                "type": "server_error",
            }
        })
        yield _sse("[DONE]")
        return

    # A first role chunk improves compatibility with generic clients.
    yield _sse(_stream_chunk(
        request_id,
        req.model,
        content=None,
        finish_reason=None,
    ) | {
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant"},
            "finish_reason": None,
        }]
    })

    streamer = TextIteratorStreamer(
        processor.tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )

    generation_errors: list[BaseException] = []

    def worker():
        try:
            with torch.inference_mode():
                model.generate(
                    **inputs,
                    **_generation_args(req),
                    streamer=streamer,
                )
        except BaseException as exc:
            generation_errors.append(exc)
            # Prevent the HTTP stream from hanging forever if generate() fails
            # before Transformers can push its end-of-stream sentinel.
            try:
                streamer.on_finalized_text("", stream_end=True)
            except Exception:
                pass

    splitter = _ThinkingStreamSplitter(enable_thinking)
    reasoning_accumulator: list[str] = []
    content_accumulator: list[str] = []

    # When tools are present, buffer final assistant text until generation ends.
    # This prevents Qwen's native <tool_call> XML from leaking into Vellium's
    # visible assistant message. Reasoning still streams live.
    buffer_final_for_tools = bool(tools)

    with generation_lock:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        try:
            for piece in streamer:
                reasoning_piece, content_piece = splitter.feed(piece)

                if reasoning_piece:
                    reasoning_accumulator.append(reasoning_piece)
                    yield _sse(_stream_chunk(
                        request_id,
                        req.model,
                        reasoning=reasoning_piece,
                    ))

                if content_piece:
                    content_accumulator.append(content_piece)
                    if not buffer_final_for_tools:
                        yield _sse(_stream_chunk(
                            request_id,
                            req.model,
                            content=content_piece,
                        ))

            tail_reasoning, tail_content = splitter.flush()

            if tail_reasoning:
                reasoning_accumulator.append(tail_reasoning)
                yield _sse(_stream_chunk(
                    request_id,
                    req.model,
                    reasoning=tail_reasoning,
                ))

            if tail_content:
                content_accumulator.append(tail_content)
                if not buffer_final_for_tools:
                    yield _sse(_stream_chunk(
                        request_id,
                        req.model,
                        content=tail_content,
                    ))

            thread.join()

        except BaseException as exc:
            generation_errors.append(exc)

    if generation_errors:
        message = str(generation_errors[0])
        yield _sse({
            "error": {
                "message": message,
                "type": "server_error",
            }
        })
        yield _sse("[DONE]")
        return

    full_content = "".join(content_accumulator)
    visible_content, parsed_tool_calls = _parse_qwen_tool_calls(full_content)
    visible_content = _normalize_structured_content(visible_content, req.response_format)

    if buffer_final_for_tools:
        if visible_content:
            # Chunk it so Vellium receives responsive UI updates even though we
            # intentionally buffered the tool-sensitive final section.
            for index in range(0, len(visible_content), 140):
                yield _sse(_stream_chunk(
                    request_id,
                    req.model,
                    content=visible_content[index:index + 140],
                ))

        for index, call in enumerate(parsed_tool_calls):
            yield _sse(_stream_chunk(
                request_id,
                req.model,
                tool_calls=[{
                    "index": index,
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["function"]["name"],
                        "arguments": call["function"]["arguments"],
                    },
                }],
            ))

    finish_reason = "tool_calls" if parsed_tool_calls else (
        "stop" if visible_content or reasoning_accumulator else "length"
    )

    yield _sse(_stream_chunk(
        request_id,
        req.model,
        finish_reason=finish_reason,
    ))
    yield _sse("[DONE]")


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_PATH,
        "served_model_name": SERVED_MODEL_NAME,
        "device": str(model.device),
        "reasoning_effort": DEFAULT_REASONING_EFFORT,
        "thinking_enabled": DEFAULT_ENABLE_THINKING,
        "meta_parameters": len([
            name
            for name, param in model.named_parameters()
            if param.device.type == "meta"
        ]),
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": SERVED_MODEL_NAME,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    if req.stream:
        return StreamingResponse(
            _stream_completion(req),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        return _build_nonstream_result(req)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate")
def generate(req: GenerateRequest):
    chat_req = ChatRequest(
        model=SERVED_MODEL_NAME,
        messages=[{"role": "user", "content": req.prompt}],
        stream=False,
        max_tokens=req.max_new_tokens,
        temperature=req.temperature,
        top_p=req.top_p,
    )

    result = _build_nonstream_result(chat_req)
    message = result["choices"][0]["message"]

    return {
        "response": message.get("content", ""),
        "reasoning": message.get("reasoning_content", ""),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info",
    )
