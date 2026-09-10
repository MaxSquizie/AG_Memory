from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Mapping, Sequence

from .contracts import (
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    EvidenceSpan,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
)
from .linguistic_candidates import CoordinationKind, LinguisticCandidateGraph


LogicalProbe = Callable[[str, str, tuple[str, ...]], str | None]


@dataclass(frozen=True, slots=True)
class _Atom:
    local_id: str
    sentence_id: int
    start: int
    end: int
    text: str
    predicate_start: int | None = None
    predicate_end: int | None = None


@dataclass(frozen=True, slots=True)
class LogicalFormalizationResult:
    roots: tuple[PropositionRootCandidate, ...]
    diagnostics: tuple[str, ...] = ()
    unresolved: str | None = None


class LogicalFormBuilder:
    """Build source-level propositional scope from already parsed semantic frames.

    The builder never invents predicates, roles, entities, canonical UIDs or truth.
    Python supplies fixed proposition operands and enumerates legal formula shapes.
    A bounded semantic probe is used only when the source relation/scope is not
    already fixed by the linguistic candidate graph.

    OR is the safe base relation for alternatives. A separate bounded semantic
    probe upgrades an already established OR subtree to XOR only when the source
    explicitly commits to exclusivity. This avoids both marker dictionaries and
    accidental exclusive readings of ordinary natural-language "or".
    """

    _RELATION_CHOICES = (
        "AND",
        "OR",
        "IMPLIES_LR",
        "IMPLIES_RL",
        "NONE",
        "UNCLEAR",
    )
    _WHOLE_NEGATION_CHOICES = ("WHOLE_NOT", "NO", "UNCLEAR")
    _CONTENT_OPERATOR_CHOICES = ("NOT_CONTENT", "NONE", "UNCLEAR")
    _OR_EXCLUSIVITY_CHOICES = ("EXCLUSIVE", "INCLUSIVE_OR", "UNCLEAR")
    _MAX_SCOPE_CHOICES = 24

    def __init__(
        self,
        graph: LinguisticCandidateGraph,
        probe: LogicalProbe,
    ) -> None:
        self.graph = graph
        self.probe = probe
        self._diagnostics: list[str] = []
        self._unresolved: str | None = None

    def build(
        self,
        source_text: str,
        assertions: Sequence[AssertionCandidate],
        assertion_spans: Mapping[str, object | None],
        conditionals: Sequence[ConditionalCandidate] = (),
    ) -> LogicalFormalizationResult:
        # A builder is normally turn-local, but keep repeated direct/test use
        # deterministic as well.
        self._diagnostics = []
        self._unresolved = None
        by_id = {item.local_id: item for item in assertions}
        provisional: list[
            tuple[int, int, PropositionExprCandidate, EvidenceSpan | None, tuple[str, ...]]
        ] = []
        consumed: set[str] = set()

        # Existing conditional recognition already gives us exact branch membership
        # and direction.  Expose the same structure through the common proposition
        # AST without changing the mature conditional Integration path.
        for conditional in conditionals:
            antecedent = conditional.antecedent_expr or self._flat_expr(
                conditional.antecedent_refs, PropositionOperator.AND
            )
            consequent = conditional.consequent_expr or self._flat_expr(
                conditional.consequent_refs, PropositionOperator.AND
            )
            antecedent = self._with_leaf_negations(antecedent, by_id)
            consequent = self._with_leaf_negations(consequent, by_id)
            antecedent = self._refine_or_exclusivity(
                source_text, antecedent, by_id, context="conditional antecedent"
            )
            consequent = self._refine_or_exclusivity(
                source_text, consequent, by_id, context="conditional consequent"
            )
            expr = PropositionExprCandidate(
                PropositionOperator.IMPLIES,
                members=(antecedent, consequent),
            )
            evidence = conditional.evidence or self._evidence_for_refs(
                source_text,
                (*conditional.antecedent_refs, *conditional.consequent_refs),
                by_id,
            )
            start = evidence.start if evidence is not None else 10**12
            provisional.append((start, 0, expr, evidence, ()))
            consumed.update(expr.leaf_refs())

        # A matrix frame can be a linguistic truth operator rather than a world
        # predicate: "Неверно, что P".  The candidate proposition edge is structural
        # evidence; the model only decides NOT_CONTENT/NONE/UNCLEAR for that one
        # already-bounded matrix/content pair.
        for parent in assertions:
            if (
                parent.local_id in consumed
                or parent.status is not AssertionStatus.ASSERTED
                or parent.quoted
            ):
                continue
            proposition_actants = [
                item
                for item in parent.actants
                if item.proposition is not None
                or (
                    item.candidate_ref is not None
                    and item.candidate_ref in by_id
                )
            ]
            if len(proposition_actants) != 1:
                continue
            # Open the semantic truth-operator probe only for a negated matrix or
            # an impersonal/content-only matrix.  Ordinary attitude frames with an
            # explicit experiencer/speaker remain outside this logical classifier.
            # This is a structural gate, not a predicate-word list.
            non_content_actants = [
                item for item in parent.actants if item not in proposition_actants
            ]
            if not parent.negated and non_content_actants:
                continue
            content_actant = proposition_actants[0]
            raw_content = (
                content_actant.proposition
                if content_actant.proposition is not None
                else PropositionExprCandidate.ref_expr(content_actant.candidate_ref or "")
            )
            content = self._with_leaf_negations(raw_content, by_id)
            content = self._refine_or_exclusivity(
                source_text, content, by_id, context=f"content of {parent.local_id}"
            )
            content_refs = content.leaf_refs()
            if not content_refs or any(ref not in by_id for ref in content_refs):
                continue
            if parent.local_id in content_refs:
                continue

            prompt = self._content_operator_prompt(
                source_text, parent, content, by_id
            )
            decision = self.probe(
                "logical_content_operator",
                prompt,
                self._CONTENT_OPERATOR_CHOICES,
            )
            if decision != "NOT_CONTENT":
                if decision in {"UNCLEAR", None}:
                    self._diagnostics.append(
                        f"LOGIC:{parent.local_id}:content_operator_unclear"
                    )
                    self._unresolved = (
                        f"logical content operator unresolved for {parent.local_id}"
                    )
                    return LogicalFormalizationResult(
                        (), tuple(self._diagnostics), self._unresolved
                    )
                continue

            expr = PropositionExprCandidate(
                PropositionOperator.NOT, members=(content,)
            )
            evidence = self._cover_evidence(
                source_text,
                tuple(
                    item
                    for item in (
                        parent.evidence,
                        self._evidence_for_refs(
                            source_text, content_refs, by_id
                        ),
                    )
                    if item is not None
                ),
            )
            start = evidence.start if evidence is not None else 10**12
            provisional.append(
                (start, 1, expr, evidence, (parent.local_id,))
            )
            consumed.add(parent.local_id)
            consumed.update(content_refs)
            self._diagnostics.append(
                f"LOGIC:{parent.local_id}:matrix_as_NOT"
            )

        atoms_by_sentence: dict[int, list[_Atom]] = {}
        for assertion in assertions:
            if (
                assertion.local_id in consumed
                or assertion.status is not AssertionStatus.ASSERTED
                or assertion.quoted
            ):
                continue
            atom = self._atom(assertion, assertion_spans.get(assertion.local_id))
            if atom is None:
                continue
            atoms_by_sentence.setdefault(atom.sentence_id, []).append(atom)

        for sentence_id, atoms in sorted(atoms_by_sentence.items()):
            atoms.sort(key=lambda item: (item.start, item.end, item.local_id))
            if len(atoms) < 2:
                continue

            relations: list[str | None] = []
            for left, right in zip(atoms, atoms[1:]):
                structural = self._structural_relation(
                    left, right, source_text
                )
                if structural is not None:
                    relations.append(structural)
                    self._diagnostics.append(
                        f"LOGIC:{left.local_id}->{right.local_id}:structural_{structural}"
                    )
                    continue
                if not self._relation_probe_candidate(
                    source_text, sentence_id, left, right
                ):
                    relations.append(None)
                    continue
                prompt = self._relation_prompt(
                    source_text, sentence_id, left, right
                )
                decision = self.probe(
                    "logical_relation", prompt, self._RELATION_CHOICES
                )
                if decision in {"UNCLEAR", None}:
                    self._diagnostics.append(
                        f"LOGIC:{left.local_id}->{right.local_id}:relation_unclear"
                    )
                    self._unresolved = (
                        "truth-functional relation unresolved between "
                        f"{left.local_id} and {right.local_id}"
                    )
                    return LogicalFormalizationResult(
                        (), tuple(self._diagnostics), self._unresolved
                    )
                if decision == "NONE":
                    relations.append(None)
                    continue
                relations.append(decision)
                self._diagnostics.append(
                    f"LOGIC:{left.local_id}->{right.local_id}:{decision}"
                )

            segment_start = 0
            for boundary_index in range(len(relations) + 1):
                at_end = boundary_index == len(relations)
                if not at_end and relations[boundary_index] is not None:
                    continue
                segment_end = boundary_index
                if segment_end - segment_start >= 1:
                    segment_atoms = atoms[segment_start : segment_end + 1]
                    segment_relations = tuple(
                        item
                        for item in relations[segment_start:segment_end]
                        if item is not None
                    )
                    expr = self._compose_segment(
                        source_text,
                        sentence_id,
                        segment_atoms,
                        segment_relations,
                        by_id,
                    )
                    if self._unresolved is not None:
                        return LogicalFormalizationResult(
                            (), tuple(self._diagnostics), self._unresolved
                        )
                    if expr is not None:
                        evidence = self._cover_evidence(
                            source_text,
                            tuple(
                                by_id[item.local_id].evidence
                                for item in segment_atoms
                                if by_id[item.local_id].evidence is not None
                            ),
                        )
                        start = evidence.start if evidence is not None else segment_atoms[0].start
                        provisional.append((start, 2, expr, evidence, ()))
                        consumed.update(expr.leaf_refs())
                segment_start = boundary_index + 1

        provisional.sort(key=lambda item: (item[0], item[1], self._render(item[2])))
        roots = tuple(
            PropositionRootCandidate(
                local_id=f"F{index}",
                expression=expr,
                evidence=evidence,
                operator_source_refs=operator_refs,
            )
            for index, (_start, _kind, expr, evidence, operator_refs)
            in enumerate(provisional, start=1)
        )
        return LogicalFormalizationResult(
            roots, tuple(self._diagnostics), self._unresolved
        )

    @staticmethod
    def _flat_expr(
        refs: Sequence[str],
        operator: PropositionOperator,
    ) -> PropositionExprCandidate:
        ordered = tuple(dict.fromkeys(refs))
        if len(ordered) == 1:
            return PropositionExprCandidate.ref_expr(ordered[0])
        return PropositionExprCandidate(
            operator,
            members=tuple(
                PropositionExprCandidate.ref_expr(ref) for ref in ordered
            ),
        )

    @classmethod
    def _with_leaf_negations(
        cls,
        expr: PropositionExprCandidate,
        by_id: Mapping[str, AssertionCandidate],
    ) -> PropositionExprCandidate:
        if expr.operator is PropositionOperator.REF:
            assert expr.ref is not None
            leaf = PropositionExprCandidate.ref_expr(expr.ref)
            assertion = by_id.get(expr.ref)
            if assertion is not None and assertion.negated:
                return PropositionExprCandidate(
                    PropositionOperator.NOT, members=(leaf,)
                )
            return leaf
        return PropositionExprCandidate(
            expr.operator,
            members=tuple(
                cls._with_leaf_negations(member, by_id)
                for member in expr.members
            ),
        )

    def _atom(
        self,
        assertion: AssertionCandidate,
        span: object | None,
    ) -> _Atom | None:
        sentence_id: int | None = None
        p_start: int | None = None
        p_end: int | None = None
        if span is not None:
            p_start = getattr(span, "start_index", None)
            p_end = getattr(span, "end_index", None)
            if isinstance(p_start, int):
                clause = self.graph.clause_for_token(p_start)
                if clause is not None:
                    sentence_id = clause.sentence_id
        evidence = assertion.evidence
        if sentence_id is None and evidence is not None:
            for clause in self.graph.clauses:
                if (
                    clause.span.evidence.start <= evidence.start
                    < clause.span.evidence.end
                ):
                    sentence_id = clause.sentence_id
                    break
        if sentence_id is None or evidence is None:
            return None
        return _Atom(
            local_id=assertion.local_id,
            sentence_id=sentence_id,
            start=evidence.start,
            end=evidence.end,
            text=evidence.text,
            predicate_start=p_start if isinstance(p_start, int) else None,
            predicate_end=p_end if isinstance(p_end, int) else None,
        )

    def _structural_relation(
        self,
        left: _Atom,
        right: _Atom,
        source_text: str,
    ) -> str | None:
        # First use the explicit predicate-coordination graph when both semantic
        # frames retain overt predicate heads.
        if (
            left.predicate_start is not None
            and right.predicate_start is not None
            and left.predicate_end is not None
            and right.predicate_end is not None
        ):
            left_heads = {
                item.token_index
                for item in self.graph.predicates
                if left.predicate_start <= item.token_index <= left.predicate_end
            }
            right_heads = {
                item.token_index
                for item in self.graph.predicates
                if right.predicate_start <= item.token_index <= right.predicate_end
            }
            if len(left_heads) == 1 and len(right_heads) == 1:
                left_head = next(iter(left_heads))
                right_head = next(iter(right_heads))
                for group in self.graph.frame_graph.coordinations:
                    members = group.member_token_indices
                    if left_head not in members or right_head not in members:
                        continue
                    li, ri = members.index(left_head), members.index(right_head)
                    if abs(li - ri) != 1:
                        continue
                    return (
                        PropositionOperator.OR.value
                        if group.operator is CoordinationKind.OR
                        else PropositionOperator.AND.value
                    )

        # Recovered ellipsis can lack a target predicate head even though the
        # source still contains an explicit clause coordinator. Coordinator
        # identity is finite grammar, not an open-ended semantic lexicon.
        if 0 <= left.end <= right.start <= len(source_text):
            boundary = source_text[left.end:right.start].casefold()
            words = tuple(
                part
                for part in "".join(
                    ch if (ch.isalpha() or ch in {"ё", "-"}) else " "
                    for ch in boundary
                ).split()
                if part
            )
            if any(word in {"или", "либо"} for word in words):
                return PropositionOperator.OR.value
            if any(word in {"и", "да", "а", "но", "однако"} for word in words):
                return PropositionOperator.AND.value

        # Clause markers provide the same finite structural evidence when source
        # evidence spans overlap because of shared/recovered actants.
        right_clause = next(
            (
                clause
                for clause in self.graph.clauses
                if clause.sentence_id == right.sentence_id
                and clause.span.evidence.start <= right.start
                < clause.span.evidence.end
            ),
            None,
        )
        if right_clause is not None and right_clause.marker:
            marker = right_clause.marker.casefold()
            if marker in {"или", "либо"}:
                return PropositionOperator.OR.value
            if marker in {"и", "да", "а", "но", "однако"}:
                return PropositionOperator.AND.value
        return None

    def _relation_probe_candidate(
        self,
        source_text: str,
        sentence_id: int,
        left: _Atom,
        right: _Atom,
    ) -> bool:
        """Open a semantic probe only for a bounded nontrivial relation surface.

        The trigger does not enumerate semantic paraphrases. It recognizes only
        structural evidence that material outside the two proposition cores may
        encode their relation: lexical boundary material or a punctuation-led
        preface such as "one of the following: ...".
        """
        sentence_text = self._sentence_text(source_text, sentence_id)
        if 0 <= left.end <= right.start <= len(source_text):
            boundary = source_text[left.end:right.start]
            if any(ch.isalpha() for ch in boundary):
                return True

        clauses = [
            item for item in self.graph.clauses if item.sentence_id == sentence_id
        ]
        if clauses:
            sentence_start = min(item.span.evidence.start for item in clauses)
            prefix = source_text[sentence_start:left.start]
            if ":" in prefix or "—" in prefix or "–" in prefix:
                return True
        return ":" in sentence_text and left.start < right.start

    def _compose_segment(
        self,
        source_text: str,
        sentence_id: int,
        atoms: Sequence[_Atom],
        relations: tuple[str, ...],
        by_id: Mapping[str, AssertionCandidate],
    ) -> PropositionExprCandidate | None:
        if len(atoms) < 2 or len(relations) != len(atoms) - 1:
            return None
        atom_exprs = tuple(
            self._with_leaf_negations(
                PropositionExprCandidate.ref_expr(item.local_id), by_id
            )
            for item in atoms
        )

        if len(set(relations)) == 1 and relations[0] in {"AND", "OR"}:
            expr = PropositionExprCandidate(
                PropositionOperator(relations[0]),
                members=atom_exprs,
            )
            expr = self._refine_or_exclusivity(
                source_text, expr, by_id, context=f"sentence {sentence_id}"
            )
            return self._maybe_whole_negation(
                source_text, sentence_id, atoms, expr, by_id
            )

        candidates = self._scope_candidates(atom_exprs, relations)
        if not candidates:
            self._unresolved = (
                f"logical scope has no legal candidate tree in sentence {sentence_id}"
            )
            return None
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > self._MAX_SCOPE_CHOICES:
            self._diagnostics.append(
                f"LOGIC:sentence{sentence_id}:scope_candidate_overflow:{len(candidates)}"
            )
            self._unresolved = (
                f"logical scope candidate overflow in sentence {sentence_id}: "
                f"{len(candidates)} candidates"
            )
            return None

        labels = tuple(f"C{index}" for index in range(1, len(candidates) + 1))
        sentence_text = self._sentence_text(source_text, sentence_id)
        prompt = (
            f"TEXT:\n{sentence_text}\n"
            + "ATOMS:\n"
            + "\n".join(
                f"{item.local_id}: {item.text}" for item in atoms
            )
            + "\nCANDIDATE SCOPES:\n"
            + "\n".join(
                f"{label}: {self._render(expr)}"
                for label, expr in zip(labels, candidates)
            )
        )
        decision = self.probe(
            "logical_scope", prompt, (*labels, "UNCLEAR")
        )
        if decision is None or decision == "UNCLEAR":
            self._diagnostics.append(
                f"LOGIC:sentence{sentence_id}:scope_unclear"
            )
            self._unresolved = f"logical scope unresolved in sentence {sentence_id}"
            return None
        expr = candidates[labels.index(decision)]
        expr = self._refine_or_exclusivity(
            source_text, expr, by_id, context=f"sentence {sentence_id}"
        )
        return self._maybe_whole_negation(
            source_text, sentence_id, atoms, expr, by_id
        )

    @classmethod
    def _scope_candidates(
        cls,
        atoms: tuple[PropositionExprCandidate, ...],
        relations: tuple[str, ...],
    ) -> tuple[PropositionExprCandidate, ...]:
        @lru_cache(maxsize=None)
        def build(start: int, end: int) -> tuple[PropositionExprCandidate, ...]:
            if end - start == 1:
                return (atoms[start],)
            values: dict[str, PropositionExprCandidate] = {}
            for split in range(start, end - 1):
                relation = relations[split]
                for left in build(start, split + 1):
                    for right in build(split + 1, end):
                        expr = cls._combine(relation, left, right)
                        values.setdefault(cls._render(expr), expr)
            return tuple(values[key] for key in sorted(values))
        return build(0, len(atoms))

    @staticmethod
    def _combine(
        relation: str,
        left: PropositionExprCandidate,
        right: PropositionExprCandidate,
    ) -> PropositionExprCandidate:
        if relation in {"AND", "OR"}:
            operator = PropositionOperator(relation)
            left_members = left.members if left.operator is operator else (left,)
            right_members = right.members if right.operator is operator else (right,)
            return PropositionExprCandidate(
                operator,
                members=tuple((*left_members, *right_members)),
            )
        if relation == "IMPLIES_LR":
            return PropositionExprCandidate(
                PropositionOperator.IMPLIES, members=(left, right)
            )
        if relation == "IMPLIES_RL":
            return PropositionExprCandidate(
                PropositionOperator.IMPLIES, members=(right, left)
            )
        raise ValueError(f"unsupported logical relation: {relation}")

    def _refine_or_exclusivity(
        self,
        source_text: str,
        expr: PropositionExprCandidate,
        by_id: Mapping[str, AssertionCandidate],
        *,
        context: str,
    ) -> PropositionExprCandidate:
        """Upgrade only explicitly exclusive OR subtrees to canonical XOR.

        UNCLEAR keeps OR because OR is entailed by both inclusive and exclusive
        readings. This is a sound weakening, not a guessed semantic fallback.
        """
        if expr.operator is PropositionOperator.REF:
            return expr
        members = tuple(
            self._refine_or_exclusivity(
                source_text, member, by_id, context=context
            )
            for member in expr.members
        )
        refined = PropositionExprCandidate(expr.operator, members=members)
        if refined.operator is not PropositionOperator.OR:
            return refined

        leaf_lines = []
        for ref in refined.leaf_refs():
            assertion = by_id.get(ref)
            leaf_lines.append(
                f"{ref}: "
                + (
                    assertion.evidence.text
                    if assertion is not None and assertion.evidence is not None
                    else ref
                )
            )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"CONTEXT:\n{context}\n"
            f"OR CANDIDATE:\n{self._render(refined)}\n"
            + "ALTERNATIVES:\n"
            + "\n".join(leaf_lines)
        )
        decision = self.probe(
            "logical_or_exclusivity",
            prompt,
            self._OR_EXCLUSIVITY_CHOICES,
        )
        if decision == "EXCLUSIVE":
            self._diagnostics.append(
                f"LOGIC:{context}:OR_promoted_to_XOR:{self._render(refined)}"
            )
            return PropositionExprCandidate(
                PropositionOperator.XOR, members=refined.members
            )
        if decision == "UNCLEAR":
            self._diagnostics.append(
                f"LOGIC:{context}:or_exclusivity_unclear_kept_OR"
            )
        return refined

    def _whole_negation_probe_candidate(
        self,
        sentence_id: int,
        atoms: Sequence[_Atom],
        by_id: Mapping[str, AssertionCandidate],
    ) -> bool:
        if any(by_id[item.local_id].negated for item in atoms):
            return True
        clauses = [
            item for item in self.graph.clauses if item.sentence_id == sentence_id
        ]
        if not clauses:
            return False
        start = min(item.span.evidence.start or 0 for item in clauses)
        end = max(item.span.evidence.end or 0 for item in clauses)
        for token in self.graph.tokens:
            if not (start <= token.start < end):
                continue
            # НЕ/НИ are finite grammatical scope triggers, not semantic answers.
            surface = (token.raw_text or token.text).strip().casefold()
            if surface in {"не", "ни"}:
                return True
        return False

    def _maybe_whole_negation(
        self,
        source_text: str,
        sentence_id: int,
        atoms: Sequence[_Atom],
        expr: PropositionExprCandidate,
        by_id: Mapping[str, AssertionCandidate],
    ) -> PropositionExprCandidate | None:
        if not self._whole_negation_probe_candidate(
            sentence_id, atoms, by_id
        ):
            return expr
        sentence_text = self._sentence_text(source_text, sentence_id)
        prompt = (
            f"TEXT:\n{sentence_text}\n"
            f"CANDIDATE FORMULA:\n{self._render(expr)}\n"
            + "LOCAL NEGATIONS ALREADY REPRESENTED:\n"
            + (
                ", ".join(
                    item.local_id
                    for item in atoms
                    if by_id[item.local_id].negated
                )
                or "NONE"
            )
        )
        decision = self.probe(
            "logical_whole_negation",
            prompt,
            self._WHOLE_NEGATION_CHOICES,
        )
        if decision == "WHOLE_NOT":
            return PropositionExprCandidate(
                PropositionOperator.NOT, members=(expr,)
            )
        if decision == "UNCLEAR" or decision is None:
            self._diagnostics.append(
                f"LOGIC:sentence{sentence_id}:whole_negation_unclear"
            )
            self._unresolved = (
                f"whole-formula negation scope unresolved in sentence {sentence_id}"
            )
            return None
        return expr

    def _relation_prompt(
        self,
        source_text: str,
        sentence_id: int,
        left: _Atom,
        right: _Atom,
    ) -> str:
        sentence_text = self._sentence_text(source_text, sentence_id)
        boundary = ""
        if 0 <= left.end <= right.start <= len(source_text):
            boundary = source_text[left.end:right.start]
        return (
            f"TEXT:\n{sentence_text}\n"
            f"LEFT ({left.local_id}):\n{left.text}\n"
            f"RIGHT ({right.local_id}):\n{right.text}\n"
            f"BOUNDARY SURFACE:\n{boundary or '<overlap-or-none>'}"
        )

    def _content_operator_prompt(
        self,
        source_text: str,
        parent: AssertionCandidate,
        content: PropositionExprCandidate,
        by_id: Mapping[str, AssertionCandidate],
    ) -> str:
        content_lines = []
        for ref in content.leaf_refs():
            assertion = by_id.get(ref)
            content_lines.append(
                f"{ref}: {assertion.evidence.text if assertion and assertion.evidence else ref}"
            )
        return (
            f"TEXT:\n{source_text}\n"
            f"MATRIX ({parent.local_id}):\n"
            f"{parent.evidence.text if parent.evidence else parent.predicate.surface}\n"
            f"MATRIX PREDICATE:\n{parent.predicate.surface}\n"
            f"CONTENT FORMULA:\n{self._render(content)}\n"
            + "CONTENT LEAVES:\n"
            + "\n".join(content_lines)
        )

    def _sentence_text(self, source_text: str, sentence_id: int) -> str:
        clauses = [
            item for item in self.graph.clauses if item.sentence_id == sentence_id
        ]
        if not clauses:
            return source_text
        start = min(item.span.evidence.start for item in clauses)
        end = max(item.span.evidence.end for item in clauses)
        return source_text[start:end]

    @staticmethod
    def _evidence_for_refs(
        source_text: str,
        refs: Sequence[str],
        by_id: Mapping[str, AssertionCandidate],
    ) -> EvidenceSpan | None:
        items = tuple(
            by_id[ref].evidence
            for ref in refs
            if ref in by_id and by_id[ref].evidence is not None
        )
        return LogicalFormBuilder._cover_evidence(source_text, items)

    @staticmethod
    def _cover_evidence(
        source_text: str,
        items: Sequence[EvidenceSpan],
    ) -> EvidenceSpan | None:
        if not items:
            return None
        start = min(item.start for item in items)
        end = max(item.end for item in items)
        return EvidenceSpan(source_text[start:end], start, end)

    @staticmethod
    def _render(expr: PropositionExprCandidate) -> str:
        if expr.operator is PropositionOperator.REF:
            assert expr.ref is not None
            return expr.ref
        if expr.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}:
            return f"NOT({LogicalFormBuilder._render(expr.members[0])})"
        if expr.operator is PropositionOperator.IMPLIES:
            return (
                "IMPLIES("
                + LogicalFormBuilder._render(expr.members[0])
                + ","
                + LogicalFormBuilder._render(expr.members[1])
                + ")"
            )
        return (
            f"{expr.operator.value}("
            + ",".join(LogicalFormBuilder._render(item) for item in expr.members)
            + ")"
        )
