from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable

from ah.model import ActantRole

from .contracts import (
    ActantCandidate,
    AssertionCandidate,
    EvidenceSpan,
    PerceptionResult,
    TemplateCandidate,
    TemporalScopeCandidate,
    TemporalScopeKind,
    TemporalScopeProbeDecision,
)
from .morphology import Morphology, material_analyses


class TemporalScopeFormalizationError(ValueError):
    """Raised when temporal quantifier meaning/scope cannot be fixed safely."""


TemporalScopeSemanticResolver = Callable[
    [str, AssertionCandidate, tuple[EvidenceSpan, ...]],
    TemporalScopeProbeDecision,
]


@dataclass(frozen=True, slots=True)
class _Cue:
    index: int
    evidence: EvidenceSpan


class TemporalScopeFormalizer:
    """Distinguish proposition-level NEVER from ordinary predicate negation.

    The deterministic gate uses already assigned temporal/circumstantial roles
    and morphology only to bound the possible source cue.  It does not map words
    or phrases to NEVER.  One closed semantic decision chooses NEVER versus plain
    negation; Python then installs a TIME binder and consumes predicate negation.
    """

    _WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё-]+")
    _CUE_ROLES = frozenset(
        {ActantRole.TIME, ActantRole.DURATION, ActantRole.AMOUNT, ActantRole.HOW_TO}
    )

    def __init__(self, morphology: Morphology) -> None:
        self.morphology = morphology

    @staticmethod
    def _source_context(
        result: PerceptionResult, assertion: AssertionCandidate
    ) -> str:
        if assertion.evidence is not None and assertion.evidence.text.strip():
            return assertion.evidence.text.strip()
        return result.source_text

    @staticmethod
    def _actant_evidence(actant: ActantCandidate) -> EvidenceSpan | None:
        if actant.evidence is not None and actant.evidence.text.strip():
            return actant.evidence
        text = (actant.mention or actant.normalized_hint or "").strip()
        return EvidenceSpan(text) if text else None

    def _has_material_cue_morphology(self, actant: ActantCandidate) -> bool:
        text = (actant.mention or actant.normalized_hint or "").strip()
        if not text:
            return False
        readings = []
        for token in self._WORD_RE.findall(text):
            try:
                values = tuple(self.morphology.analyze_all(token))
            except AttributeError:
                value = self.morphology.analyze(token)
                values = () if value is None else (value,)
            readings.extend(material_analyses(values))
        if not readings:
            # Role assignment is already structural evidence.  A morphology
            # backend may legitimately be disabled/OOV; do not turn that into a
            # word-level semantic fallback.
            return actant.role in self._CUE_ROLES
        return any(
            item.pos in {"ADVB", "PRCL", "NPRO", "NUMR", "PREP", "NOUN"}
            for item in readings
        )

    def _cues(self, assertion: AssertionCandidate) -> tuple[_Cue, ...]:
        out = []
        for index, actant in enumerate(assertion.actants):
            if (
                actant.role not in self._CUE_ROLES
                or actant.candidate_ref is not None
                or actant.entity_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
                or actant.quantifier is not None
                or not self._has_material_cue_morphology(actant)
            ):
                continue
            evidence = self._actant_evidence(actant)
            if evidence is not None:
                out.append(_Cue(index, evidence))
        return tuple(out)

    @staticmethod
    def _with_time_role(predicate):
        candidate = predicate.template_candidate
        if candidate is None or ActantRole.TIME in candidate.roles:
            return predicate
        updated = tuple(
            role
            for role in candidate.roles
            if role
            not in {
                ActantRole.DURATION,
                ActantRole.AMOUNT,
                ActantRole.HOW_TO,
            }
        )
        if ActantRole.TIME not in updated:
            updated = (*updated, ActantRole.TIME)
        return replace(predicate, template_candidate=TemplateCandidate(updated))

    def _install(
        self,
        assertion: AssertionCandidate,
        cue: _Cue,
        candidate: TemporalScopeCandidate,
    ) -> AssertionCandidate:
        actants = list(assertion.actants)
        original = actants[cue.index]
        if any(
            index != cue.index and item.role is ActantRole.TIME
            for index, item in enumerate(actants)
        ):
            raise TemporalScopeFormalizationError(
                f"NEVER scope has more than one possible TIME slot in {assertion.local_id!r}"
            )
        actants[cue.index] = replace(
            original,
            role=ActantRole.TIME,
            entity_ref=candidate.variable_ref,
            temporal=None,
            quantifier=None,
        )
        return replace(
            assertion,
            predicate=self._with_time_role(assertion.predicate),
            actants=tuple(actants),
            negated=False,
            temporal_scope=candidate,
        )

    def _formalize_variant(
        self,
        result: PerceptionResult,
        assertion: AssertionCandidate,
        resolver: TemporalScopeSemanticResolver | None,
    ) -> AssertionCandidate:
        cues = self._cues(assertion)
        explicit = assertion.temporal_scope
        if explicit is not None:
            matches = tuple(
                _Cue(
                    index,
                    self._actant_evidence(actant)
                    or explicit.evidence
                    or EvidenceSpan("temporal scope"),
                )
                for index, actant in enumerate(assertion.actants)
                if actant.entity_ref == explicit.variable_ref
            )
            if len(matches) == 1:
                return self._install(assertion, matches[0], explicit)
            if len(cues) != 1:
                raise TemporalScopeFormalizationError(
                    f"Explicit temporal scope has no unique source cue in {assertion.local_id!r}"
                )
            return self._install(assertion, cues[0], explicit)

        if not assertion.negated or not cues:
            return assertion
        if resolver is None:
            # Integration consumes explicit typed semantics only; it never
            # reinterprets source words after Perception.
            return assertion
        decision = resolver(
            self._source_context(result, assertion),
            assertion,
            tuple(item.evidence for item in cues),
        )
        if not isinstance(decision, TemporalScopeProbeDecision):
            raise TemporalScopeFormalizationError(
                "Temporal-scope resolver returned an invalid bounded decision"
            )
        if decision is TemporalScopeProbeDecision.PLAIN_NEGATION:
            return assertion
        if decision is TemporalScopeProbeDecision.AMBIGUOUS:
            raise TemporalScopeFormalizationError(
                f"Temporal NEVER scope is ambiguous for {assertion.predicate.surface!r}"
            )
        if len(cues) != 1:
            raise TemporalScopeFormalizationError(
                f"Temporal NEVER source cue is not unique for {assertion.local_id!r}"
            )
        cue = cues[0]
        candidate = TemporalScopeCandidate(
            TemporalScopeKind.NEVER,
            variable_ref=f"TS:{assertion.local_id}:TIME",
            anchor="RELEVANT_PAST",
            evidence=cue.evidence,
        )
        return self._install(assertion, cue, candidate)

    def formalize(
        self,
        result: PerceptionResult,
        *,
        resolver: TemporalScopeSemanticResolver | None = None,
    ) -> PerceptionResult:
        """Return an idempotently scoped copy without reading or writing AH."""

        assertions = []
        for assertion in result.assertions:
            base = self._formalize_variant(
                result, replace(assertion, alternatives=()), resolver
            )
            alternatives = tuple(
                self._formalize_variant(
                    result, replace(item, alternatives=()), resolver
                )
                for item in assertion.alternatives
            )
            if alternatives:
                signatures = {
                    (
                        None
                        if item.temporal_scope is None
                        else (
                            item.temporal_scope.kind,
                            item.temporal_scope.variable_ref,
                            item.temporal_scope.anchor,
                        ),
                        item.negated,
                    )
                    for item in (base, *alternatives)
                }
                if len(signatures) != 1:
                    raise TemporalScopeFormalizationError(
                        f"Temporal-scope alternatives disagree for {assertion.local_id!r}"
                    )
            assertions.append(replace(base, alternatives=alternatives))
        return replace(result, assertions=tuple(assertions))
