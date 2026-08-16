from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
import json
import re

from ah.agent.interaction_context import InteractionContext
from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptivePerceptionParser,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)

from .contracts import (
    ActantCandidate,
    AssertionCandidate,
    CommandCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    StructuralClarificationSpec,
    TemplateCandidate,
    QueryCandidate,
    QueryMode,
)


class TextGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse: ...


@dataclass(frozen=True, slots=True)
class LLMPerceptionSettings:
    system_prompt_path: Path | None = None  # legacy single-call protocols
    generation: LLMRoleSettings = LLMRoleSettings(
        max_new_tokens=24,
        temperature=0.0,
        top_p=1.0,
        top_k=0,
        repetition_penalty=1.0,
        no_repeat_ngram_size=0,
    )
    protocol: str = "adaptive_v3"
    probe_prompt_dir: Path | None = None
    probe_retry_attempts: int = 1
    repair_attempts: int | None = None  # deprecated alias -> probe_retry_attempts
    ground_actants: bool = True
    max_acts: int = 4
    max_actants_per_act: int = 8
    predicate_symbol_language: str = "en"
    morphology_backend: str = "auto"

    def __post_init__(self) -> None:
        if self.repair_attempts is not None:
            object.__setattr__(self, "probe_retry_attempts", self.repair_attempts)
        if self.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3", "span_v1", "line_v1", "compact_json_v1", "legacy_json"}:
            raise ValueError("Unsupported perception protocol")
        if self.probe_retry_attempts < 0 or self.probe_retry_attempts > 2:
            raise ValueError("probe_retry_attempts must be in [0, 2]")
        if self.max_acts <= 0 or self.max_actants_per_act <= 0:
            raise ValueError("adaptive parser budgets must be > 0")
        if self.predicate_symbol_language != "en":
            raise ValueError("predicate_symbol_language currently must be 'en'")
        if self.morphology_backend not in {"auto", "pymorphy3", "none"}:
            raise ValueError("morphology_backend must be auto, pymorphy3, or none")


class PerceptionParseError(ValueError):
    pass


class PerceptionClarificationRequired(PerceptionParseError):
    def __init__(self, spec: StructuralClarificationSpec) -> None:
        super().__init__(f"structural clarification required: {spec.mention}")
        self.spec = spec


@dataclass(frozen=True, slots=True)
class PerceptionAttemptDiagnostic:
    role: str
    raw_text: str
    error: str | None = None
    prompt: str = ""
    normalized_answer: str | None = None
    retry_index: int = 0


@dataclass(frozen=True, slots=True)
class PerceptionDiagnostic:
    sequence: int
    source_text: str
    attempts: tuple[PerceptionAttemptDiagnostic, ...]
    decoded: PerceptionResult | None
    final_error: str | None = None


class LLMPerceptionService:
    """LLM text -> runtime-only PerceptionResult.

    Default `adaptive_v3` never asks the model to serialize a compound payload.
    The shared LLM answers a sequence of tiny stateless probes (enum / bit / source
    span choices); Python owns parser state, lexical predicate identity and construction of
    the rich runtime contracts. Legacy single-call protocols remain readable for
    compatibility and tests.

    Canonical UID selection, entity resolution, T registration, domain routing and
    all AH writes remain deterministic and outside the model boundary.
    """

    def __init__(self, backend: TextGenerator, settings: LLMPerceptionSettings) -> None:
        self.backend = backend
        self.settings = settings
        self._diagnostic_lock = Lock()
        self._diagnostic_sequence = 0
        self._diagnostics: deque[PerceptionDiagnostic] = deque(maxlen=30)

    def diagnostics(self) -> tuple[PerceptionDiagnostic, ...]:
        """Runtime-only parser diagnostics for the GUI. Never enters AH/H."""
        with self._diagnostic_lock:
            return tuple(self._diagnostics)

    def _record_diagnostic(
        self,
        source_text: str,
        attempts: list[PerceptionAttemptDiagnostic],
        decoded: PerceptionResult | None,
        final_error: str | None = None,
    ) -> None:
        with self._diagnostic_lock:
            self._diagnostic_sequence += 1
            self._diagnostics.append(
                PerceptionDiagnostic(
                    sequence=self._diagnostic_sequence,
                    source_text=source_text,
                    attempts=tuple(attempts),
                    decoded=decoded,
                    final_error=final_error,
                )
            )

    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult:
        if self.settings.protocol in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return self._parse_adaptive(text)
        return self._parse_legacy_protocol(text, interaction_context)

    def parse_with_structural_resolution(
        self,
        text: str,
        interaction_context: InteractionContext,
        resolution_key: str,
    ) -> PerceptionResult:
        del interaction_context
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            raise PerceptionParseError("Structural clarification requires an adaptive perception protocol")
        return self._parse_adaptive(text, structural_resolution=resolution_key)

    def propose_template_candidate(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        filled_roles: tuple[ActantRole, ...],
        role_bindings: tuple[tuple[ActantRole, str], ...] = (),
    ) -> TemplateCandidate:
        """Return the explicit runtime schema for an unknown predicate.

        v0.12.39 deliberately performs no extra LLM call here. The semantic parser
        has already produced the assertion/query/command roles; this boundary only
        packages those validated runtime roles as a noncanonical TemplateCandidate.
        Deterministic Integration owns canonical registration and later monotonic T
        expansion. ``source_text``/``role_bindings`` remain in the interface for
        provenance and compatibility with the orchestrator contract.
        """
        del source_text, predicate, role_bindings
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            raise PerceptionParseError(
                "Dynamic TemplateCandidate proposal requires an adaptive perception protocol"
            )
        explicit = set(filled_roles)
        return TemplateCandidate(tuple(role for role in ActantRole if role in explicit))

    def interpret_clarification_answer(
        self,
        answer_text: str,
        option_labels: tuple[str, ...],
    ) -> int | None:
        """Perception-only interpretation of the user's explicit clarification reply."""
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return None
        parser = AdaptivePerceptionParser(
            self.backend,
            AdaptiveSettings(
                prompt_dir=self.settings.probe_prompt_dir,
                generation=self.settings.generation,
                retry_attempts=self.settings.probe_retry_attempts,
                max_acts=self.settings.max_acts,
                max_actants_per_act=self.settings.max_actants_per_act,
                predicate_symbol_language=self.settings.predicate_symbol_language,
                morphology_backend=self.settings.morphology_backend,
                verify_predicate_symbol=(self.settings.protocol == "adaptive_v3"),
            ),
        )
        try:
            parsed = parser.interpret_clarification_answer(answer_text, option_labels)
        except AdaptiveParseError as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            self._record_diagnostic(answer_text, attempts, None, str(exc))
            return None
        return parsed.option_index

    def _parse_adaptive(
        self, text: str, *, structural_resolution: str | None = None
    ) -> PerceptionResult:
        parser = AdaptivePerceptionParser(
            self.backend,
            AdaptiveSettings(
                prompt_dir=self.settings.probe_prompt_dir,
                generation=self.settings.generation,
                retry_attempts=self.settings.probe_retry_attempts,
                max_acts=self.settings.max_acts,
                max_actants_per_act=self.settings.max_actants_per_act,
                predicate_symbol_language=self.settings.predicate_symbol_language,
                morphology_backend=self.settings.morphology_backend,
                verify_predicate_symbol=(self.settings.protocol == "adaptive_v3"),
            ),
        )
        try:
            parsed = parser.parse(text, structural_resolution=structural_resolution)
        except AdaptiveStructuralClarificationRequired as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            self._record_diagnostic(text, attempts, None, str(exc))
            raise PerceptionClarificationRequired(exc.spec) from exc
        except AdaptiveParseError as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            final_error = str(exc)
            self._record_diagnostic(text, attempts, None, final_error)
            raise PerceptionParseError(final_error) from exc

        attempts = [
            PerceptionAttemptDiagnostic(
                role=trace.stage,
                raw_text=trace.raw_text,
                error=trace.error,
                prompt=trace.prompt,
                normalized_answer=trace.normalized_answer,
                retry_index=trace.retry_index,
            )
            for trace in parsed.traces
        ]
        self._record_diagnostic(text, attempts, parsed.perception)
        return parsed.perception

    def _parse_legacy_protocol(
        self, text: str, interaction_context: InteractionContext
    ) -> PerceptionResult:
        generation = self.settings.generation
        response = self.backend.generate(
            self._user_prompt(text, interaction_context),
            system=self._system_prompt(),
            override=self._generation_override(generation),
            role="perception",
        )

        raw = response.text
        errors: list[str] = []
        attempts: list[PerceptionAttemptDiagnostic] = []
        try:
            decoded = self.parse_response(text, raw)
        except PerceptionParseError as exc:
            error = str(exc)
            errors.append(error)
            attempts.append(PerceptionAttemptDiagnostic("perception", raw, error))
        else:
            attempts.append(PerceptionAttemptDiagnostic("perception", raw))
            self._record_diagnostic(text, attempts, decoded)
            return decoded

        for _ in range(self.settings.probe_retry_attempts):
            # Legacy compatibility only. adaptive_v1 never feeds a bad answer back.
            repaired = self.backend.generate(
                self._repair_prompt(text, raw),
                system=self._repair_system_prompt(),
                override=self._generation_override(generation),
                role="perception_repair",
            )
            raw = repaired.text
            try:
                decoded = self.parse_response(text, raw)
            except PerceptionParseError as exc:
                error = str(exc)
                errors.append(error)
                attempts.append(PerceptionAttemptDiagnostic("perception_repair", raw, error))
                continue
            attempts.append(PerceptionAttemptDiagnostic("perception_repair", raw))
            self._record_diagnostic(text, attempts, decoded)
            return decoded

        final_error = "Perception output remained invalid after repair: " + " | ".join(errors)
        self._record_diagnostic(text, attempts, None, final_error)
        raise PerceptionParseError(final_error)

    @staticmethod
    def _generation_override(generation: LLMRoleSettings) -> dict[str, Any]:
        return {
            "max_new_tokens": generation.max_new_tokens,
            "temperature": generation.temperature,
            "top_p": generation.top_p,
            "top_k": generation.top_k,
            "repetition_penalty": generation.repetition_penalty,
            "no_repeat_ngram_size": generation.no_repeat_ngram_size,
        }

    def parse_response(self, source_text: str, raw_text: str) -> PerceptionResult:
        try:
            using_span_protocol = self.settings.protocol == "span_v1" and not raw_text.lstrip().startswith("{")
            using_line_protocol = self.settings.protocol == "line_v1" and not raw_text.lstrip().startswith("{")
            if using_span_protocol:
                result = self._span_result(source_text, raw_text)
            elif using_line_protocol:
                result = self._line_result(source_text, raw_text)
            else:
                # Backward-compatible diagnostic/test path: line_v1 prefers the
                # mechanically simpler record protocol, but if the model still emits
                # a complete JSON object we can deterministically decode it rather than
                # wasting a repair call.
                payload = self._extract_json(raw_text)
                if self._looks_compact(payload):
                    result = self._compact_result(source_text, payload)
                else:
                    result = self._legacy_result(source_text, payload)
            if self.settings.ground_actants:
                self._validate_grounding(source_text, result, strict_predicate=(using_line_protocol or using_span_protocol))
            return result
        except PerceptionParseError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise PerceptionParseError(f"Invalid perception payload: {exc}") from exc

    @staticmethod
    def _unquote(value: str) -> str:
        text = value.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
            text = text[1:-1]
        return text.replace(r"\n", "\n").replace(r"\t", "\t")

    @classmethod
    def _line_actants(cls, fields: list[str]) -> tuple[ActantCandidate, ...]:
        result: list[ActantCandidate] = []
        for field in fields:
            field = field.strip()
            if not field:
                continue
            if "=" not in field:
                raise PerceptionParseError(f"line actant must be ROLE=value: {field!r}")
            role_text, value_text = field.split("=", 1)
            try:
                role = ActantRole(role_text.strip().upper())
            except ValueError as exc:
                raise PerceptionParseError(f"unknown actant role: {role_text!r}") from exc
            value = cls._unquote(value_text)
            if not value:
                raise PerceptionParseError("line actant value cannot be empty")
            if value.startswith("@") and len(value) > 1:
                result.append(ActantCandidate(role=role, candidate_ref=value[1:]))
            else:
                result.append(ActantCandidate(role=role, mention=value))
        return tuple(result)

    @staticmethod
    def _line_predicate(surface: str, normalized: str) -> PredicateCandidate:
        surface = surface.strip()
        normalized = normalized.strip()
        implicit = surface == "_"
        if implicit:
            surface = normalized
        if normalized in {"", "-", "_"}:
            normalized = surface
        if not surface:
            raise PerceptionParseError("line predicate surface is required")
        if not normalized:
            raise PerceptionParseError("line predicate lemma is required")
        return PredicateCandidate(
            surface=surface,
            normalized_hint=normalized,
            sense_hint=("IMPLICIT" if implicit else None),
        )

    @dataclass(frozen=True, slots=True)
    class _SourceToken:
        index: int
        text: str
        start: int
        end: int

    @classmethod
    def _source_tokens(cls, source_text: str) -> tuple["LLMPerceptionService._SourceToken", ...]:
        # Unicode-aware words plus standalone punctuation. Offsets let the adapter
        # recover the exact original span, including internal whitespace.
        return tuple(
            cls._SourceToken(i, match.group(0), match.start(), match.end())
            for i, match in enumerate(re.finditer(r"\w+|[^\w\s]", source_text, flags=re.UNICODE), start=1)
        )

    @classmethod
    def _resolve_span(
        cls,
        source_text: str,
        tokens: tuple["LLMPerceptionService._SourceToken", ...],
        spec: str,
    ) -> tuple[str, EvidenceSpan]:
        raw = spec.strip()
        aliases = {"$SELF": "я", "$USER": "ты", "$WE": "мы"}
        if raw.upper() in aliases:
            text = aliases[raw.upper()]
            return text, EvidenceSpan(text=text)
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", raw)
        if match is None:
            raise PerceptionParseError(f"span must be token index/range, got {spec!r}")
        start_i = int(match.group(1))
        end_i = int(match.group(2) or start_i)
        if start_i < 1 or end_i < start_i or end_i > len(tokens):
            raise PerceptionParseError(
                f"span {spec!r} is outside token range 1..{len(tokens)}"
            )
        first = tokens[start_i - 1]
        last = tokens[end_i - 1]
        text = source_text[first.start:last.end]
        return text, EvidenceSpan(text=text, start=first.start, end=last.end)

    @classmethod
    def _span_predicate(
        cls,
        source_text: str,
        tokens: tuple["LLMPerceptionService._SourceToken", ...],
        index_text: str,
        lemma: str,
    ) -> PredicateCandidate:
        lemma = cls._unquote(lemma).strip()
        if not lemma or lemma in {"-", "_"}:
            raise PerceptionParseError("span predicate lemma is required")
        try:
            index = int(index_text)
        except ValueError as exc:
            raise PerceptionParseError(f"predicate token must be an integer, got {index_text!r}") from exc
        if index == 0:
            return PredicateCandidate(surface=lemma, normalized_hint=lemma, sense_hint="IMPLICIT")
        if index < 1 or index > len(tokens):
            raise PerceptionParseError(
                f"predicate token {index} is outside token range 1..{len(tokens)}"
            )
        tok = tokens[index - 1]
        return PredicateCandidate(
            surface=tok.text,
            normalized_hint=lemma,
            evidence=EvidenceSpan(tok.text, tok.start, tok.end),
        )

    @classmethod
    def _span_actants(
        cls,
        source_text: str,
        tokens: tuple["LLMPerceptionService._SourceToken", ...],
        fields: list[str],
    ) -> tuple[ActantCandidate, ...]:
        result: list[ActantCandidate] = []
        seen: set[ActantRole] = set()
        for field in fields:
            field = field.strip()
            if not field:
                continue
            if "=" not in field:
                raise PerceptionParseError(f"span actant must be ROLE=span: {field!r}")
            role_text, value_text = field.split("=", 1)
            try:
                role = ActantRole(role_text.strip().upper())
            except ValueError as exc:
                raise PerceptionParseError(f"unknown actant role: {role_text!r}") from exc
            if role in seen:
                raise PerceptionParseError(f"duplicate actant role: {role.value}")
            seen.add(role)
            value = value_text.strip()
            if value.startswith("@") and len(value) > 1:
                result.append(ActantCandidate(role=role, candidate_ref=value[1:]))
                continue
            text, evidence = cls._resolve_span(source_text, tokens, value)
            result.append(ActantCandidate(role=role, mention=text, evidence=evidence))
        return tuple(result)

    def _span_result(self, source_text: str, raw_text: str) -> PerceptionResult:
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
        else:
            lines = stripped.splitlines()
        lines = [line.strip() for line in lines if line.strip()]
        if not lines:
            raise PerceptionParseError("LLM response is empty")
        if len(lines) == 1 and lines[0].upper() == "NONE":
            return PerceptionResult(source_text, (), (), (), ())

        tokens = self._source_tokens(source_text)
        if not tokens:
            raise PerceptionParseError("source contains no parseable tokens")
        assertions: list[AssertionCandidate] = []
        queries: list[QueryCandidate] = []
        commands: list[CommandCandidate] = []
        for line in lines:
            parts = [part.strip() for part in line.split("|")]
            kind = parts[0].upper() if parts else ""
            if kind == "A":
                if len(parts) < 5:
                    raise PerceptionParseError("A span record has too few fields")
                local_id = parts[1]
                if not re.fullmatch(r"A\d+", local_id, flags=re.IGNORECASE):
                    raise PerceptionParseError(f"assertion id must be A<number>, got {local_id!r}")
                predicate = self._span_predicate(source_text, tokens, parts[2], parts[3])
                neg = self._compact_bool(parts[4])
                assertions.append(AssertionCandidate(
                    local_id=local_id,
                    predicate=predicate,
                    actants=self._span_actants(source_text, tokens, parts[5:]),
                    negated=neg,
                ))
            elif kind == "Q":
                if len(parts) < 5:
                    raise PerceptionParseError("Q span record has too few fields")
                try:
                    mode = QueryMode(parts[1].upper())
                except ValueError as exc:
                    raise PerceptionParseError(f"unknown query mode: {parts[1]!r}") from exc
                predicate = self._span_predicate(source_text, tokens, parts[2], parts[3])
                requested = None if parts[4] in {"", "-", "_"} else ActantRole(parts[4].upper())
                if mode is QueryMode.FILL_ROLE and requested is None:
                    raise PerceptionParseError("FILL_ROLE requires requested role")
                queries.append(QueryCandidate(
                    predicate=predicate,
                    actants=self._span_actants(source_text, tokens, parts[5:]),
                    requested_role=requested,
                    query_mode=mode,
                ))
            elif kind == "C":
                if len(parts) < 3:
                    raise PerceptionParseError("C span record has too few fields")
                commands.append(CommandCandidate(
                    predicate=self._span_predicate(source_text, tokens, parts[1], parts[2]),
                    actants=self._span_actants(source_text, tokens, parts[3:]),
                ))
            else:
                raise PerceptionParseError(f"unexpected span protocol record: {line!r}")
        return PerceptionResult(source_text, tuple(assertions), tuple(queries), tuple(commands), ())

    def _line_result(self, source_text: str, raw_text: str) -> PerceptionResult:
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
        else:
            lines = stripped.splitlines()

        lines = [line.strip() for line in lines if line.strip()]
        if not lines:
            raise PerceptionParseError("LLM response is empty")
        if len(lines) == 1 and lines[0].upper() == "NONE":
            return PerceptionResult(source_text, (), (), (), ())

        assertions: list[AssertionCandidate] = []
        queries: list[QueryCandidate] = []
        commands: list[CommandCandidate] = []
        for line in lines:
            # A line protocol is intentionally strict at the framing level: prose or
            # prompt echo must not be silently interpreted as semantic memory.
            parts = [part.strip() for part in line.split("|")]
            kind = parts[0].upper() if parts else ""
            if kind == "A":
                if len(parts) < 5:
                    raise PerceptionParseError("A line requires A|ID|surface|lemma|0/1|ROLE=value...")
                local_id = parts[1]
                if not local_id:
                    raise PerceptionParseError("A line requires a local ID")
                predicate = self._line_predicate(parts[2], parts[3])
                neg = self._compact_bool(parts[4])
                assertions.append(AssertionCandidate(
                    local_id=local_id,
                    predicate=predicate,
                    actants=self._line_actants(parts[5:]),
                    negated=neg,
                ))
            elif kind == "Q":
                if len(parts) < 5:
                    raise PerceptionParseError("Q line requires Q|MODE|surface|lemma|ROLE_OR_-|ROLE=value...")
                mode = QueryMode(parts[1].upper())
                predicate = self._line_predicate(parts[2], parts[3])
                requested = None if parts[4] in {"", "-", "_"} else ActantRole(parts[4].upper())
                if mode is QueryMode.FILL_ROLE and requested is None:
                    raise PerceptionParseError("FILL_ROLE Q line requires requested role")
                queries.append(QueryCandidate(
                    predicate=predicate,
                    actants=self._line_actants(parts[5:]),
                    requested_role=requested,
                    query_mode=mode,
                ))
            elif kind == "C":
                if len(parts) < 3:
                    raise PerceptionParseError("C line requires C|surface|lemma|ROLE=value...")
                commands.append(CommandCandidate(
                    predicate=self._line_predicate(parts[1], parts[2]),
                    actants=self._line_actants(parts[3:]),
                ))
            elif kind == "NONE" and len(parts) == 1:
                if len(lines) != 1:
                    raise PerceptionParseError("NONE cannot be combined with semantic acts")
                return PerceptionResult(source_text, (), (), (), ())
            else:
                raise PerceptionParseError(f"unexpected line protocol record: {line!r}")

        return PerceptionResult(
            source_text=source_text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=(),
        )

    @staticmethod
    def _ground_text(value: str) -> str:
        return " ".join(value.casefold().split())

    def _validate_grounding(
        self, source_text: str, result: PerceptionResult, *, strict_predicate: bool = True
    ) -> None:
        source = self._ground_text(source_text)
        implicit_mentions = {"я", "ты", "мы"}

        def check_predicate(predicate: PredicateCandidate) -> None:
            if not predicate.surface.strip():
                raise PerceptionParseError("predicate surface cannot be empty")
            if not strict_predicate or predicate.sense_hint == "IMPLICIT":
                return
            surface = self._ground_text(predicate.surface)
            if surface not in source:
                raise PerceptionParseError(
                    f"ungrounded predicate surface {predicate.surface!r}; copy the surface form from SOURCE or use surface=_ for an implicit predicate"
                )

        def check_actants(actants: tuple[ActantCandidate, ...]) -> None:
            for actant in actants:
                if actant.candidate_ref is not None or actant.mention is None:
                    continue
                mention = self._ground_text(actant.mention)
                if mention in source or mention in implicit_mentions:
                    continue
                raise PerceptionParseError(
                    f"ungrounded actant mention {actant.mention!r}; copy entity/value spans from SOURCE"
                )

        for assertion in result.assertions:
            check_predicate(assertion.predicate)
            check_actants(assertion.actants)
        for query in result.queries:
            check_predicate(query.predicate)
            check_actants(query.actants)
        for command in result.commands:
            check_predicate(command.predicate)
            check_actants(command.actants)

    def _repair_system_prompt(self) -> str:
        if self.settings.protocol == "span_v1":
            return _SPAN_REPAIR_SYSTEM_PROMPT
        if self.settings.protocol == "line_v1":
            return _LINE_REPAIR_SYSTEM_PROMPT
        return _REPAIR_SYSTEM_PROMPT

    @staticmethod
    def _looks_compact(payload: dict[str, Any]) -> bool:
        return any(key in payload for key in ("a", "q", "c")) and not any(
            key in payload for key in ("assertions", "queries", "commands")
        )

    def _compact_result(self, source_text: str, payload: dict[str, Any]) -> PerceptionResult:
        assertions = tuple(self._compact_assertion(v) for v in self._list(payload, "a"))
        queries = tuple(self._compact_query(v) for v in self._list(payload, "q"))
        commands = tuple(self._compact_command(v) for v in self._list(payload, "c"))
        diagnostics_raw = payload.get("d", [])
        if diagnostics_raw is None:
            diagnostics_raw = []
        if not isinstance(diagnostics_raw, list):
            raise PerceptionParseError("compact field 'd' must be a list")
        diagnostics = tuple(str(v) for v in diagnostics_raw)
        return PerceptionResult(source_text, assertions, queries, commands, diagnostics)

    @staticmethod
    def _list(payload: dict[str, Any], key: str) -> list[Any]:
        value = payload.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise PerceptionParseError(f"compact field {key!r} must be a list")
        return value

    @classmethod
    def _compact_predicate(cls, raw: dict[str, Any]) -> PredicateCandidate:
        surface = str(raw.get("p") or "").strip()
        normalized = raw.get("n")
        normalized_text = None if normalized is None else str(normalized).strip() or None
        if not surface and normalized_text:
            surface = normalized_text
        if not surface:
            raise PerceptionParseError("compact predicate 'p' is required")
        return PredicateCandidate(surface=surface, normalized_hint=normalized_text)

    @classmethod
    def _compact_actants(cls, raw: Any) -> tuple[ActantCandidate, ...]:
        if raw is None:
            return ()
        if not isinstance(raw, list):
            raise PerceptionParseError("compact 'r' must be a list")
        result: list[ActantCandidate] = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise PerceptionParseError("compact actant must be [ROLE, value]")
            role = ActantRole(str(item[0]).upper())
            value = item[1]
            if isinstance(value, dict):
                if value.get("ref") is not None:
                    result.append(ActantCandidate(role=role, candidate_ref=str(value["ref"])))
                    continue
                value = value.get("text")
            if value is None:
                raise PerceptionParseError("compact actant value cannot be null")
            text = str(value).strip()
            if not text:
                raise PerceptionParseError("compact actant value cannot be empty")
            if text.startswith("@") and len(text) > 1:
                result.append(ActantCandidate(role=role, candidate_ref=text[1:]))
            else:
                result.append(ActantCandidate(role=role, mention=text))
        return tuple(result)


    @staticmethod
    def _compact_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().casefold()
            if lowered in {"true", "1", "yes"}:
                return True
            if lowered in {"false", "0", "no", ""}:
                return False
        raise PerceptionParseError(f"invalid compact boolean: {value!r}")

    @classmethod
    def _compact_assertion(cls, raw: Any) -> AssertionCandidate:
        if not isinstance(raw, dict):
            raise PerceptionParseError("compact assertion must be an object")
        local_id = str(raw.get("id") or "").strip()
        if not local_id:
            raise PerceptionParseError("compact assertion 'id' is required")
        return AssertionCandidate(
            local_id=local_id,
            predicate=cls._compact_predicate(raw),
            actants=cls._compact_actants(raw.get("r", [])),
            negated=cls._compact_bool(raw.get("neg", False)),
        )

    @classmethod
    def _compact_query(cls, raw: Any) -> QueryCandidate:
        if not isinstance(raw, dict):
            raise PerceptionParseError("compact query must be an object")
        mode = QueryMode(str(raw.get("m") or "EXISTS").upper())
        role_raw = raw.get("role")
        requested_role = None if role_raw in (None, "", "null") else ActantRole(str(role_raw).upper())
        if mode is QueryMode.FILL_ROLE and requested_role is None:
            raise PerceptionParseError("FILL_ROLE compact query requires 'role'")
        return QueryCandidate(
            predicate=cls._compact_predicate(raw),
            actants=cls._compact_actants(raw.get("r", [])),
            requested_role=requested_role,
            query_mode=mode,
        )

    @classmethod
    def _compact_command(cls, raw: Any) -> CommandCandidate:
        if not isinstance(raw, dict):
            raise PerceptionParseError("compact command must be an object")
        return CommandCandidate(
            predicate=cls._compact_predicate(raw),
            actants=cls._compact_actants(raw.get("r", [])),
        )

    @classmethod
    def _legacy_result(cls, source_text: str, payload: dict[str, Any]) -> PerceptionResult:
        assertions = tuple(cls._assertion(v) for v in payload.get("assertions", []))
        queries = tuple(cls._query(v) for v in payload.get("queries", []))
        commands = tuple(cls._command(v) for v in payload.get("commands", []))
        diagnostics = tuple(str(v) for v in payload.get("diagnostics", []))
        return PerceptionResult(source_text, assertions, queries, commands, diagnostics)

    def _system_prompt(self) -> str:
        path = self.settings.system_prompt_path
        if path is not None and path.is_file():
            return path.read_text(encoding="utf-8")
        return _SPAN_SYSTEM_PROMPT if self.settings.protocol == "span_v1" else (_LINE_SYSTEM_PROMPT if self.settings.protocol == "line_v1" else _DEFAULT_SYSTEM_PROMPT)

    def _user_prompt(self, text: str, context: InteractionContext) -> str:
        # Perception receives only the current utterance. Workspace/AgentContext must
        # never leak into this role. span_v1 additionally numbers source tokens so the
        # model selects source spans instead of copying arbitrary strings.
        if self.settings.protocol == "span_v1":
            tokens = self._source_tokens(text)
            token_lines = "\n".join(f"{tok.index}={tok.text}" for tok in tokens)
            return f"TEXT:\n{text}\n\nTOKENS:\n{token_lines}\n\nANSWER:"
        return f"SOURCE:\n{text}"

    def _repair_prompt(self, source_text: str, bad_output: str) -> str:
        suffix = (
            "Return only corrected span_v1 records using token numbers from TOKENS."
            if self.settings.protocol == "span_v1"
            else (
                "Return only corrected line_v1 records."
                if self.settings.protocol == "line_v1"
                else "Return the same parse as valid compact JSON only."
            )
        )
        if self.settings.protocol == "span_v1":
            tokens = self._source_tokens(source_text)
            token_lines = "\n".join(f"{tok.index}={tok.text}" for tok in tokens)
            source_block = f"TEXT:\n{source_text}\n\nTOKENS:\n{token_lines}"
        else:
            source_block = "SOURCE:\n" + source_text
        return source_block + "\n\nBAD OUTPUT:\n" + bad_output + "\n\n" + suffix

    @classmethod
    def _extract_json(cls, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            stripped = "\n".join(lines).strip()
        try:
            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise PerceptionParseError("Perception JSON root must be an object")
            return value
        except json.JSONDecodeError:
            pass

        # Extract first balanced object while respecting quoted strings. This accepts
        # harmless model chatter without trying to semantically repair malformed JSON.
        start = stripped.find("{")
        if start < 0:
            raise PerceptionParseError("LLM response contains no JSON object")
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(stripped[start:i + 1])
                    except json.JSONDecodeError as exc:
                        raise PerceptionParseError(f"Malformed JSON object: {exc}") from exc
                    if not isinstance(value, dict):
                        raise PerceptionParseError("Perception JSON root must be an object")
                    return value
        raise PerceptionParseError("Unbalanced JSON object in LLM response")

    @classmethod
    def _predicate(cls, raw: dict[str, Any]) -> PredicateCandidate:
        return PredicateCandidate(
            surface=str(raw.get("surface") or raw.get("predicate") or ""),
            normalized_hint=(None if raw.get("normalized_hint") is None else str(raw.get("normalized_hint"))),
            sense_hint=(None if raw.get("sense_hint") is None else str(raw.get("sense_hint"))),
            evidence=cls._evidence(raw.get("evidence")),
        )

    @classmethod
    def _actant(cls, raw: dict[str, Any]) -> ActantCandidate:
        role = ActantRole(str(raw["role"]).upper())
        confidence = raw.get("parser_confidence")
        return ActantCandidate(
            role=role,
            mention=(None if raw.get("mention") is None else str(raw.get("mention"))),
            normalized_hint=(None if raw.get("normalized_hint") is None else str(raw.get("normalized_hint"))),
            semantic_hint=(None if raw.get("semantic_hint") is None else str(raw.get("semantic_hint"))),
            candidate_ref=(None if raw.get("candidate_ref") is None else str(raw.get("candidate_ref"))),
            entity_ref=(None if raw.get("entity_ref") is None else str(raw.get("entity_ref"))),
            evidence=cls._evidence(raw.get("evidence")),
            parser_confidence=(None if confidence is None else float(confidence)),
        )

    @classmethod
    def _assertion(cls, raw: dict[str, Any]) -> AssertionCandidate:
        return AssertionCandidate(
            local_id=str(raw["local_id"]),
            predicate=cls._predicate(raw.get("predicate") or {}),
            actants=tuple(cls._actant(v) for v in raw.get("actants", [])),
            evidence=cls._evidence(raw.get("evidence")),
            alternatives=tuple(cls._assertion(v) for v in raw.get("alternatives", [])),
            negated=bool(raw.get("negated", False)),
        )

    @classmethod
    def _query(cls, raw: dict[str, Any]) -> QueryCandidate:
        mode = QueryMode(str(raw.get("query_mode", "EXISTS")).upper())
        role_raw = raw.get("requested_role")
        return QueryCandidate(
            predicate=cls._predicate(raw.get("predicate") or {}),
            actants=tuple(cls._actant(v) for v in raw.get("actants", [])),
            requested_role=(None if role_raw is None else ActantRole(str(role_raw).upper())),
            query_mode=mode,
        )

    @classmethod
    def _command(cls, raw: dict[str, Any]) -> CommandCandidate:
        return CommandCandidate(
            predicate=cls._predicate(raw.get("predicate") or {}),
            actants=tuple(cls._actant(v) for v in raw.get("actants", [])),
        )

    @staticmethod
    def _evidence(raw: Any) -> EvidenceSpan | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            return EvidenceSpan(raw)
        return EvidenceSpan(
            text=str(raw.get("text", "")),
            start=(None if raw.get("start") is None else int(raw.get("start"))),
            end=(None if raw.get("end") is None else int(raw.get("end"))),
        )


_SPAN_SYSTEM_PROMPT = """Parse only the current user utterance. The user provides TEXT and numbered TOKENS.
Return only short records separated by |. No explanations, JSON, or markdown.

Assertion: A, then A1/A2..., predicate token number, base predicate form, 0 or 1 for negation, then roles.
Query: Q, then EXISTS or FILL_ROLE, predicate token number, base predicate form, requested role or -, then roles.
Command: C, then predicate token number, base predicate form, then roles.
Write a role as ROLE=N or ROLE=N-M, where N is only a TOKENS index. If one argument contains and/or, give its full continuous token range once. A nested fact may be ROLE=@A2. For implicit I/you/we, $SELF/$USER/$WE are allowed. If there are no acts, return NONE.

Do not copy TEXT or TOKENS. Do not invent words or UIDs.
Allowed roles: SUBJECT, OBJECT, AUXILLIARY, RECIPIENT, SOURCE, ABSENTEE, LOCATION, STATE, TIME, DURATION, CAUSE, PURPOSE, TOOL, MATERIAL, AMOUNT, HOW-TO."""

_SPAN_REPAIR_SYSTEM_PROMPT = """The previous answer was malformed. Parse only TEXT. Return only A/Q/C records with numeric TOKENS references, or NONE. Do not repeat instructions or examples."""

_LINE_SYSTEM_PROMPT = """You are a semantic parser. Return only line_v1 records. No JSON, markdown, or explanations.
A|ID|surface|lemma|0/1|ROLE=value...
Q|EXISTS/FILL_ROLE|surface|lemma|ROLE_OR_-|ROLE=value...
C|surface|lemma|ROLE=value...
If there are no acts: NONE

Copy surface and ROLE values from SOURCE exactly. Use the base predicate form for lemma. If the predicate is implicit, surface=_. @A2 refers to assertion A2. Do not turn a question into an assertion. Do not emit UIDs or C/P/H/L. Do not add facts.
Allowed roles: SUBJECT, OBJECT, AUXILLIARY, RECIPIENT, SOURCE, ABSENTEE, LOCATION, STATE, TIME, DURATION, CAUSE, PURPOSE, TOOL, MATERIAL, AMOUNT, HOW-TO."""

_LINE_REPAIR_SYSTEM_PROMPT = """Repair only the line_v1 format of the previous parse. Return only A|..., Q|..., C|..., or NONE. Do not add or remove semantic acts. Copy ROLE values from SOURCE."""

_DEFAULT_SYSTEM_PROMPT = """You are a semantic parser. Return only JSON, without markdown.
Format: {"a":[{"id":"A1","p":"predicate surface","n":"base form","neg":false,"r":[["SUBJECT","text"],["OBJECT","text"]]}],"q":[],"c":[]}
Use @A2 instead of text for a nested assertion.
Query: {"m":"EXISTS","p":"predicate","n":"base form","role":null,"r":[]}. For a missing role use m="FILL_ROLE" and role="OBJECT".
Command: {"p":"predicate","n":"base form","r":[]}.
Allowed roles: SUBJECT, OBJECT, AUXILLIARY, RECIPIENT, SOURCE, ABSENTEE, LOCATION, STATE, TIME, DURATION, CAUSE, PURPOSE, TOOL, MATERIAL, AMOUNT, HOW-TO.
Do not emit UIDs or C/P/H/L. Do not invent facts. Keep pronouns, deictic words, dates, and places as source text. If there are no acts, return {"a":[],"q":[],"c":[]}."""

_REPAIR_SYSTEM_PROMPT = """Repair only the format of the previous parse. Return one valid compact JSON object with keys a, q, c. Do not add or remove semantic acts."""
