from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable

from ah.model import ActantRole
from ah.temporal import TemporalMode, TemporalModeProbeDecision

from .contracts import AssertionCandidate, AssertionStatus, PerceptionResult
from .morphology import Morphology, material_analyses


class TemporalModeFormalizationError(ValueError):
    """Raised when an occurrence-level temporal reading cannot be fixed safely."""


@dataclass(frozen=True, slots=True)
class PredicateTemporalProfile:
    """UID-free morphology summary supplied to the bounded semantic probe."""

    aspects: tuple[str, ...] = ()
    tenses: tuple[str, ...] = ()
    moods: tuple[str, ...] = ()
    poses: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("aspects", "tenses", "moods", "poses"):
            values = tuple(
                sorted(
                    {
                        str(value).strip().casefold()
                        for value in getattr(self, field_name)
                        if str(value).strip()
                    }
                )
            )
            object.__setattr__(self, field_name, values)


TemporalModeSemanticResolver = Callable[
    [str, AssertionCandidate, PredicateTemporalProfile],
    TemporalModeProbeDecision,
]


class TemporalModeFormalizer:
    """Classify temporal interpretation on an occurrence, never on canonical T.

    Structure and morphology may settle only genuinely invariant cases.  A
    bounded semantic resolver handles the remaining observable cases and may
    abstain.  The pass produces staging metadata only and never reads or writes AH.
    """

    _WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё-]+")
    _VERBAL_POSES = frozenset({"VERB", "INFN", "PRTF", "PRTS", "GRND"})
    _ASPECTS = frozenset({"perf", "impf"})
    _TENSES = frozenset({"past", "pres", "futr"})
    _MOODS = frozenset({"indc", "impr"})
    _STATE_SENSES = frozenset(
        {"RESULT_STATE", "IMPLICIT", "NOMINAL_PREDICATION"}
    )

    def __init__(self, morphology: Morphology) -> None:
        self.morphology = morphology

    def _profile(self, assertion: AssertionCandidate) -> PredicateTemporalProfile:
        surface = (
            assertion.predicate.evidence.text
            if assertion.predicate.evidence is not None
            and assertion.predicate.evidence.text.strip()
            else assertion.predicate.surface
        )
        analyses = []
        for token in self._WORD_RE.findall(surface):
            try:
                readings = tuple(self.morphology.analyze_all(token))
            except AttributeError:
                reading = self.morphology.analyze(token)
                readings = () if reading is None else (reading,)
            analyses.extend(
                item
                for item in material_analyses(readings)
                if item.pos in self._VERBAL_POSES
            )
        aspects = {
            value
            for item in analyses
            for value in self._ASPECTS
            if value in item.grammemes
        }
        tenses = {
            value
            for item in analyses
            for value in self._TENSES
            if value in item.grammemes
        }
        moods = {
            value
            for item in analyses
            for value in self._MOODS
            if value in item.grammemes
        }
        moods.update(item.mood for item in analyses if item.mood)
        return PredicateTemporalProfile(
            tuple(aspects),
            tuple(tenses),
            tuple(moods),
            tuple(item.pos for item in analyses if item.pos),
        )

    @staticmethod
    def _source_context(
        result: PerceptionResult, assertion: AssertionCandidate
    ) -> str:
        if assertion.evidence is not None and assertion.evidence.text.strip():
            return assertion.evidence.text.strip()
        return result.source_text

    @staticmethod
    def _observable(assertion: AssertionCandidate) -> bool:
        return any(
            actant.role in {ActantRole.TIME, ActantRole.DURATION}
            for actant in assertion.actants
        )

    @classmethod
    def _deterministic_mode(
        cls,
        assertion: AssertionCandidate,
        profile: PredicateTemporalProfile,
    ) -> TemporalMode | None:
        sense = str(assertion.predicate.sense_hint or "").strip().upper()
        if sense in cls._STATE_SENSES:
            return TemporalMode.STATE
        if profile.aspects == ("perf",):
            return TemporalMode.EVENT
        return None

    def _formalize_variant(
        self,
        result: PerceptionResult,
        assertion: AssertionCandidate,
        resolver: TemporalModeSemanticResolver | None,
        *,
        scoped_refs: frozenset[str],
    ) -> AssertionCandidate:
        if assertion.temporal_mode is not None:
            return assertion
        if (
            assertion.status is not AssertionStatus.ASSERTED
            or assertion.quoted
            or assertion.local_id in scoped_refs
            or not self._observable(assertion)
        ):
            return assertion

        profile = self._profile(assertion)
        mode = self._deterministic_mode(assertion, profile)
        if mode is None:
            if resolver is None:
                raise TemporalModeFormalizationError(
                    f"Temporal mode requires a bounded semantic decision for "
                    f"{assertion.predicate.surface!r}"
                )
            decision = resolver(
                self._source_context(result, assertion), assertion, profile
            )
            if not isinstance(decision, TemporalModeProbeDecision):
                raise TemporalModeFormalizationError(
                    "Temporal-mode resolver returned an invalid bounded decision"
                )
            if decision is TemporalModeProbeDecision.AMBIGUOUS:
                raise TemporalModeFormalizationError(
                    f"Temporal mode is ambiguous for "
                    f"{assertion.predicate.surface!r}"
                )
            mode = TemporalMode(decision.value)
        return replace(assertion, temporal_mode=mode)

    def formalize(
        self,
        result: PerceptionResult,
        *,
        resolver: TemporalModeSemanticResolver | None = None,
    ) -> PerceptionResult:
        """Return an idempotently classified copy without canonical side effects."""

        scoped_refs = frozenset(
            ref
            for root in result.proposition_roots
            for ref in (
                *root.expression.leaf_refs(),
                *root.operator_source_refs,
            )
        )
        assertions: list[AssertionCandidate] = []
        for assertion in result.assertions:
            base = self._formalize_variant(
                result,
                replace(assertion, alternatives=()),
                resolver,
                scoped_refs=scoped_refs,
            )
            alternatives = tuple(
                self._formalize_variant(
                    result,
                    replace(alternative, alternatives=()),
                    resolver,
                    scoped_refs=scoped_refs,
                )
                for alternative in assertion.alternatives
            )
            if alternatives:
                modes = {base.temporal_mode, *(item.temporal_mode for item in alternatives)}
                if len(modes) != 1:
                    raise TemporalModeFormalizationError(
                        f"Temporal-mode alternatives disagree for "
                        f"{assertion.predicate.surface!r}"
                    )
            assertions.append(replace(base, alternatives=alternatives))
        return replace(result, assertions=tuple(assertions))
