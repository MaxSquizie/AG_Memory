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
    _NEGATION_PARTICLES = frozenset({"не", "ни"})

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

    @classmethod
    def _predicate_has_local_negation(
        cls, source_text: str, predicate: PredicateCandidate
    ) -> bool:
        """Return whether an overt grammatical negation directly precedes the predicate.

        This is a source-span check, not semantic quantifier recognition.  It is
        intentionally narrow: only an independently visible ``не``/``ни`` token
        immediately before the predicate (modulo punctuation/whitespace) counts as
        body-level negation evidence.  Wider scope remains the bounded semantic
        resolver's responsibility.
        """

        evidence = predicate.evidence
        if (
            evidence is None
            or evidence.start is None
            or evidence.start <= 0
            or evidence.start > len(source_text)
        ):
            return False
        prefix = source_text[: evidence.start]
        matches = tuple(cls._WORD_RE.finditer(prefix))
        if not matches:
            return False
        previous = matches[-1]
        between = prefix[previous.end() :]
        if any(char.isalnum() for char in between):
            return False
        return cls._fold(previous.group(0)) in cls._NEGATION_PARTICLES

    @classmethod
    def _independent_negative_scope_conflict(
        cls,
        source_text: str,
        predicate: PredicateCandidate,
        phrase: str,
        *,
        predicate_negated: bool,
    ) -> bool:
        """Detect two source-visible negative sites that cannot be collapsed safely.

        ``NOT_FORALL`` expressions often contain their own standalone ``не`` while
        Russian negative existentials use concord (e.g. a ``ни``-phrase plus verbal
        ``не``).  If a binder phrase itself contains standalone ``не`` *and* the
        predicate has a separate local negation, there are two independently visible
        scope sites.  A single NOT_FORALL/NOT_EXISTS label is insufficient to decide
        whether the second negation belongs inside or outside the binder, so the
        formalizer must fail closed rather than consume it.
        """

        if not predicate_negated:
            return False
        phrase_tokens = tuple(cls._fold(token) for token in cls._tokens(phrase))
        if "не" not in phrase_tokens:
            return False
        return cls._predicate_has_local_negation(source_text, predicate)

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

    def _phrase_profile(self, phrase: str) -> tuple[bool, bool]:
        """Return (binder-like morphology, nominal-head morphology)."""

        binder = False
        nominal = False
        for token in self._tokens(phrase):
            analyses = self._analyses(token)
            for item in material_analyses(analyses):
                nominal = nominal or item.pos == "NOUN"
                binder = binder or item.pos in {"NPRO", "NUMR"} or bool(
                    {"Apro", "Anum", "Ques", "Dmns"}
                    & set(item.grammemes)
                )
        return binder, nominal

    def _analyses(self, token: str):
        try:
            return tuple(self.morphology.analyze_all(token))
        except AttributeError:
            item = self.morphology.analyze(token)
            return () if item is None else (item,)

    def _expand_hyphenated_actants(
        self,
        source_text: str,
        actants: tuple[ActantCandidate, ...],
    ) -> tuple[ActantCandidate, ...]:
        """Restore a source-adjacent hyphen suffix to its provisional actant."""

        expanded: list[ActantCandidate] = []
        for actant in actants:
            evidence = actant.evidence
            if (
                evidence is None
                or evidence.start is None
                or evidence.end is None
            ):
                expanded.append(actant)
                continue
            suffix = re.match(
                r"[-‐‑][A-Za-zА-Яа-яЁё]+",
                source_text[int(evidence.end) :],
            )
            if suffix is None:
                expanded.append(actant)
                continue
            end = int(evidence.end) + suffix.end()
            phrase = source_text[int(evidence.start) : end]
            binder, _nominal = self._phrase_profile(phrase)
            if not binder:
                expanded.append(actant)
                continue
            expanded.append(
                replace(
                    actant,
                    mention=phrase,
                    normalized_hint=None,
                    evidence=type(evidence)(phrase, evidence.start, end),
                )
            )
        return tuple(expanded)

    def _fuse_split_nominal_binders(
        self,
        source_text: str,
        assertion: AssertionCandidate,
    ) -> AssertionCandidate:
        """Rejoin a determiner fragment with its adjacent nominal restriction."""

        actants = list(
            self._expand_hyphenated_actants(source_text, assertion.actants)
        )
        consumed: set[int] = set()
        replacements: dict[int, ActantCandidate] = {}
        ordered = sorted(
            range(len(actants)),
            key=lambda index: (
                actants[index].evidence.start
                if actants[index].evidence is not None
                and actants[index].evidence.start is not None
                else 10**12,
                index,
            ),
        )
        weak_fragment_roles = {
            ActantRole.AMOUNT,
            ActantRole.AUXILLIARY,
            ActantRole.HOW_TO,
        }
        for left_index, right_index in zip(ordered, ordered[1:]):
            if left_index in consumed or right_index in consumed:
                continue
            left = actants[left_index]
            right = actants[right_index]
            if any(
                item.candidate_ref is not None
                or item.composition is not None
                or item.proposition is not None
                or item.quantifier is not None
                for item in (left, right)
            ):
                continue
            left_evidence = left.evidence
            right_evidence = right.evidence
            if (
                left_evidence is None
                or right_evidence is None
                or left_evidence.start is None
                or left_evidence.end is None
                or right_evidence.start is None
                or right_evidence.end is None
                or left_evidence.end > right_evidence.start
            ):
                continue
            between = source_text[left_evidence.end : right_evidence.start]
            if between.strip():
                continue
            left_phrase = source_text[left_evidence.start : left_evidence.end]
            right_phrase = source_text[right_evidence.start : right_evidence.end]
            left_binder, left_nominal = self._phrase_profile(left_phrase)
            _right_binder, right_nominal = self._phrase_profile(right_phrase)
            if not left_binder or left_nominal or not right_nominal:
                continue

            start = int(left_evidence.start)
            end = int(right_evidence.end)
            phrase = source_text[start:end]
            role = (
                right.role
                if left.role in weak_fragment_roles
                and right.role not in weak_fragment_roles
                else left.role
            )
            replacements[left_index] = replace(
                left,
                role=role,
                mention=phrase,
                normalized_hint=None,
                evidence=type(left_evidence)(phrase, start, end),
                nominal_relations=right.nominal_relations,
                grammatical_number=right.grammatical_number,
            )
            consumed.add(right_index)

        if not consumed and not replacements:
            return assertion
        fused = tuple(
            replacements.get(index, actant)
            for index, actant in enumerate(actants)
            if index not in consumed
        )
        predicate = assertion.predicate
        proposed = predicate.template_candidate
        if proposed is not None:
            fused_roles = {item.role for item in fused}
            ordered_roles = tuple(
                dict.fromkeys(
                    (
                        *(role for role in proposed.roles if role in fused_roles),
                        *(item.role for item in fused),
                    )
                )
            )
            predicate = replace(
                predicate,
                template_candidate=type(proposed)(ordered_roles),
            )
        return replace(assertion, predicate=predicate, actants=fused)

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
        if (
            kind in {QuantifierKind.NOT_EXISTS, QuantifierKind.NOT_FORALL}
            and self._independent_negative_scope_conflict(
                result.source_text,
                assertion.predicate,
                phrase,
                predicate_negated=assertion.negated,
            )
        ):
            raise QuantifierFormalizationError(
                "Negative binder and predicate body contain independent source "
                f"negation sites for {phrase!r}; relative scope is unresolved"
            )

        phrase_tokens = tuple(self._fold(token) for token in self._tokens(phrase))
        if (
            kind is QuantifierKind.NOT_FORALL
            and not any(token in self._NEGATION_PARTICLES for token in phrase_tokens)
            and self._predicate_has_local_negation(
                result.source_text, assertion.predicate
            )
        ):
            # The only visible negation site is immediately before the event
            # predicate, hence it belongs to the body: FORALL(x, NOT(P(x))).
            kind = QuantifierKind.FORALL
        if (
            kind is QuantifierKind.NOT_FORALL
            and "ни" in phrase_tokens
            and any(
                item.pos == "NUMR" or "Anum" in item.grammemes
                for token in self._tokens(phrase)
                for item in material_analyses(self._analyses(token))
            )
        ):
            # A negative cardinal binder denies existence of a witness; it does
            # not deny an every-member proposition.
            kind = QuantifierKind.NOT_EXISTS

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
        assertion = self._fuse_split_nominal_binders(
            result.source_text, assertion
        )
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
