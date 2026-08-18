from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
import json
import re

from ah.config import PersistenceSettings
from ah.core import JsonPersistence
from ah.ignition.engine import IgnitionSnapshot
from ah.integration.errors import IntegrationError
from ah.model import RuntimeState
from ah.perception import PerceptionResult
from ah.perception.llm_parser import PerceptionClarificationRequired, PerceptionParseError
from ah.projection import ContextProjector

from .errors import CorpusError
from .loader import max_excitation


DIALOGUE_FORMAT = "ah_dialogue_v1"

_SPEAKER_ALIASES = {
    "user": "user",
    "agent": "agent",
    "assistant": "agent",
    "self": "agent",
    "пользователь": "user",
    "агент": "agent",
}

_BLANK_BLOCK = re.compile(r"\n\s*\n")


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    speaker: str
    text: str
    index: int = 0


@dataclass
class MemoryImportResult:
    turns_processed: int = 0
    facts_created: int = 0
    errors: list[str] = field(default_factory=list)
    max_excitation: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "turns_processed": self.turns_processed,
            "facts_created": self.facts_created,
            "errors": list(self.errors),
            "max_excitation": self.max_excitation,
        }


def split_raw_experience_text(text: str) -> list[str]:
    """Split unformatted prose into H-experience chunks.

    Blank lines start a new chunk. Empty blocks and ``#`` comments are skipped,
    matching the acceptance-file convention.
    """
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        return []
    chunks: list[str] = []
    for block in _BLANK_BLOCK.split(source):
        kept: list[str] = []
        for line in block.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            kept.append(line.rstrip())
        paragraph = "\n".join(kept).strip()
        if paragraph:
            chunks.append(paragraph)
    return chunks


def parse_dialogue_json(payload: Mapping[str, Any] | list[Any]) -> list[DialogueTurn]:
    if isinstance(payload, list):
        raise CorpusError(
            f"Dialogue JSON must be an object with format={DIALOGUE_FORMAT!r} and a turns array"
        )
    if not isinstance(payload, Mapping):
        raise CorpusError("Dialogue JSON must be an object")
    fmt = str(payload.get("format") or "").strip()
    if fmt != DIALOGUE_FORMAT:
        raise CorpusError(f"Unsupported dialogue format {fmt!r}; expected {DIALOGUE_FORMAT!r}")
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        raise CorpusError("Dialogue JSON needs a turns array")
    turns: list[DialogueTurn] = []
    for index, item in enumerate(raw_turns, start=1):
        if not isinstance(item, Mapping):
            raise CorpusError(f"Turn {index} must be an object with speaker and text")
        speaker = _normalize_speaker(item.get("speaker"), index)
        text = str(item.get("text") or "").strip()
        if not text:
            raise CorpusError(f"Turn {index} has empty text")
        turns.append(DialogueTurn(speaker=speaker, text=text, index=index))
    return turns


def load_dialogue_file(path: str | Path) -> list[DialogueTurn]:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise CorpusError(f"Dialogue file not found: {source}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"Invalid dialogue JSON in {source}: {exc}") from exc
    return parse_dialogue_json(raw)


def dump_dialogue_payload(
    turns: Iterable[DialogueTurn | Mapping[str, Any]],
    *,
    exported_at: str | None = None,
) -> dict[str, Any]:
    serialized: list[dict[str, str]] = []
    for index, item in enumerate(turns, start=1):
        if isinstance(item, DialogueTurn):
            speaker = item.speaker
            text = item.text
        else:
            speaker = _normalize_speaker(item.get("speaker"), index)
            text = str(item.get("text") or "").strip()
        if not text:
            continue
        serialized.append({"speaker": speaker, "text": text})
    stamp = exported_at or datetime.now().astimezone().isoformat(timespec="seconds")
    return {"format": DIALOGUE_FORMAT, "exported_at": stamp, "turns": serialized}


def _normalize_speaker(raw: Any, index: int) -> str:
    key = str(raw or "").strip().casefold()
    speaker = _SPEAKER_ALIASES.get(key)
    if speaker is None:
        raise CorpusError(
            f"Turn {index} has unknown speaker {raw!r}; use user or agent"
        )
    return speaker


def _restore_interaction_context(target, source) -> None:
    for item in fields(source):
        setattr(target, item.name, deepcopy(getattr(source, item.name)))


def _facts_from_commit(commit) -> int:
    return sum(1 for assertion in getattr(commit, "assertions", ()) if getattr(assertion, "created", False))


def _complete_perception_templates(services, perception: PerceptionResult) -> PerceptionResult:
    if getattr(services, "perception", None) is None:
        return perception
    if getattr(services, "agent", None) is not None:
        orchestrator = services.create_orchestrator()
        return orchestrator._complete_dynamic_templates(perception, services.operation_lock)
    proposer = getattr(services.perception, "propose_template_candidate", None)
    if proposer is None:
        return perception
    from ah.perception import TemplateCandidate, TemplateSelection

    requests = services.integration.template_requests(perception)
    if not requests:
        return perception
    candidate_mapping: dict = {}
    selection_mapping: dict = {}
    for request in requests:
        predicate = request.predicate
        if request.sense_options:
            continue
        if predicate.template_candidate is not None:
            continue
        candidate = proposer(
            request.source_context,
            predicate,
            request.filled_roles,
            request.role_bindings,
        )
        if isinstance(candidate, TemplateCandidate):
            candidate_mapping[predicate] = candidate
            selection_mapping[predicate] = TemplateSelection(create_new=True)
    if not candidate_mapping and not selection_mapping:
        return perception
    from ah.agent.orchestrator import AgentOrchestrator

    return AgentOrchestrator._apply_template_resolutions(
        perception, candidate_mapping, selection_mapping
    )


def import_raw_experience(
    services,
    chunks: Iterable[str],
    *,
    parse_user_semantics: bool = True,
) -> MemoryImportResult:
    """Write each chunk as a USER turn without lighting Ignition.

    With Perception available and ``parse_user_semantics`` the chunk is parsed into
    C/P facts plus an H experience. Otherwise only the H experience is recorded.
    """
    result = MemoryImportResult()
    parse_user = bool(parse_user_semantics) and getattr(services, "perception", None) is not None
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk).strip()
        if not text:
            continue
        label = f"text[{index}]"
        try:
            commit = _import_user_turn(services, text, parse_user=parse_user)
        except (IntegrationError, PerceptionParseError, PerceptionClarificationRequired, ValueError, RuntimeError) as exc:
            result.errors.append(f"{label}: {exc}")
            try:
                commit = services.integration.integrate_external(
                    PerceptionResult(source_text=text), services.context
                )
            except Exception as fallback_exc:
                result.errors.append(f"{label} fallback: {fallback_exc}")
                continue
        result.turns_processed += 1
        result.facts_created += _facts_from_commit(commit)
    result.max_excitation = max_excitation(services.core)
    return result


def import_dialogue_cold(
    services,
    turns: Iterable[DialogueTurn],
    *,
    parse_user_semantics: bool = True,
) -> MemoryImportResult:
    """Commit dialogue turns through Integration without lighting Ignition."""
    result = MemoryImportResult()
    parse_agent = bool(getattr(services.config.orchestrator, "parse_agent_response_to_h", False))
    perception = getattr(services, "perception", None)
    parse_user = bool(parse_user_semantics) and perception is not None

    for turn in turns:
        label = f"{turn.speaker}[{turn.index or '?'}]"
        try:
            if turn.speaker == "user":
                commit = _import_user_turn(services, turn.text, parse_user=parse_user)
            else:
                commit = _import_agent_turn(services, turn.text, parse_semantics=parse_agent)
        except (IntegrationError, PerceptionParseError, PerceptionClarificationRequired, ValueError, RuntimeError) as exc:
            result.errors.append(f"{label}: {exc}")
            try:
                fallback = services.integration.integrate_external(
                    PerceptionResult(source_text=turn.text), services.context
                ) if turn.speaker == "user" else services.integration.integrate_to_h(
                    PerceptionResult(
                        source_text=turn.text,
                        diagnostics=("AGENT_H_TEXT_ONLY",),
                    ),
                    services.context,
                )
            except Exception as fallback_exc:
                result.errors.append(f"{label} fallback: {fallback_exc}")
                continue
            result.turns_processed += 1
            result.facts_created += _facts_from_commit(fallback)
            continue
        result.turns_processed += 1
        result.facts_created += _facts_from_commit(commit)

    result.max_excitation = max_excitation(services.core)
    return result


def _import_user_turn(services, text: str, *, parse_user: bool):
    if not parse_user:
        return services.integration.integrate_external(
            PerceptionResult(source_text=text), services.context
        )
    parsed = services.perception.parse(text, services.context)
    parsed = _complete_perception_templates(services, parsed)
    return services.integration.integrate_external(parsed, services.context)


def _import_agent_turn(services, text: str, *, parse_semantics: bool):
    if parse_semantics and services.perception is not None:
        parsed = services.perception.parse(text, services.context)
        parsed = _complete_perception_templates(services, parsed)
        return services.integration.integrate_to_h(parsed, services.context)
    return services.integration.integrate_to_h(
        PerceptionResult(source_text=text, diagnostics=("AGENT_H_TEXT_ONLY",)),
        services.context,
    )


def import_memory_snapshot(services, path: str | Path, *, cold_restore: bool = True) -> MemoryImportResult:
    """Replace live AH with a persistence snapshot. Optional cold runtime restore."""
    source = Path(path)
    if not source.is_file():
        raise CorpusError(f"Memory snapshot not found: {source}")
    loader = JsonPersistence(
        source,
        PersistenceSettings(
            enabled=True,
            load_on_start=True,
            autosave_every_ticks=services.config.persistence.autosave_every_ticks,
            save_runtime_state=not cold_restore,
            save_pending_impulses=not cold_restore,
        ),
    )
    bundle = loader.load(uid_generator=services.core.uid)
    services.core.store.replace_from(bundle.core.store)
    if cold_restore:
        services.core.store._replace_runtime_states(
            {uid: RuntimeState() for uid, _state in services.core.store.runtime_items()}
        )
    if bundle.interaction_context is not None:
        _restore_interaction_context(services.context, bundle.interaction_context)
    if cold_restore or bundle.ignition_snapshot is None:
        services.ignition.restore_snapshot(IgnitionSnapshot(0, {}, {}))
    else:
        services.ignition.restore_snapshot(bundle.ignition_snapshot)
    ensure_identity = getattr(type(services), "_ensure_identity_context", None)
    if callable(ensure_identity):
        ensure_identity(services.core, services.context, services.config)
    services.projector = ContextProjector(services.core, services.config.context)
    return MemoryImportResult(
        turns_processed=1,
        max_excitation=max_excitation(services.core),
    )
