from __future__ import annotations

from dataclasses import replace
import re

from ah.agent.interaction_context import InteractionContext
from ah.model import ActantRole

from .association_semantics import AssociationProbeError, AssociationSemanticClassifier
from .contracts import (
    ActantCandidate,
    ActantCompositionCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
)
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import PerceptionAttemptDiagnostic, PerceptionParseError


class AssociationContinuationQueryCandidate(QueryCandidate):
    """Typed discourse query that reuses the active association endpoints."""


_CORRELATIVE_COORDINATORS: dict[str, CompositionOperator] = {
    "и": CompositionOperator.AND,
    "или": CompositionOperator.OR,
    "либо": CompositionOperator.OR,
}
_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


def _last_word(text: str) -> str | None:
    matches = tuple(_WORD_RE.finditer(text))
    return matches[-1].group(0).casefold() if matches else None


def _only_word(text: str) -> str | None:
    words = tuple(match.group(0).casefold() for match in _WORD_RE.finditer(text))
    return words[0] if len(words) == 1 else None


def _simple_composition_member(actant: ActantCandidate) -> bool:
    """Only merge source-grounded plain actants; never erase richer structure."""
    return (
        actant.composition is None
        and actant.candidate_ref is None
        and actant.entity_ref is None
        and actant.proposition is None
        and actant.quantifier is None
        and not actant.nominal_relations
        and actant.evidence is not None
        and actant.evidence.start is not None
        and actant.evidence.end is not None
        and bool((actant.mention or actant.lookup_text or actant.evidence.text).strip())
    )


def _merge_role(actants: tuple[ActantCandidate, ...]) -> ActantRole | None:
    """Choose the semantic role shared by a correlative coordination.

    The recurrent parser failure this repairs is one correctly typed member plus
    later members demoted to AUXILLIARY. If two genuinely different non-auxiliary
    roles are present, the source is not safe to rewrite and remains untouched.
    """
    non_aux = {item.role for item in actants if item.role is not ActantRole.AUXILLIARY}
    if len(non_aux) == 1:
        return next(iter(non_aux))
    if not non_aux and actants:
        return ActantRole.AUXILLIARY
    return None


def _composition_member(actant: ActantCandidate) -> CompositionMemberCandidate:
    mention = (actant.mention or actant.lookup_text or actant.evidence.text).strip()  # type: ignore[union-attr]
    return CompositionMemberCandidate(
        mention=mention,
        normalized_hint=actant.normalized_hint,
        semantic_hint=actant.semantic_hint,
        evidence=actant.evidence,
    )


def _repair_root_correlative_coordination(source_text: str, root):
    """Recover source-explicit ``и A, и B`` / ``либо A, либо B`` compositions.

    LinguisticCandidateBuilder already handles ordinary ``A и B``. The repeated
    coordinator form was falling through because the second coordinator is preceded
    by a comma, so the second nominal was independently role-classified and often
    became AUXILLIARY. This repair uses only evidence offsets and the repeated
    source coordinator; it makes no lexical/ontological decision about the nouns.
    """
    candidates = [item for item in root.actants if _simple_composition_member(item)]
    if len(candidates) < 2:
        return root
    ordered = sorted(candidates, key=lambda item: (item.evidence.start, item.evidence.end))  # type: ignore[union-attr]
    used: set[int] = set()
    replacements: list[tuple[set[int], ActantCandidate]] = []

    for index, first in enumerate(ordered):
        if id(first) in used:
            continue
        first_start = first.evidence.start  # type: ignore[union-attr]
        prefix_word = _last_word(source_text[:first_start])
        operator = _CORRELATIVE_COORDINATORS.get(prefix_word or "")
        if operator is None:
            continue

        group = [first]
        previous = first
        for following in ordered[index + 1 :]:
            if id(following) in used:
                continue
            previous_end = previous.evidence.end  # type: ignore[union-attr]
            following_start = following.evidence.start  # type: ignore[union-attr]
            if following_start < previous_end:
                continue
            between_word = _only_word(source_text[previous_end:following_start])
            if _CORRELATIVE_COORDINATORS.get(between_word or "") is not operator:
                break
            tentative = tuple((*group, following))
            if _merge_role(tentative) is None:
                break
            group.append(following)
            previous = following

        if len(group) < 2:
            continue
        role = _merge_role(tuple(group))
        if role is None:
            continue
        start = group[0].evidence.start  # type: ignore[union-attr]
        end = group[-1].evidence.end  # type: ignore[union-attr]
        surface = source_text[start:end]
        confidence_values = [item.parser_confidence for item in group if item.parser_confidence is not None]
        merged = ActantCandidate(
            role=role,
            mention=surface,
            semantic_hint=group[0].semantic_hint,
            evidence=EvidenceSpan(surface, start, end),
            parser_confidence=(min(confidence_values) if confidence_values else None),
            composition=ActantCompositionCandidate(
                operator=operator,
                members=tuple(_composition_member(item) for item in group),
            ),
        )
        member_ids = {id(item) for item in group}
        used.update(member_ids)
        replacements.append((member_ids, merged))

    if not replacements:
        return root

    replacement_by_member: dict[int, tuple[set[int], ActantCandidate]] = {}
    for member_ids, merged in replacements:
        for member_id in member_ids:
            replacement_by_member[member_id] = (member_ids, merged)

    rewritten: list[ActantCandidate] = []
    emitted: set[int] = set()
    for actant in root.actants:
        replacement = replacement_by_member.get(id(actant))
        if replacement is None:
            rewritten.append(actant)
            continue
        member_ids, merged = replacement
        key = id(merged)
        if key not in emitted:
            rewritten.append(merged)
            emitted.add(key)
        used.update(member_ids)
    return replace(root, actants=tuple(rewritten))


def normalize_correlative_actant_compositions(result: PerceptionResult) -> PerceptionResult:
    assertions = tuple(
        _repair_root_correlative_coordination(result.source_text, item)
        for item in result.assertions
    )
    queries = tuple(
        _repair_root_correlative_coordination(result.source_text, item)
        for item in result.queries
    )
    commands = tuple(
        _repair_root_correlative_coordination(result.source_text, item)
        for item in result.commands
    )
    if (
        assertions == result.assertions
        and queries == result.queries
        and commands == result.commands
    ):
        return result
    return replace(
        result,
        assertions=assertions,
        queries=queries,
        commands=commands,
        diagnostics=tuple((*result.diagnostics, "CORRELATIVE_ACTANT_COMPOSITION_NORMALIZED")),
    )
