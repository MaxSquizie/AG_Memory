from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import json


def pretty_json(value) -> str:
    def encode(obj):
        if isinstance(obj, Enum):
            return obj.value
        return str(obj)
    return json.dumps(value, ensure_ascii=False, indent=2, default=encode)


def perception_call_phase(diag) -> str:
    roles = {attempt.role for attempt in diag.attempts}
    if roles <= {"template_sense"}:
        return "post-parse lexical template sense"
    if roles <= {"clarification_answer"}:
        return "clarification answer interpretation"
    if roles <= {"perception", "perception_repair"}:
        return "legacy single-shot perception"
    return "adaptive semantic parse"


def format_parser_raw_history(history, *, turn_source_text: str = "") -> str:
    if not history:
        return ""
    parts = [
        "PERCEPTION TIMELINE (runtime order)",
        f"TURN SOURCE:\n{turn_source_text or history[0].source_text}",
        f"PERCEPTION CALLS: {len(history)}",
    ]
    step = 0
    for call_index, diag in enumerate(history, start=1):
        parts.append(
            f"\n{'='*72}\nPERCEPTION CALL {call_index}/{len(history)} — {perception_call_phase(diag)}\n"
            f"STATUS: {'FAILED' if diag.final_error else 'OK'} | diagnostic #{diag.sequence}\n"
            f"CALL SOURCE:\n{diag.source_text}\n{'='*72}"
        )
        for attempt in diag.attempts:
            step += 1
            retry = f" retry={attempt.retry_index}" if attempt.retry_index else ""
            parts.append(f"\n--- STEP {step}: {attempt.role}{retry} — {'FAILED' if attempt.error else 'OK'} ---")
            if attempt.prompt:
                parts.append(f"\nINPUT:\n{attempt.prompt}")
            parts.append(f"\nRAW:\n{attempt.raw_text or '<empty>'}")
            if attempt.normalized_answer is not None:
                parts.append(f"\nACCEPTED: {attempt.normalized_answer}")
            if attempt.error:
                parts.append(f"\nWHY IT FAILED: {attempt.error}")
        if diag.final_error:
            parts.append(f"\nCALL FINAL ERROR: {diag.final_error}")
    return "\n".join(parts)


def format_parser_decoded_history(history):
    calls = []
    for diag in history:
        item = {
            "sequence": diag.sequence,
            "phase": perception_call_phase(diag),
            "source_text": diag.source_text,
            "status": "INVALID" if diag.final_error else "OK",
            "error": diag.final_error,
            "perception": None if diag.decoded is None else asdict(diag.decoded),
        }
        calls.append(item)
    return {"calls": calls, "status": "INVALID" if any(d.final_error for d in history) else "OK"}
