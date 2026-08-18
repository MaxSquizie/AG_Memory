from __future__ import annotations

from dataclasses import asdict
from enum import Enum
import json

from ah.perception import PerceptionDiagnostic


def perception_call_phase(diag: PerceptionDiagnostic) -> str:
    roles = {attempt.role for attempt in diag.attempts}
    if roles <= {"template_sense"}:
        return "post-parse: lexical template sense (orchestrator)"
    if roles <= {"perception", "perception_repair"}:
        return "legacy single-shot perception"
    if roles <= {"clarification_answer"}:
        return "clarification answer interpretation"
    return "adaptive semantic parse"


def format_parser_raw_history(
    history: tuple[PerceptionDiagnostic, ...],
    *,
    turn_source_text: str = "",
) -> str:
    if not history:
        return ""
    parts = [
        "PERCEPTION TIMELINE (ordered by runtime; not the prompt-file list in "
        "'Perception probe')",
        f"TURN SOURCE:\n{turn_source_text or history[0].source_text}",
        f"PERCEPTION CALLS: {len(history)}",
    ]
    probe_index = 0
    for call_index, diag in enumerate(history, start=1):
        phase = perception_call_phase(diag)
        call_status = "OK" if diag.final_error is None else "FAILED"
        parts.append(
            f"\n{'=' * 72}\n"
            f"PERCEPTION CALL {call_index}/{len(history)} — {phase}\n"
            f"STATUS: {call_status} | diagnostic #{diag.sequence}\n"
            f"CALL SOURCE:\n{diag.source_text}\n"
            f"{'=' * 72}"
        )
        if not diag.attempts:
            parts.append("\n(no probe attempts were recorded for this call)")
        for attempt in diag.attempts:
            probe_index += 1
            retry = f" retry={attempt.retry_index}" if attempt.retry_index else ""
            probe_status = "FAILED" if attempt.error else "OK"
            parts.append(
                f"\n--- STEP {probe_index}: {attempt.role}{retry} — {probe_status} ---"
            )
            if attempt.prompt:
                parts.append(f"\nINPUT:\n{attempt.prompt}")
            parts.append(f"\nRAW:\n{attempt.raw_text or '<empty>'}")
            if attempt.normalized_answer is not None:
                parts.append(f"\nACCEPTED: {attempt.normalized_answer}")
            if attempt.error:
                parts.append(f"\nWHY IT FAILED: {attempt.error}")
        if diag.final_error:
            parts.append(f"\nCALL FINAL ERROR: {diag.final_error}")
    turn_status = "FAILED" if any(d.final_error for d in history) else "OK"
    parts.append(f"\nTURN PERCEPTION STATUS: {turn_status}")
    return "\n".join(parts)


def format_parser_decoded_history(history: tuple[PerceptionDiagnostic, ...]) -> dict[str, object]:
    calls: list[dict[str, object]] = []
    for call_index, diag in enumerate(history, start=1):
        entry: dict[str, object] = {
            "call": call_index,
            "diagnostic_sequence": diag.sequence,
            "phase": perception_call_phase(diag),
            "source_text": diag.source_text,
            "status": "OK" if diag.final_error is None else "FAILED",
            "probes": [
                {
                    "step": index,
                    "role": attempt.role,
                    "status": "FAILED" if attempt.error else "OK",
                    "raw_text": attempt.raw_text,
                    "accepted": attempt.normalized_answer,
                    "error": attempt.error,
                }
                for index, attempt in enumerate(diag.attempts, start=1)
            ],
        }
        if diag.final_error:
            entry["error"] = diag.final_error
        if diag.decoded is not None:
            entry["perception"] = asdict(diag.decoded)
        calls.append(entry)
    return {
        "status": "FAILED" if any(d.final_error for d in history) else "OK",
        "calls": calls,
    }


def pretty_json(value: object) -> str:
    def encode(obj: object) -> str:
        if isinstance(obj, Enum):
            return obj.value
        return str(obj)

    return json.dumps(value, ensure_ascii=False, indent=2, default=encode)
