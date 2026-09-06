from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Mapping

from ah.model import ActantRole

from .contracts import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PredicateCandidate,
    SituationRelationCandidate,
    SituationRelationHintCandidate,
    SituationRelationHintKind,
    TemplateCandidate,
)
from .linguistic_candidates import (
    FrameDependencyKind,
    LinguisticCandidateGraph,
    SourceToken,
)
from .morphology import MorphInfo, Morphology, material_analyses, stable_normal_form


@dataclass(frozen=True, slots=True)
class EventNormalizationOutcome:
    assertions: tuple[AssertionCandidate, ...]
    relations: tuple[SituationRelationCandidate, ...]
    relation_hints: tuple[SituationRelationHintCandidate, ...]
    diagnostics: tuple[str, ...] = ()


class EventNormalizer:
    """Deterministic event/state normalization over an already parsed frame graph.

    The normalizer never reads AH and never assigns canonical UIDs.  Its job is to
    preserve event structure that surface predicate nesting tends to hide:

    * detached gerunds remain independently asserted situations instead of being
      silently demoted to proposition-valued HOW_TO/OBJECT content;
    * a *perfective, preposed* gerund can establish source-order FOLLOW, while an
      imperfective gerund is kept independent without inventing temporal order;
    * coordinated perfective predicates can establish a conservative FOLLOW edge;
    * a passive full participle used inside an asserted subject NP can expose a
      result STATE without inventing the event or agent that produced that state;
    * weaker narrative adjacency is emitted only as a runtime hint and is never a
      canonical CAUSE/FOLLOW link.

    This layer is intentionally conservative.  It does not infer a causal edge from
    mere textual succession and it does not turn every adjective/participle into an
    event.
    """

    def __init__(self, graph: LinguisticCandidateGraph, morphology: Morphology) -> None:
        self.graph = graph
        self.morphology = morphology

    @staticmethod
    def _word(token: SourceToken) -> bool:
        return re.search(r"\w", token.text, flags=re.UNICODE) is not None

    @staticmethod
    def _material(token: SourceToken) -> tuple[MorphInfo, ...]:
        return material_analyses(token.analyses)

    @classmethod
    def _has_pos(cls, token: SourceToken, pos: str) -> bool:
        return any(item.pos == pos for item in cls._material(token))

    @classmethod
    def _has_grammeme(cls, token: SourceToken, value: str) -> bool:
        return any(value in item.grammemes for item in cls._material(token))

    @classmethod
    def _aspect(cls, token: SourceToken) -> str | None:
        values = {
            value
            for item in cls._material(token)
            for value in ("perf", "impf")
            if value in item.grammemes
        }
        return next(iter(values)) if len(values) == 1 else None

    def _token_for_predicate(self, assertion: AssertionCandidate) -> SourceToken | None:
        evidence = assertion.predicate.evidence
        if evidence is None or evidence.start is None or evidence.end is None:
            return None
        exact = [
            token for token in self.graph.tokens
            if token.start == evidence.start and token.end == evidence.end
        ]
        if len(exact) == 1:
            return exact[0]
        inside = [
            token for token in self.graph.tokens
            if evidence.start <= token.start and token.end <= evidence.end and self._word(token)
        ]
        predicate_positions = {item.token_index for item in self.graph.predicates}
        candidates = [token for token in inside if token.index in predicate_positions]
        return candidates[0] if len(candidates) == 1 else None

    def _assertion_by_head(
        self, assertions: tuple[AssertionCandidate, ...]
    ) -> dict[int, list[AssertionCandidate]]:
        result: dict[int, list[AssertionCandidate]] = {}
        for assertion in assertions:
            token = self._token_for_predicate(assertion)
            if token is not None:
                result.setdefault(token.index, []).append(assertion)
        return result

    def _comma_between(self, left: int, right: int) -> bool:
        lo, hi = sorted((left, right))
        return any(
            token.text == "," for token in self.graph.tokens
            if lo < token.index < hi
        )

    @staticmethod
    def _relation_key(item: SituationRelationCandidate) -> tuple[str, str, str]:
        return (item.canonical_relation_id, item.source_ref, item.target_ref)

    @staticmethod
    def _hint_key(item: SituationRelationHintCandidate) -> tuple[str, str, str]:
        return (item.kind.value, item.source_ref, item.target_ref)

    @staticmethod
    def _actant_identity(actant: ActantCandidate) -> tuple[str, str] | None:
        if actant.entity_ref:
            return ("entity", actant.entity_ref)
        text = (actant.normalized_hint or actant.mention or "").strip().casefold().replace("ё", "е")
        if text:
            return ("text", text)
        return None

    @classmethod
    def _share_participant(cls, left: AssertionCandidate, right: AssertionCandidate) -> bool:
        left_ids = {
            identity
            for actant in left.actants
            if actant.role in {ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT}
            if (identity := cls._actant_identity(actant)) is not None
        }
        right_ids = {
            identity
            for actant in right.actants
            if actant.role in {ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT}
            if (identity := cls._actant_identity(actant)) is not None
        }
        return bool(left_ids & right_ids)

    def _evidence_between(self, source: AssertionCandidate, target: AssertionCandidate) -> EvidenceSpan | None:
        left = source.evidence or source.predicate.evidence
        right = target.evidence or target.predicate.evidence
        if (
            left is None or right is None
            or left.start is None or left.end is None
            or right.start is None or right.end is None
        ):
            return None
        start = min(left.end, right.end)
        end = max(left.start, right.start)
        if end <= start:
            return None
        return EvidenceSpan(self.graph.text[start:end], start, end)

    def _normalize_detached_nonfinite(
        self,
        assertions: list[AssertionCandidate],
        relations: list[SituationRelationCandidate],
        hints: list[SituationRelationHintCandidate],
        diagnostics: list[str],
    ) -> None:
        by_id = {item.local_id: item for item in assertions}
        by_head = self._assertion_by_head(tuple(assertions))
        relation_keys = {self._relation_key(item) for item in relations}
        hint_keys = {self._hint_key(item) for item in hints}

        for dependency in self.graph.frame_graph.dependencies:
            if dependency.kind is not FrameDependencyKind.NONFINITE:
                continue
            parents = by_head.get(dependency.parent_token_index, ())
            children = by_head.get(dependency.child_token_index, ())
            if len(parents) != 1 or len(children) != 1:
                continue
            parent = by_id.get(parents[0].local_id, parents[0])
            child = by_id.get(children[0].local_id, children[0])
            child_token = self.graph.token(dependency.child_token_index)
            if not self._has_pos(child_token, "GRND"):
                continue
            if (
                parent.status is not AssertionStatus.ASSERTED
                or child.status not in {AssertionStatus.ASSERTED, AssertionStatus.EMBEDDED}
                or parent.quoted
                or child.quoted
                or not self._comma_between(dependency.parent_token_index, dependency.child_token_index)
            ):
                continue

            # A detached gerund is narrator-provided event content.  If generic frame
            # nesting temporarily attached it as HOW_TO/OBJECT/PURPOSE, remove that
            # proposition-valued embedding.  An already chosen CAUSE role is stronger
            # semantic evidence and becomes an ordinary CAUSE relation instead.
            removed_roles: list[ActantRole] = []
            kept: list[ActantCandidate] = []
            for actant in parent.actants:
                if actant.candidate_ref == child.local_id and actant.role in {
                    ActantRole.OBJECT,
                    ActantRole.PURPOSE,
                    ActantRole.HOW_TO,
                    ActantRole.CAUSE,
                    ActantRole.TIME,
                }:
                    removed_roles.append(actant.role)
                    if actant.role is ActantRole.CAUSE:
                        key = ("CAUSE", child.local_id, parent.local_id)
                        if key not in relation_keys:
                            relations.append(
                                SituationRelationCandidate(
                                    "CAUSE", child.local_id, parent.local_id, child.evidence
                                )
                            )
                            relation_keys.add(key)
                    continue
                kept.append(actant)
            if removed_roles:
                parent = replace(parent, actants=tuple(kept))
                by_id[parent.local_id] = parent
            if child.status is AssertionStatus.EMBEDDED:
                child = replace(child, status=AssertionStatus.ASSERTED)
                by_id[child.local_id] = child

            child_before_parent = dependency.child_token_index < dependency.parent_token_index
            aspect = self._aspect(child_token)
            if child_before_parent and aspect == "perf":
                key = ("FOLLOW", child.local_id, parent.local_id)
                if key not in relation_keys:
                    relations.append(
                        SituationRelationCandidate(
                            "FOLLOW", child.local_id, parent.local_id, child.evidence
                        )
                    )
                    relation_keys.add(key)
                diagnostics.append(
                    f"event-normalizer: detached perfective gerund {child.local_id} FOLLOW {parent.local_id}"
                )
            else:
                kind = (
                    SituationRelationHintKind.SIMULTANEOUS_CANDIDATE
                    if aspect == "impf"
                    else SituationRelationHintKind.TEMPORAL_CANDIDATE
                )
                key = (kind.value, child.local_id, parent.local_id)
                if key not in hint_keys:
                    hints.append(
                        SituationRelationHintCandidate(
                            kind,
                            child.local_id,
                            parent.local_id,
                            evidence=child.evidence,
                            reason="detached non-finite event without safe directional temporal entailment",
                        )
                    )
                    hint_keys.add(key)

        assertions[:] = [by_id.get(item.local_id, item) for item in assertions]

    def _normalize_perfective_coordination(
        self,
        assertions: list[AssertionCandidate],
        relations: list[SituationRelationCandidate],
        hints: list[SituationRelationHintCandidate],
        diagnostics: list[str],
    ) -> None:
        by_head = self._assertion_by_head(tuple(assertions))
        relation_keys = {self._relation_key(item) for item in relations}
        hint_keys = {self._hint_key(item) for item in hints}
        for group in self.graph.frame_graph.coordinations:
            members: list[AssertionCandidate] = []
            valid = True
            for head in group.member_token_indices:
                candidates = by_head.get(head, ())
                if len(candidates) != 1:
                    valid = False
                    break
                members.append(candidates[0])
            if not valid:
                continue
            for left, right, left_head, right_head in zip(
                members, members[1:], group.member_token_indices, group.member_token_indices[1:]
            ):
                if (
                    left.status is not AssertionStatus.ASSERTED
                    or right.status is not AssertionStatus.ASSERTED
                    or left.quoted or right.quoted or left.negated or right.negated
                ):
                    continue
                left_token = self.graph.token(left_head)
                right_token = self.graph.token(right_head)
                if self._aspect(left_token) != "perf" or self._aspect(right_token) != "perf":
                    continue
                key = ("FOLLOW", left.local_id, right.local_id)
                if key not in relation_keys:
                    relations.append(
                        SituationRelationCandidate(
                            "FOLLOW",
                            left.local_id,
                            right.local_id,
                            self._evidence_between(left, right),
                        )
                    )
                    relation_keys.add(key)
                    diagnostics.append(
                        f"event-normalizer: coordinated perfective events {left.local_id} FOLLOW {right.local_id}"
                    )
                if self._share_participant(left, right):
                    hint_key = (
                        SituationRelationHintKind.CAUSAL_CANDIDATE.value,
                        left.local_id,
                        right.local_id,
                    )
                    if hint_key not in hint_keys:
                        hints.append(
                            SituationRelationHintCandidate(
                                SituationRelationHintKind.CAUSAL_CANDIDATE,
                                left.local_id,
                                right.local_id,
                                self._evidence_between(left, right),
                                reason="ordered perfective events share a participant; causality is not asserted",
                            )
                        )
                        hint_keys.add(hint_key)

    def _normalize_serial_perfective_events(
        self,
        assertions: list[AssertionCandidate],
        relations: list[SituationRelationCandidate],
        hints: list[SituationRelationHintCandidate],
        diagnostics: list[str],
    ) -> None:
        """Recover source-order FOLLOW outside explicit predicate groups.

        The linguistic frame graph deliberately keeps conservative clause
        boundaries.  Literary coordination can therefore put two finite events in
        separate sibling clauses (``узнала знак и закрыла глаза``), or insert a
        detached gerund between conjuncts (``снял чехол, подняв пыль, и поставил
        лампу``).  Those cases need not appear in ``frame_graph.coordinations`` even
        though their temporal order is written explicitly.

        Add FOLLOW only for consecutive asserted *finite perfective* source events
        inside one top-level sentence when either (a) an explicit additive
        coordinator lies between them, or (b) a comma-separated serial chain keeps
        exactly the same SUBJECT identity.  Adversative/disjunctive coordinators and
        subordinate/relative clauses are excluded.  The rule establishes narration
        order only; CAUSE remains a runtime candidate and still requires the later
        semantic promotion gate.
        """
        rows: list[tuple[int, AssertionCandidate, SourceToken, object]] = []
        for assertion in assertions:
            if (
                assertion.status is not AssertionStatus.ASSERTED
                or assertion.quoted
                or assertion.negated
            ):
                continue
            token = self._token_for_predicate(assertion)
            if token is None or not self._has_pos(token, "VERB") or self._aspect(token) != "perf":
                continue
            clause = self.graph.clause_for_token(token.index)
            if (
                clause is None
                or clause.parent_clause_id is not None
                or clause.relative
                or clause.quoted
                or clause.implicit_copula
            ):
                continue
            rows.append((token.index, assertion, token, clause))
        rows.sort(key=lambda item: item[0])

        relation_keys = {self._relation_key(item) for item in relations}
        hint_keys = {self._hint_key(item) for item in hints}

        def subject_identity(item: AssertionCandidate) -> tuple[str, str] | None:
            subjects = [a for a in item.actants if a.role is ActantRole.SUBJECT]
            if len(subjects) != 1:
                return None
            return self._actant_identity(subjects[0])

        for left_row, right_row in zip(rows, rows[1:]):
            left_index, left, _left_token, left_clause = left_row
            right_index, right, _right_token, right_clause = right_row
            if left_clause.sentence_id != right_clause.sentence_id:
                continue
            # An already materialized relation owns the pair.  In particular do not
            # add FOLLOW on top of an explicit CAUSE/FOLLOW with opposite meaning.
            if any(
                (rel.source_ref, rel.target_ref) in {
                    (left.local_id, right.local_id),
                    (right.local_id, left.local_id),
                }
                for rel in relations
            ):
                continue

            between = [
                token for token in self.graph.tokens
                if left_index < token.index < right_index
            ]
            words = {token.text.casefold() for token in between}
            if words & {"но", "однако", "а", "или", "либо"}:
                continue
            if any(token.text == ";" for token in between):
                continue
            explicit_additive = bool(words & {"и", "да"})
            comma_serial = any(token.text == "," for token in between)
            same_subject = (
                subject_identity(left) is not None
                and subject_identity(left) == subject_identity(right)
            )
            if not explicit_additive and not (comma_serial and same_subject):
                continue

            key = ("FOLLOW", left.local_id, right.local_id)
            if key not in relation_keys:
                relations.append(
                    SituationRelationCandidate(
                        "FOLLOW",
                        left.local_id,
                        right.local_id,
                        self._evidence_between(left, right),
                    )
                )
                relation_keys.add(key)
                diagnostics.append(
                    "event-normalizer: serial perfective events "
                    f"{left.local_id} FOLLOW {right.local_id}"
                )

            # FOLLOW is temporal structure only.  Expose a causal hypothesis when
            # there is already participant continuity, as before, or when the target
            # subject is a passive-participle result description.  The latter is a
            # common literary re-mention pattern (``ударил его, оглушенный матрос
            # упал``) where local entity identity may still be split.  The hint is
            # non-canonical; AdaptivePerceptionParser still requires source entailment
            # before any CAUSE becomes L.
            def passive_result_subject(item: AssertionCandidate) -> bool:
                subjects = [a for a in item.actants if a.role is ActantRole.SUBJECT]
                if len(subjects) != 1:
                    return False
                evidence = subjects[0].evidence
                if evidence is None or evidence.start is None or evidence.end is None:
                    return False
                return any(
                    any(info.pos == "PRTF" for info in material_analyses(token.analyses))
                    for token in self.graph.tokens
                    if token.start >= evidence.start and token.end <= evidence.end
                )

            causal_shape = self._share_participant(left, right) or passive_result_subject(right)
            if causal_shape:
                hint_key = (
                    SituationRelationHintKind.CAUSAL_CANDIDATE.value,
                    left.local_id,
                    right.local_id,
                )
                if hint_key not in hint_keys:
                    reason = (
                        "serial perfective passive-result subject; source order does not "
                        "by itself entail causality"
                        if passive_result_subject(right) and not self._share_participant(left, right)
                        else
                        "serial perfective events share a participant; source order does not "
                        "by itself entail causality"
                    )
                    hints.append(
                        SituationRelationHintCandidate(
                            SituationRelationHintKind.CAUSAL_CANDIDATE,
                            left.local_id,
                            right.local_id,
                            self._evidence_between(left, right),
                            reason=reason,
                        )
                    )
                    hint_keys.add(hint_key)

    def _result_state_assertions(
        self,
        assertions: list[AssertionCandidate],
        diagnostics: list[str],
    ) -> None:
        additions: list[AssertionCandidate] = []
        existing = {
            (
                item.predicate.lookup_form.casefold(),
                tuple((a.role.value, (a.normalized_hint or a.mention or "").casefold()) for a in item.actants),
            )
            for item in assertions
        }
        next_id = 1
        numeric_ids = [
            int(match.group(1))
            for item in assertions
            if (match := re.fullmatch(r"A(\d+)", item.local_id))
        ]
        if numeric_ids:
            next_id = max(numeric_ids) + 1

        for source in tuple(assertions):
            if source.status is not AssertionStatus.ASSERTED or source.quoted:
                continue
            subject = next((item for item in source.actants if item.role is ActantRole.SUBJECT), None)
            if subject is None or subject.evidence is None or subject.evidence.start is None or subject.evidence.end is None:
                continue
            span_tokens = [
                token for token in self.graph.tokens
                if subject.evidence.start <= token.start and token.end <= subject.evidence.end and self._word(token)
            ]
            if len(span_tokens) < 2:
                continue
            # Only explicit passive full participles are safe result-state evidence.
            participles = [
                token for token in span_tokens
                if any(
                    item.pos == "PRTF" and "pssv" in item.grammemes
                    for item in self._material(token)
                )
            ]
            if len(participles) != 1:
                continue
            participle = participles[0]
            following_nouns = [
                token for token in span_tokens
                if token.index > participle.index and any(
                    item.pos in {"NOUN", "NPRO"} for item in self._material(token)
                )
            ]
            if not following_nouns:
                continue
            head = following_nouns[0]
            head_lemma = stable_normal_form(head.analyses, poses={"NOUN", "NPRO"}) or head.text
            state_surface = participle.text.casefold()
            signature = (
                "быть",
                (
                    (ActantRole.SUBJECT.value, head_lemma.casefold()),
                    (ActantRole.STATE.value, state_surface),
                ),
            )
            if signature in existing:
                continue
            synthetic_subject = ActantCandidate(
                ActantRole.SUBJECT,
                mention=head.text,
                normalized_hint=head_lemma,
                entity_ref=subject.entity_ref,
                # Keep the exact source NP span so the normal source-coreference
                # binder can identify this state subject with the matrix subject.
                evidence=subject.evidence,
            )
            state = ActantCandidate(
                ActantRole.STATE,
                mention=participle.text,
                normalized_hint=state_surface,
                semantic_hint=(
                    "RESULT_STATE_FROM_PARTICIPLE:"
                    + (stable_normal_form(participle.analyses, poses={"PRTF"}) or participle.text)
                ),
                evidence=EvidenceSpan(
                    participle.text, participle.start, participle.end
                ),
            )
            local_id = f"A{next_id}"
            next_id += 1
            evidence = source.evidence or subject.evidence
            additions.append(
                AssertionCandidate(
                    local_id=local_id,
                    predicate=PredicateCandidate(
                        surface="быть",
                        normalized_hint="быть",
                        sense_hint="RESULT_STATE",
                        evidence=None,
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
                    ),
                    actants=(synthetic_subject, state),
                    evidence=evidence,
                    status=AssertionStatus.ASSERTED,
                )
            )
            existing.add(signature)
            diagnostics.append(
                f"event-normalizer: passive participle state {local_id} from {source.local_id}"
            )
        assertions.extend(additions)

    def _narrative_adjacency_hints(
        self,
        assertions: list[AssertionCandidate],
        relations: list[SituationRelationCandidate],
        hints: list[SituationRelationHintCandidate],
    ) -> None:
        relation_pairs = {
            (item.source_ref, item.target_ref) for item in relations
        } | {
            (item.target_ref, item.source_ref) for item in relations
        }
        hint_keys = {self._hint_key(item) for item in hints}
        hinted_pairs = {(item.source_ref, item.target_ref) for item in hints}
        ordered = [
            item for item in assertions
            if item.status is AssertionStatus.ASSERTED
            and not item.quoted
            and item.evidence is not None
            and item.evidence.start is not None
        ]
        ordered.sort(key=lambda item: (item.evidence.start, item.evidence.end or 10**12, item.local_id))
        for left, right in zip(ordered, ordered[1:]):
            if (left.local_id, right.local_id) in relation_pairs:
                continue
            # A more specific temporal/simultaneous hypothesis for the same pair
            # dominates generic narrative adjacency.  Do not stack a second
            # CAUSAL_CANDIDATE merely because the events are also adjacent.
            if (left.local_id, right.local_id) in hinted_pairs:
                continue
            left_token = self._token_for_predicate(left)
            right_token = self._token_for_predicate(right)
            if left_token is None or right_token is None:
                continue
            left_clause = self.graph.clause_for_token(left_token.index)
            right_clause = self.graph.clause_for_token(right_token.index)
            if left_clause is None or right_clause is None:
                continue
            # Candidate only when narration itself puts the situations next to each
            # other in one sentence or across one immediate sentence boundary.
            if abs(left_clause.sentence_id - right_clause.sentence_id) > 1:
                continue
            key = (
                SituationRelationHintKind.CAUSAL_CANDIDATE.value,
                left.local_id,
                right.local_id,
            )
            if key in hint_keys:
                continue
            hints.append(
                SituationRelationHintCandidate(
                    SituationRelationHintKind.CAUSAL_CANDIDATE,
                    left.local_id,
                    right.local_id,
                    self._evidence_between(left, right),
                    reason="adjacent narrated events; requires semantic evidence before CAUSE materialization",
                )
            )
            hint_keys.add(key)

    def normalize(
        self,
        assertions: tuple[AssertionCandidate, ...] | list[AssertionCandidate],
        relations: tuple[SituationRelationCandidate, ...] | list[SituationRelationCandidate],
    ) -> EventNormalizationOutcome:
        mutable_assertions = list(assertions)
        mutable_relations = list(relations)
        hints: list[SituationRelationHintCandidate] = []
        diagnostics: list[str] = []
        self._normalize_detached_nonfinite(
            mutable_assertions, mutable_relations, hints, diagnostics
        )
        self._normalize_perfective_coordination(
            mutable_assertions, mutable_relations, hints, diagnostics
        )
        self._normalize_serial_perfective_events(
            mutable_assertions, mutable_relations, hints, diagnostics
        )
        self._result_state_assertions(mutable_assertions, diagnostics)
        self._narrative_adjacency_hints(mutable_assertions, mutable_relations, hints)

        # Stable de-duplication keeps diagnostics reproducible when one structural
        # cue is discovered through more than one internal route.
        rel_seen: set[tuple[str, str, str]] = set()
        final_relations: list[SituationRelationCandidate] = []
        for item in mutable_relations:
            key = self._relation_key(item)
            if key in rel_seen:
                continue
            rel_seen.add(key)
            final_relations.append(item)
        hint_seen: set[tuple[str, str, str]] = set()
        final_hints: list[SituationRelationHintCandidate] = []
        for item in hints:
            key = self._hint_key(item)
            if key in hint_seen:
                continue
            hint_seen.add(key)
            final_hints.append(item)
        return EventNormalizationOutcome(
            assertions=tuple(mutable_assertions),
            relations=tuple(final_relations),
            relation_hints=tuple(final_hints),
            diagnostics=tuple(diagnostics),
        )
