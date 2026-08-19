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
from ah.model import RuntimeState
from ah.perception import PerceptionResult
from ah.projection import ContextProjector
from ah.integration import TemplateCompletionService
from .errors import CorpusError
from .loader import max_excitation

DIALOGUE_FORMAT = "ah_dialogue_v1"
_SPEAKER_ALIASES = {"user": "user", "agent": "agent", "assistant": "agent", "self": "agent", "пользователь": "user", "агент": "agent"}
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

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"turns_processed": self.turns_processed, "facts_created": self.facts_created, "errors": list(self.errors), "max_excitation": self.max_excitation, "ok": self.ok}


def split_raw_experience_text(text: str) -> list[str]:
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not source:
        return []
    chunks: list[str] = []
    for block in _BLANK_BLOCK.split(source):
        lines = [line.rstrip() for line in block.split("\n") if line.strip() and not line.strip().startswith("#")]
        paragraph = "\n".join(lines).strip()
        if paragraph:
            chunks.append(paragraph)
    return chunks


def _normalize_speaker(raw: Any, index: int) -> str:
    speaker = _SPEAKER_ALIASES.get(str(raw or "").strip().casefold())
    if speaker is None:
        raise CorpusError(f"Turn {index} has unknown speaker {raw!r}; use user or agent")
    return speaker


def parse_dialogue_json(payload: Mapping[str, Any] | list[Any]) -> list[DialogueTurn]:
    if not isinstance(payload, Mapping):
        raise CorpusError("Dialogue JSON must be an object")
    if str(payload.get("format") or "").strip() != DIALOGUE_FORMAT:
        raise CorpusError(f"Unsupported dialogue format; expected {DIALOGUE_FORMAT!r}")
    raw_turns = payload.get("turns")
    if not isinstance(raw_turns, list):
        raise CorpusError("Dialogue JSON needs a turns array")
    turns: list[DialogueTurn] = []
    for index, item in enumerate(raw_turns, start=1):
        if not isinstance(item, Mapping):
            raise CorpusError(f"Turn {index} must be an object")
        text = str(item.get("text") or "").strip()
        if not text:
            raise CorpusError(f"Turn {index} has empty text")
        turns.append(DialogueTurn(_normalize_speaker(item.get("speaker"), index), text, index))
    return turns


def load_dialogue_file(path: str | Path) -> list[DialogueTurn]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"Invalid dialogue JSON in {source}: {exc}") from exc
    return parse_dialogue_json(payload)


def dump_dialogue_payload(turns: Iterable[DialogueTurn | Mapping[str, Any]], *, exported_at: str | None = None) -> dict[str, Any]:
    serialized: list[dict[str, str]] = []
    for index, item in enumerate(turns, start=1):
        if isinstance(item, DialogueTurn):
            speaker, text = item.speaker, item.text
        else:
            speaker, text = _normalize_speaker(item.get("speaker"), index), str(item.get("text") or "").strip()
        if text:
            serialized.append({"speaker": speaker, "text": text})
    return {"format": DIALOGUE_FORMAT, "exported_at": exported_at or datetime.now().astimezone().isoformat(timespec="seconds"), "turns": serialized}


def _facts_from_commit(commit) -> int:
    return sum(1 for assertion in getattr(commit, "assertions", ()) if getattr(assertion, "created", False))


def _complete_templates(services, perception: PerceptionResult) -> PerceptionResult:
    """Reuse the live orchestrator's exact template/sense completion path.

    This is intentionally centralized through the same code path as live turns so
    corpus construction cannot silently use a different formalization policy.
    """
    if getattr(services, "perception", None) is None:
        return perception
    with services.operation_lock:
        return TemplateCompletionService(services.integration, services.perception).complete(perception)


def _import_user_turn(services, text: str, *, parse_user: bool):
    if not parse_user:
        return services.integration.integrate_external(PerceptionResult(source_text=text), services.context)
    parsed = services.perception.parse(text, services.context)
    parsed = _complete_templates(services, parsed)
    return services.integration.integrate_external(parsed, services.context)


def _import_agent_turn(services, text: str, *, parse_semantics: bool):
    if parse_semantics and services.perception is not None:
        parsed = services.perception.parse(text, services.context)
        parsed = _complete_templates(services, parsed)
        return services.integration.integrate_to_h(parsed, services.context)
    return services.integration.integrate_to_h(PerceptionResult(source_text=text, diagnostics=("AGENT_H_TEXT_ONLY",)), services.context)


def import_raw_experience(services, chunks: Iterable[str], *, parse_user_semantics: bool = True, strict: bool = True) -> MemoryImportResult:
    result = MemoryImportResult()
    parse_user = bool(parse_user_semantics) and getattr(services, "perception", None) is not None
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk).strip()
        if not text:
            continue
        try:
            commit = _import_user_turn(services, text, parse_user=parse_user)
        except Exception as exc:
            message = f"text[{index}]: {type(exc).__name__}: {exc}"
            result.errors.append(message)
            if strict:
                raise CorpusError(message) from exc
            commit = services.integration.integrate_external(PerceptionResult(source_text=text), services.context)
        result.turns_processed += 1
        result.facts_created += _facts_from_commit(commit)
    result.max_excitation = max_excitation(services.core)
    return result


def import_dialogue_cold(services, turns: Iterable[DialogueTurn], *, parse_user_semantics: bool = True, strict: bool = True) -> MemoryImportResult:
    result = MemoryImportResult()
    parse_agent = bool(getattr(services.config.orchestrator, "parse_agent_response_to_h", False))
    parse_user = bool(parse_user_semantics) and getattr(services, "perception", None) is not None
    for turn in turns:
        try:
            commit = _import_user_turn(services, turn.text, parse_user=parse_user) if turn.speaker == "user" else _import_agent_turn(services, turn.text, parse_semantics=parse_agent)
        except Exception as exc:
            message = f"{turn.speaker}[{turn.index or '?'}]: {type(exc).__name__}: {exc}"
            result.errors.append(message)
            if strict:
                raise CorpusError(message) from exc
            commit = services.integration.integrate_external(PerceptionResult(source_text=turn.text), services.context) if turn.speaker == "user" else services.integration.integrate_to_h(PerceptionResult(source_text=turn.text, diagnostics=("AGENT_H_TEXT_ONLY",)), services.context)
        result.turns_processed += 1
        result.facts_created += _facts_from_commit(commit)
    result.max_excitation = max_excitation(services.core)
    return result


def import_memory_snapshot(services, path: str | Path, *, cold_restore: bool = True) -> MemoryImportResult:
    source = Path(path)
    if not source.is_file():
        raise CorpusError(f"Memory snapshot not found: {source}")
    loader = JsonPersistence(source, PersistenceSettings(enabled=True, load_on_start=True, autosave_every_ticks=services.config.persistence.autosave_every_ticks, save_runtime_state=not cold_restore, save_pending_impulses=not cold_restore))
    bundle = loader.load(uid_generator=services.core.uid)
    services.core.store.replace_from(bundle.core.store)
    if cold_restore:
        services.core.store._replace_runtime_states({uid: RuntimeState() for uid, _ in services.core.store.runtime_items()})
    if bundle.interaction_context is not None:
        for item in fields(bundle.interaction_context):
            setattr(services.context, item.name, deepcopy(getattr(bundle.interaction_context, item.name)))
    services.ignition.restore_snapshot(IgnitionSnapshot(0, {}, {}) if cold_restore or bundle.ignition_snapshot is None else bundle.ignition_snapshot)
    type(services)._ensure_identity_context(services.core, services.context, services.config)
    services.projector = ContextProjector(services.core, services.config.context)
    return MemoryImportResult(turns_processed=1, max_excitation=max_excitation(services.core))
