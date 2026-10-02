from __future__ import annotations

from dataclasses import replace
import re

from ah.model import ActantRole

from .adaptive_parser import AdaptiveParseError, AdaptiveSettings
from .association_continuation import AssociationContinuationLLMPerceptionService
from .association_semantics import (
    AssociationEndpointSelector,
    AssociationQueryDecision,
    AssociationSemanticClassifier,
)
from .contracts import (
    ActantCandidate,
    ActantCompositionCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    PerceptionResult,
    QueryCandidate,
)
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import PerceptionParseError
from .morphology import build_morphology, material_analyses
from .semantic_predicates import SemanticPredicateAdaptiveParser


_COORDINATOR_RE = re.compile(r"^\s*,?\s*(и|или|либо)\s*$", flags=re.IGNORECASE | re.UNICODE)
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)
_NOMINAL_POS = {"NOUN", "NPRO"}


def _plain_source_actant(item: ActantCandidate) -> bool:
    return (
        item.composition is None
        and item.candidate_ref is None
        and item.entity_ref is None
        and item.proposition is None
        and item.quantifier is None
        and item.evidence is not None
        and item.evidence.start is not None
        and item.evidence.end is not None
    )


def _head_word(item: ActantCandidate) -> str | None:
    source = ""
    if item.evidence is not None:
        source = item.evidence.text
    if not source:
        source = item.mention or item.lookup_text or ""
    words = tuple(match.group(0) for match in _WORD_RE.finditer(source))
    return words[-1] if words else None


def _nominal_profile(morphology, item: ActantCandidate):
    word = _head_word(item)
    if not word:
        return None
    try:
        analyses = material_analyses(tuple(morphology.analyze_all(word)))
    except (AttributeError, TypeError):
        single = morphology.analyze(word)
        analyses = () if single is None else (single,)
    nominal = tuple(info for info in analyses if info.pos in _NOMINAL_POS)
    if not nominal:
        return None
    numbers = frozenset(info.number for info in nominal if info.number)
    cases = frozenset(info.case for info in nominal if info.case)
    return numbers, cases


def _compatible_nominals(morphology, left: ActantCandidate, right: ActantCandidate) -> bool:
    lp = _nominal_profile(morphology, left)
    rp = _nominal_profile(morphology, right)
    if lp is None or rp is None:
        return False
    left_numbers, left_cases = lp
    right_numbers, right_cases = rp
    if left_numbers and right_numbers and left_numbers.isdisjoint(right_numbers):
        return False
    # Russian animate accusative is commonly represented by a genitive-shaped
    # reading.  Exact case agreement is therefore supporting evidence, not a hard
    # requirement once one member is already a validated OBJECT and the other is a
    # suspicious AMOUNT/AUXILIARY demotion.
    if left_cases and right_cases and not left_cases.isdisjoint(right_cases):
        return True
    return True


def _merged_role(left: ActantCandidate, right: ActantCandidate) -> ActantRole | None:
    if left.role is right.role:
        return left.role
    if left.role is ActantRole.AUXILLIARY:
        return right.role
    if right.role is ActantRole.AUXILLIARY:
        return left.role
    if {left.role, right.role} == {ActantRole.OBJECT, ActantRole.AMOUNT}:
        return ActantRole.OBJECT
    return None


def _member(item: ActantCandidate) -> CompositionMemberCandidate:
    mention = (item.mention or item.lookup_text or item.evidence.text).strip()  # type: ignore[union-attr]
    return CompositionMemberCandidate(
        mention=mention,
        normalized_hint=item.normalized_hint,
        semantic_hint=item.semantic_hint,
        evidence=item.evidence,
    )


def _repair_plain_coordination(source_text: str, root, morphology):
    """Recover A-and-B when one member received a spurious fallback role.

    The repair is deliberately narrow: two adjacent source-grounded nominal
    actants must be connected by exactly one overt coordinator. Equal roles merge
    directly; otherwise only AUXILIARY demotion or a non-numeric OBJECT/AMOUNT split
    is repairable. This fixes frames such as ``делают деревянных ворон и столы``
    without turning unrelated complements around ``и`` into one group.
    """
    candidates = [item for item in root.actants if _plain_source_actant(item)]
    if len(candidates) < 2:
        return root
    ordered = sorted(candidates, key=lambda item: (item.evidence.start, item.evidence.end))  # type: ignore[union-attr]
    replacement_by_id: dict[int, ActantCandidate] = {}
    consumed: set[int] = set()

    for left, right in zip(ordered, ordered[1:]):
        if id(left) in consumed or id(right) in consumed:
            continue
        left_end = left.evidence.end  # type: ignore[union-attr]
        right_start = right.evidence.start  # type: ignore[union-attr]
        if right_start < left_end:
            continue
        match = _COORDINATOR_RE.fullmatch(source_text[left_end:right_start])
        if match is None:
            continue
        operator = CompositionOperator.AND if match.group(1).casefold() == "и" else CompositionOperator.OR
        role = _merged_role(left, right)
        if role is None or not _compatible_nominals(morphology, left, right):
            continue
        if role is ActantRole.OBJECT and {left.role, right.role} == {ActantRole.OBJECT, ActantRole.AMOUNT}:
            # A real numeric measure must remain AMOUNT rather than being swallowed
            # by nominal coordination repair.
            surfaces = " ".join(
                (item.evidence.text if item.evidence is not None else item.mention or "")
                for item in (left, right)
            )
            if re.search(r"\d", surfaces):
                continue

        start = left.evidence.start  # type: ignore[union-attr]
        end = right.evidence.end  # type: ignore[union-attr]
        surface = source_text[start:end]
        confidence = [
            item.parser_confidence for item in (left, right)
            if item.parser_confidence is not None
        ]
        merged = ActantCandidate(
            role=role,
            mention=surface,
            evidence=replace(left.evidence, text=surface, start=start, end=end),  # type: ignore[arg-type]
            parser_confidence=min(confidence) if confidence else None,
            composition=ActantCompositionCandidate(
                operator=operator,
                members=(_member(left), _member(right)),
            ),
            # Preserve modifier evidence instead of silently dropping attributes
            # such as ``деревянных`` when the left coordinated member owns them.
            nominal_relations=tuple((*left.nominal_relations, *right.nominal_relations)),
        )
        replacement_by_id[id(left)] = merged
        replacement_by_id[id(right)] = merged
        consumed.update({id(left), id(right)})

    if not replacement_by_id:
        return root
    emitted: set[int] = set()
    rewritten: list[ActantCandidate] = []
    for item in root.actants:
        merged = replacement_by_id.get(id(item))
        if merged is None:
            rewritten.append(item)
            continue
        key = id(merged)
        if key not in emitted:
            rewritten.append(merged)
            emitted.add(key)
    return replace(root, actants=tuple(rewritten))


def normalize_plain_actant_compositions(
    result: PerceptionResult,
    morphology,
) -> PerceptionResult:
    assertions = tuple(_repair_plain_coordination(result.source_text, item, morphology) for item in result.assertions)
    queries = tuple(_repair_plain_coordination(result.source_text, item, morphology) for item in result.queries)
    commands = tuple(_repair_plain_coordination(result.source_text, item, morphology) for item in result.commands)
    if assertions == result.assertions and queries == result.queries and commands == result.commands:
        return result
    return replace(
        result,
        assertions=assertions,
        queries=queries,
        commands=commands,
        diagnostics=tuple((*result.diagnostics, "PLAIN_ACTANT_COMPOSITION_NORMALIZED")),
    )


class CoordinationAwareLLMPerceptionService(AssociationContinuationLLMPerceptionService):
    """Final production perception adapter for coordination and association intent."""

    def _coordination_morphology(self):
        morphology = getattr(self, "_coordination_morphology_cache", None)
        if morphology is None:
            morphology = build_morphology(self.settings.morphology_backend)
            self._coordination_morphology_cache = morphology
        return morphology

    def classify_association_query(self, source_text: str, act: QueryCandidate):
        endpoints = AssociationSemanticClassifier.endpoint_candidates(act.actants)
        if len(endpoints) != 2:
            return super().classify_association_query(source_text, act)

        semantic_reranker = (
            EmbeddingSemanticReranker(self.backend)  # type: ignore[arg-type]
            if self.settings.embedding_model.strip()
            and callable(getattr(self.backend, "embed_texts", None))
            else None
        )
        parser = SemanticPredicateAdaptiveParser(
            self.backend,
            AdaptiveSettings(
                prompt_dir=self.settings.probe_prompt_dir,
                generation=self.settings.generation,
                retry_attempts=self.settings.probe_retry_attempts,
                max_actants_per_act=self.settings.max_actants_per_act,
                predicate_symbol_language=self.settings.predicate_symbol_language,
                morphology_backend=self.settings.morphology_backend,
                verify_predicate_symbol=(self.settings.protocol == "adaptive_v3"),
            ),
            semantic_reranker=semantic_reranker,
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PARSED PREDICATE:\n{act.predicate.surface}\n"
            "TWO EXPLICIT ENDPOINTS:\n"
            f"E1={endpoints[0].text}\nE2={endpoints[1].text}\n"
            "Decide the discourse operation only. ASSOCIATION means the requested "
            "answer is some shared property, shared event/context, semantic bridge, "
            "or memory path applying to both E1 and E2. ORDINARY means the utterance "
            "asks the truth/value of the parsed predicate itself. The existing "
            "copular parse is only syntax and must not decide this choice."
        )
        try:
            choice, _ = parser._deep_semantic_choice_probe(
                "association_query",
                prompt,
                ("ASSOCIATION", "ORDINARY", "UNCLEAR"),
            )
        except AdaptiveParseError as exc:
            raise PerceptionParseError(str(exc)) from exc
        if choice == "ASSOCIATION":
            return AssociationQueryDecision(endpoints[0].selector, endpoints[1].selector)
        return None

    def parse(self, text: str, interaction_context):
        result = super().parse(text, interaction_context)
        return normalize_plain_actant_compositions(
            result,
            self._coordination_morphology(),
        )
