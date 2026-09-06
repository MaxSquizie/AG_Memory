from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from typing import Any, TYPE_CHECKING

from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

from .acceptance_runner import canonical_ah_snapshot, diff_canonical_ah

if TYPE_CHECKING:
    from ah.bootstrap import RuntimeServices


RUNS_DIRNAME = "hidden_valency_diagnostics"
_DIAGNOSTIC_ROLE = "perception_hidden_valency_diagnostic"


@dataclass(frozen=True, slots=True)
class HiddenValencyDiagnosticCase:
    case_id: str
    sentence: str
    verb: str
    tested_role: ActantRole
    known_roles: tuple[tuple[ActantRole, str], ...]
    expected_label: str


@dataclass(frozen=True, slots=True)
class HiddenValencyDiagnosticResult:
    output_dir: Path
    archive_path: Path
    cases: int
    calls: int
    semantic_ok: int
    order_bias: int
    semantic_wrong: int
    inconsistent: int
    malformed: int
    exact_protocol_calls: int
    wrapper_recovered_calls: int
    first_choice_calls: int
    ah_unchanged: bool


_DIAGNOSTIC_CASES = (
    HiddenValencyDiagnosticCase(
        "recipient_positive_give",
        "Иван подарил книгу.",
        "подарить",
        ActantRole.RECIPIENT,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        "HAS_RECIPIENT_SLOT",
    ),
    HiddenValencyDiagnosticCase(
        "recipient_negative_love",
        "Иван любит чай.",
        "любить",
        ActantRole.RECIPIENT,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "чай")),
        "NO_RECIPIENT_SLOT",
    ),
    HiddenValencyDiagnosticCase(
        "recipient_negative_defeat",
        "Иван победил Петра.",
        "победить",
        ActantRole.RECIPIENT,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "Пётр")),
        "NO_RECIPIENT_SLOT",
    ),
    HiddenValencyDiagnosticCase(
        "source_positive_receive",
        "Иван получил книгу.",
        "получить",
        ActantRole.SOURCE,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        "HAS_SOURCE_SLOT",
    ),
    HiddenValencyDiagnosticCase(
        "source_negative_love",
        "Иван любит чай.",
        "любить",
        ActantRole.SOURCE,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "чай")),
        "NO_SOURCE_SLOT",
    ),
    HiddenValencyDiagnosticCase(
        "source_negative_give",
        "Иван подарил книгу.",
        "подарить",
        ActantRole.SOURCE,
        ((ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")),
        "NO_SOURCE_SLOT",
    ),
)


def _choices_for(role: ActantRole) -> tuple[str, str]:
    if role is ActantRole.RECIPIENT:
        return ("HAS_RECIPIENT_SLOT", "NO_RECIPIENT_SLOT")
    if role is ActantRole.SOURCE:
        return ("HAS_SOURCE_SLOT", "NO_SOURCE_SLOT")
    raise ValueError(f"unsupported hidden-valency diagnostic role: {role.value}")


def _format_known_roles(known_roles: tuple[tuple[ActantRole, str], ...]) -> str:
    lines = [f"{role.value}: {value.strip()}" for role, value in known_roles if value.strip()]
    return "\n".join(lines) if lines else "[none]"


def _hidden_valency_context(
    case: HiddenValencyDiagnosticCase,
    choices: tuple[str, str],
) -> str:
    if case.tested_role is ActantRole.RECIPIENT:
        question = (
            "Beyond the roles already shown, does this verb meaning have a "
            "reusable receiver/addressee/destination slot?"
        )
    elif case.tested_role is ActantRole.SOURCE:
        question = (
            "Beyond the roles already shown, does this verb meaning have a "
            "reusable source/origin slot?"
        )
    else:
        raise ValueError(f"unsupported hidden-valency diagnostic role: {case.tested_role.value}")
    return (
        f"Sentence:\n{case.sentence}\n\n"
        f"Verb:\n{case.verb}\n\n"
        f"Known roles:\n{_format_known_roles(case.known_roles)}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"CHOICES:\n{choices[0]}\n{choices[1]}"
    )


def _semantic_label(raw_text: str, choices: tuple[str, str]) -> tuple[str | None, str]:
    """Recover only the known orphan Qwen closing wrapper for capability analysis.

    Production parser validation remains exact and fail-closed. The diagnostic keeps
    exact protocol compliance separate from semantic choice so a trailing `</think>`
    cannot hide positional-copying behaviour. Any explanation, punctuation or extra
    protocol text still remains malformed.
    """
    text = raw_text.strip()
    if text in choices:
        return text, "EXACT"
    recovered = re.sub(r"(?:\s*</think>\s*)+$", "", text, flags=re.I).strip()
    if recovered in choices and recovered != text:
        return recovered, "RECOVERED_ORPHAN_THINK_CLOSE"
    return None, "MALFORMED"


def _parser_for(services: "RuntimeServices") -> AdaptivePerceptionParser:
    perception = services.perception
    if perception is None or not hasattr(perception, "settings"):
        raise RuntimeError("Adaptive perception service is required for hidden-valency diagnostics")
    settings = perception.settings
    if settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
        raise RuntimeError("Hidden-valency diagnostics require an adaptive perception protocol")
    return AdaptivePerceptionParser(
        services.llm,
        AdaptiveSettings(
            prompt_dir=settings.probe_prompt_dir,
            generation=settings.generation,
            retry_attempts=0,
            max_actants_per_act=settings.max_actants_per_act,
            predicate_symbol_language=settings.predicate_symbol_language,
            morphology_backend=settings.morphology_backend,
            verify_predicate_symbol=(settings.protocol == "adaptive_v3"),
        ),
    )


def _dump_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False, default=str)
        handle.write("\n")


def _run_hidden_valency_diagnostic_impl(services: "RuntimeServices") -> HiddenValencyDiagnosticResult:
    """Run an order-swap capability test directly against the shared local LLM.

    The diagnostic never invokes Orchestrator, Integration or AH mutation methods.
    Each semantic case is sent twice with reversed binary label order. Canonical AH
    is snapshotted before/after as an executable safety assertion.
    """
    if services.llm is None or not services.llm.is_running:
        raise RuntimeError("Local LLM must be running")

    data_dir = Path(services.config.paths.data_dir)
    runs_root = data_dir / RUNS_DIRNAME
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    output_dir = runs_root / timestamp
    suffix = 1
    while output_dir.exists() or output_dir.with_suffix(".zip").exists():
        output_dir = runs_root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)

    parser = _parser_for(services)
    with services.operation_lock:
        before = canonical_ah_snapshot(services)

    case_records: list[dict[str, Any]] = []
    exact_protocol_calls = 0
    wrapper_recovered_calls = 0
    first_choice_calls = 0
    status_counts = {
        "SEMANTIC_OK": 0,
        "ORDER_BIAS": 0,
        "SEMANTIC_WRONG": 0,
        "INCONSISTENT": 0,
        "MALFORMED": 0,
    }

    for index, case in enumerate(_DIAGNOSTIC_CASES, start=1):
        canonical_choices = _choices_for(case.tested_role)
        variants = (
            ("canonical", canonical_choices),
            ("reversed", tuple(reversed(canonical_choices))),
        )
        calls: list[dict[str, Any]] = []
        semantic_labels: list[str | None] = []

        for order_name, choice_order in variants:
            context = _hidden_valency_context(case, choice_order)
            prompt = parser._compose_probe_prompt(
                context,
                parser._instruction("template_hidden_valency"),
            )
            response = services.llm.generate(
                prompt,
                system=parser._probe_system(),
                override=parser._generation_override(8),
                role=_DIAGNOSTIC_ROLE,
            )
            raw = response.text.strip()
            semantic, protocol_mode = _semantic_label(raw, choice_order)
            semantic_labels.append(semantic)
            if protocol_mode == "EXACT":
                exact_protocol_calls += 1
            elif protocol_mode == "RECOVERED_ORPHAN_THINK_CLOSE":
                wrapper_recovered_calls += 1
            if semantic == choice_order[0]:
                first_choice_calls += 1
            calls.append({
                "order": order_name,
                "choices": list(choice_order),
                "prompt": prompt,
                "raw_response": raw,
                "semantic_label": semantic,
                "protocol_mode": protocol_mode,
                "selected_position": (
                    None if semantic is None else (1 if semantic == choice_order[0] else 2)
                ),
            })

        forward, reverse = semantic_labels
        if forward is None or reverse is None:
            status = "MALFORMED"
        elif forward == case.expected_label and reverse == case.expected_label:
            status = "SEMANTIC_OK"
        elif forward == canonical_choices[0] and reverse == canonical_choices[1]:
            # Canonical order starts with HAS; reversed order starts with NO. This
            # exact pattern means the model selected position 1 both times.
            status = "ORDER_BIAS"
        elif forward == reverse:
            status = "SEMANTIC_WRONG"
        else:
            status = "INCONSISTENT"
        status_counts[status] += 1

        record = {
            "index": index,
            "case_id": case.case_id,
            "sentence": case.sentence,
            "verb": case.verb,
            "tested_role": case.tested_role.value,
            "known_roles": [{"role": role.value, "value": value} for role, value in case.known_roles],
            "expected_label": case.expected_label,
            "status": status,
            "order_invariant": forward is not None and forward == reverse,
            "calls": calls,
        }
        case_records.append(record)
        _dump_json(output_dir / f"case_{index:02d}_{case.case_id}.json", record)

    with services.operation_lock:
        after = canonical_ah_snapshot(services)
    ah_diff = diff_canonical_ah(before, after)
    ah_unchanged = not any(ah_diff[key] for key in ("added", "removed", "changed"))
    _dump_json(output_dir / "ah_diff.json", ah_diff)

    total_calls = len(_DIAGNOSTIC_CASES) * 2
    manifest = {
        "output_dir": str(output_dir.resolve()),
        "cases": len(_DIAGNOSTIC_CASES),
        "calls": total_calls,
        "semantic_ok": status_counts["SEMANTIC_OK"],
        "order_bias": status_counts["ORDER_BIAS"],
        "semantic_wrong": status_counts["SEMANTIC_WRONG"],
        "inconsistent": status_counts["INCONSISTENT"],
        "malformed": status_counts["MALFORMED"],
        "exact_protocol_calls": exact_protocol_calls,
        "wrapper_recovered_calls": wrapper_recovered_calls,
        "first_choice_calls": first_choice_calls,
        "ah_unchanged": ah_unchanged,
        "cases_detail": case_records,
    }
    _dump_json(output_dir / "manifest.json", manifest)

    summary_lines = [
        f"Hidden-valency diagnostic: {output_dir.name}",
        f"Cases: {len(_DIAGNOSTIC_CASES)} | Calls: {total_calls}",
        (
            "Case status: "
            f"SEMANTIC_OK={status_counts['SEMANTIC_OK']} | "
            f"ORDER_BIAS={status_counts['ORDER_BIAS']} | "
            f"SEMANTIC_WRONG={status_counts['SEMANTIC_WRONG']} | "
            f"INCONSISTENT={status_counts['INCONSISTENT']} | "
            f"MALFORMED={status_counts['MALFORMED']}"
        ),
        (
            "Protocol: "
            f"EXACT={exact_protocol_calls}/{total_calls} | "
            f"RECOVERED_ORPHAN_THINK_CLOSE={wrapper_recovered_calls}/{total_calls}"
        ),
        f"First-choice selections: {first_choice_calls}/{total_calls}",
        f"AH unchanged: {ah_unchanged}",
        "",
    ]
    for item in case_records:
        call_desc = ", ".join(
            f"{call['order']}={call['semantic_label'] or '<MALFORMED>'} [{call['protocol_mode']}]"
            for call in item["calls"]
        )
        summary_lines.append(
            f"{item['index']:02d} {item['status']}: {item['case_id']} | "
            f"expected={item['expected_label']} | {call_desc}"
        )
    (output_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

    if not ah_unchanged:
        raise RuntimeError(
            f"Hidden-valency diagnostic mutated canonical AH; inspect {output_dir / 'ah_diff.json'}"
        )

    archive_path = Path(shutil.make_archive(str(output_dir), "zip", root_dir=output_dir))
    runs_root.mkdir(parents=True, exist_ok=True)
    (runs_root / "latest.txt").write_text(str(output_dir.resolve()) + "\n", encoding="utf-8", newline="\n")

    return HiddenValencyDiagnosticResult(
        output_dir=output_dir,
        archive_path=archive_path,
        cases=len(_DIAGNOSTIC_CASES),
        calls=total_calls,
        semantic_ok=status_counts["SEMANTIC_OK"],
        order_bias=status_counts["ORDER_BIAS"],
        semantic_wrong=status_counts["SEMANTIC_WRONG"],
        inconsistent=status_counts["INCONSISTENT"],
        malformed=status_counts["MALFORMED"],
        exact_protocol_calls=exact_protocol_calls,
        wrapper_recovered_calls=wrapper_recovered_calls,
        first_choice_calls=first_choice_calls,
        ah_unchanged=ah_unchanged,
    )


def run_hidden_valency_diagnostic(services: "RuntimeServices") -> HiddenValencyDiagnosticResult:
    """Run the preflight without allowing background Ignition to alter the control snapshot."""
    clock = getattr(services, "clock", None)
    resume_clock = bool(clock is not None and getattr(clock, "running", False))
    if resume_clock:
        clock.stop()
    try:
        return _run_hidden_valency_diagnostic_impl(services)
    finally:
        if resume_clock:
            clock.start()
