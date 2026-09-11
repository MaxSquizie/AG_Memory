from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable

from ah.model import ActantRole

from .contracts import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QuantifierCandidate,
    QuantifierKind,
    QuantifierProbeDecision,
)
from .morphology import Morphology, material_analyses
from .semantic_composition import SemanticCompositionError, reconcile_quantifier_scope


class QuantifierFormalizationError(ValueError):
    """Raised when source quantifier kind/scope cannot be represented safely."""


QuantifierSemanticResolver = Callable[
    [str, PredicateCandidate, ActantCandidate, bool],
    QuantifierProbeDecision,
]


@dataclass(frozen=True, slots=True)
class _Recognition:
    candidate: QuantifierCandidate
    cleaned_mention: str
    normalized_mention: str
    consumes_predicate_negation: bool = False


class QuantifierFormalizer:
    """Separate source-level binder pass before canonical Integration.

    Candidate discovery and role assignment have already happened.  A bounded
    semantic resolver classifies only one existing actant at a time; Python then
    validates the fixed label, derives a restriction from morphology, assigns a
    batch-local handle and reconciles predicate-vs-quantifier negation.  With no
    resolver this pass is deliberately conservative and only normalizes explicit
    :class:`QuantifierCandidate` metadata supplied by Perception/tests.
    """

    _WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё-]+")
    _QUOTE_CHARS = frozenset({'"', "'", "«", "»", "„", "“", "”", "‘", "’"})

    def __init__(self, morphology: Morphology) -> None:
        self.morphology = morphology

    @staticmethod
    def _fold(value: str) -> str:
        return " ".join(value.strip().casefold().replace("ё", "е").split())

    @classmethod
    def _tokens(cls, value: str) -> tuple[str, ...]:
        return tuple(match.group(0) for match in cls._WORD_RE.finditer(value))

    @staticmethod
    def _source_phrase(source_text: str, actant: ActantCandidate) -> str:
        evidence = actant.evidence
        if (
            evidence is not None
            and evidence.start is not None
            and evidence.end is not None
            and 0 <= evidence.start <= evidence.end <= len(source_text)
        ):
            exact = source_text[evidence.start:evidence.end].strip()
            if exact:
                return exact
        return (actant.mention or actant.normalized_hint or "").strip()

    @classmethod
    def _is_quoted_actant(
        cls, source_text: str, actant: ActantCandidate, phrase: str
    ) -> bool:
        evidence = actant.evidence
        if evidence is None or evidence.start is None or evidence.end is None:
            return bool(
                len(phrase) >= 2
                and phrase[0] in cls._QUOTE_CHARS
                and phrase[-1] in cls._QUOTE_CHARS
            )
        left = source_text[evidence.start - 1] if evidence.start > 0 else ""
        right = source_text[evidence.end] if evidence.end < len(source_text) else ""
        return left in cls._QUOTE_CHARS and right in cls._QUOTE_CHARS

    def _nominal_restriction(
        self, actant: ActantCandidate, phrase: str
    ) -> tuple[str | None, str | None]:
        """Return a source-grounded nominal head lemma and surface.

        This is grammatical normalization, not quantifier classification.  A
        structured NP head supplied by the parser wins.  Otherwise morphology must
        expose one unambiguous noun lemma for the rightmost nominal token.
        """

        for relation in actant.nominal_relations:
            head = (relation.head_normalized_hint or relation.head_mention).strip()
            tokens = self._tokens(head)
            if tokens:
                return self._fold(head), relation.head_mention.strip() or tokens[-1]

        for token in reversed(self._tokens(phrase)):
            try:
                analyses = tuple(self.morphology.analyze_all(token))
            except AttributeError:
                single = self.morphology.analyze(token)
                analyses = () if single is None else (single,)
            nominal = tuple(
                item
                for item in material_analyses(analyses)
                if item.pos == "NOUN" and item.normal_form.strip()
            )
            lemmas = {self._fold(item.normal_form) for item in nominal}
            if len(lemmas) == 1:
                return next(iter(lemmas)), token
        return None, None

    @staticmethod
    def _assertion_source(
        result: PerceptionResult, assertion: AssertionCandidate
    ) -> str:
        if assertion.evidence is not None and assertion.evidence.text.strip():
            return assertion.evidence.text.strip()
        return result.source_text

    def _eligible(self, actant: ActantCandidate) -> bool:
        """Use grammar only to decide whether a semantic probe is warranted.

        This gate never selects a quantifier kind.  It avoids model calls for an
        unambiguously ordinary single noun/proper name, a third-person personal
        pronoun, and non-nominal frame values.  Multi-token nominal phrases and
        determiner/pronominal/numeral readings remain open to the semantic probe.
        A disabled or evidence-free morphology fails closed instead of treating an
        OOV term as quantificational.
        """

        if (
            actant.candidate_ref is not None
            or actant.composition is not None
            or actant.proposition is not None
        ):
            return False
        phrase = (actant.mention or actant.normalized_hint or "").strip()
        tokens = self._tokens(phrase)
        if not tokens or getattr(self.morphology, "name", None) == "none":
            return False
        if actant.role not in {
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.RECIPIENT,
            ActantRole.SOURCE,
            ActantRole.ABSENTEE,
            ActantRole.AUXILLIARY,
            ActantRole.LOCATION,
            ActantRole.TIME,
            ActantRole.TOOL,
            ActantRole.MATERIAL,
        }:
            return False
        if len(tokens) == 1 and hasattr(self.morphology, "is_known"):
            try:
                if not self.morphology.is_known(tokens[0]):
                    return False
            except (AttributeError, NotImplementedError):
                pass

        analyses = []
        for token in tokens:
            try:
                token_analyses = tuple(self.morphology.analyze_all(token))
            except AttributeError:
                item = self.morphology.analyze(token)
                token_analyses = () if item is None else (item,)
            analyses.extend(material_analyses(token_analyses))
        if not analyses:
            return False

        has_pronominal = any(item.pos == "NPRO" for item in analyses)
        has_determiner = any(
            bool({"Apro", "Anum", "Ques", "Dmns"} & set(item.grammemes))
            for item in analyses
        )
        if has_pronominal or has_determiner:
            if len(tokens) == 1 and all(
                item.pos == "NPRO" and "3per" in item.grammemes
                for item in analyses
            ):
                return False
            return True
        nominal_count = sum(item.pos == "NOUN" for item in analyses)
        has_particle = any(item.pos == "PRCL" for item in analyses)
        if len(tokens) > 1 and (nominal_count > 1 or (has_particle and nominal_count)):
            return True
        return False

    def _semantic_recognition(
        self,
        result: PerceptionResult,
        assertion: AssertionCandidate,
        actant: ActantCandidate,
        resolver: QuantifierSemanticResolver,
    ) -> _Recognition | None:
        phrase = self._source_phrase(result.source_text, actant)
        if not phrase or self._is_quoted_actant(result.source_text, actant, phrase):
            return None
        decision = resolver(
            self._assertion_source(result, assertion),
            assertion.predicate,
            actant,
            assertion.negated,
        )
        if not isinstance(decision, QuantifierProbeDecision):
            raise QuantifierFormalizationError(
                "Quantifier resolver returned an invalid bounded decision"
            )
        if decision is QuantifierProbeDecision.NONE:
            return None
        if decision is QuantifierProbeDecision.AMBIGUOUS:
            raise QuantifierFormalizationError(
                f"Quantifier kind or scope is ambiguous for {phrase!r}"
            )

        kind = QuantifierKind(decision.value)
        restriction, head_surface = self._nominal_restriction(actant, phrase)
        if kind in {QuantifierKind.FORALL, QuantifierKind.NOT_FORALL} and not restriction:
            raise QuantifierFormalizationError(
                f"Universal quantifier has no source-grounded restriction for {phrase!r}"
            )
        cleaned = head_surface or (
            actant.mention or actant.normalized_hint or phrase
        ).strip()
        normalized = restriction or self._fold(cleaned)
        return _Recognition(
            QuantifierCandidate(kind, phrase, restriction, actant.evidence),
            cleaned,
            normalized,
            kind in {QuantifierKind.NOT_EXISTS, QuantifierKind.NOT_FORALL},
        )

    def _formalize_variant(
        self,
        result: PerceptionResult,
        assertion: AssertionCandidate,
        resolver: QuantifierSemanticResolver | None,
    ) -> AssertionCandidate:
        if assertion.quoted:
            return assertion
        actants: list[ActantCandidate] = []
        recognized: list[_Recognition] = []
        for index, actant in enumerate(assertion.actants):
            if actant.quantifier is not None:
                mention = (
                    actant.mention
                    or actant.normalized_hint
                    or actant.quantifier.surface
                ).strip()
                found = _Recognition(
                    actant.quantifier,
                    mention,
                    (actant.normalized_hint or mention).strip(),
                )
            elif resolver is not None and self._eligible(actant):
                found = self._semantic_recognition(result, assertion, actant, resolver)
            else:
                found = None
            if found is None:
                actants.append(actant)
                continue
            handle = actant.entity_ref or f"Q:{assertion.local_id}:{actant.role.value}:{index}"
            actants.append(
                replace(
                    actant,
                    mention=found.cleaned_mention,
                    normalized_hint=found.normalized_mention,
                    entity_ref=handle,
                    quantifier=found.candidate,
                )
            )
            recognized.append(found)

        if not recognized:
            return assertion
        kinds = {item.candidate.kind for item in recognized}
        if QuantifierKind.NOT_EXISTS in kinds and kinds & {
            QuantifierKind.FORALL,
            QuantifierKind.NOT_FORALL,
        }:
            raise QuantifierFormalizationError(
                "Cannot mix a negative existential with a universal in one assertion"
            )
        if QuantifierKind.FORALL in kinds and QuantifierKind.NOT_FORALL in kinds:
            raise QuantifierFormalizationError(
                "Mixed FORALL / NOT_FORALL scope in one assertion is not guessed"
            )
        if sum(
            item.candidate.kind is QuantifierKind.NOT_FORALL
            for item in recognized
        ) > 1:
            raise QuantifierFormalizationError(
                "Several negated universal scopes require an explicit scope decision"
            )

        negated = assertion.negated
        if kinds & {QuantifierKind.NOT_FORALL, QuantifierKind.NOT_EXISTS}:
            if negated and not all(
                item.consumes_predicate_negation
                for item in recognized
                if item.candidate.kind
                in {QuantifierKind.NOT_FORALL, QuantifierKind.NOT_EXISTS}
            ):
                raise QuantifierFormalizationError(
                    "Explicit negative binder and predicate negation require "
                    "separate source-grounded scope metadata"
                )
            if any(item.consumes_predicate_negation for item in recognized):
                negated = False
        return replace(assertion, actants=tuple(actants), negated=negated)

    def formalize(
        self,
        result: PerceptionResult,
        *,
        resolver: QuantifierSemanticResolver | None = None,
    ) -> PerceptionResult:
        """Return an idempotently quantified copy; never mutate canonical AH."""

        assertions: list[AssertionCandidate] = []
        for assertion in result.assertions:
            base = self._formalize_variant(result, assertion, resolver)
            alternatives = tuple(
                self._formalize_variant(result, alternative, resolver)
                for alternative in assertion.alternatives
            )
            if alternatives:
                kinds_by_variant = {
                    tuple(
                        (
                            actant.role,
                            None
                            if actant.quantifier is None
                            else (
                                actant.quantifier.kind,
                                actant.quantifier.restriction_lemma,
                            ),
                        )
                        for actant in variant.actants
                    )
                    for variant in (base, *alternatives)
                }
                if len(kinds_by_variant) != 1:
                    raise QuantifierFormalizationError(
                        f"Quantifier alternatives disagree in {assertion.local_id}"
                    )
                if len({base.negated, *(item.negated for item in alternatives)}) != 1:
                    raise QuantifierFormalizationError(
                        f"Quantifier alternatives disagree on polarity in {assertion.local_id}"
                    )
            assertions.append(replace(base, alternatives=alternatives))
        try:
            return reconcile_quantifier_scope(result, tuple(assertions))
        except SemanticCompositionError as exc:
            raise QuantifierFormalizationError(
                f"semantic composition invalid after quantifier formalization: {exc}"
            ) from exc
