from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Callable, Mapping, Sequence

from .contracts import (
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
)
from .linguistic_candidates import LinguisticCandidateGraph


ModalProbe = Callable[[str, str, tuple[str, ...]], str | None]

_MODAL_LABEL_TO_OPERATOR = {
    "POSSIBLE": PropositionOperator.POSSIBLE,
    "REQUIRED": PropositionOperator.REQUIRED,
    "PERMITTED": PropositionOperator.PERMITTED,
}
_MODAL_OPERATORS = frozenset(_MODAL_LABEL_TO_OPERATOR.values())
_MODAL_CUE_POS = frozenset({"PRED", "ADVB", "PRCL", "ADJS"})
_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]")


@dataclass(frozen=True, slots=True)
class ModalFormalizationResult:
    roots: tuple[PropositionRootCandidate, ...]
    diagnostics: tuple[str, ...] = ()
    unresolved: str | None = None


@dataclass(frozen=True, slots=True)
class _Cue:
    text: str
    start: int
    end: int
    sentence_id: int
    source_ref: str | None = None


class ModalScopeBuilder:
    """Add only source-supported modal wrappers to already parsed propositions.

    Python owns proposition leaves and every candidate scope. The model receives
    one structurally isolated cue and returns only a fixed modal label, followed by
    one fixed scope label when several already-enumerated subexpressions are legal.

    No lexical modal inventory is used. Candidate cues come from two structural
    shapes only:
      * an asserted zero-actant predicative shell next to another proposition;
      * unconsumed adverbial/predicative/particle material in a proposition sentence.

    NONE leaves the original factual structure untouched. UNCLEAR/protocol failure
    fails closed because silently asserting P would be stronger than an unresolved
    modal reading.
    """

    _OPERATOR_CHOICES = (
        "POSSIBLE",
        "REQUIRED",
        "PERMITTED",
        "NONE",
        "UNCLEAR",
    )
    _MAX_SCOPE_CHOICES = 24

    def __init__(
        self,
        graph: LinguisticCandidateGraph,
        probe: ModalProbe,
        *,
        ignored_token_indices: frozenset[int] = frozenset(),
    ) -> None:
        self.graph = graph
        self.probe = probe
        self.ignored_token_indices = ignored_token_indices
        self._diagnostics: list[str] = []
        self._unresolved: str | None = None

    @staticmethod
    def _render(expr: PropositionExprCandidate) -> str:
        if expr.operator is PropositionOperator.REF:
            return expr.ref or ""
        return (
            f"{expr.operator.value}("
            + ",".join(ModalScopeBuilder._render(item) for item in expr.members)
            + ")"
        )

    @staticmethod
    def _cover_evidence(
        source_text: str,
        refs: Sequence[str],
        by_id: Mapping[str, AssertionCandidate],
    ) -> EvidenceSpan | None:
        spans = [
            item.evidence
            for ref in refs
            if (item := by_id.get(ref)) is not None
            and item.evidence is not None
            and item.evidence.start is not None
            and item.evidence.end is not None
        ]
        if not spans:
            return None
        start = min(int(item.start) for item in spans)
        end = max(int(item.end) for item in spans)
        return EvidenceSpan(source_text[start:end], start, end)

    def _sentence_id(
        self,
        local_id: str,
        assertion_spans: Mapping[str, object | None],
    ) -> int | None:
        span = assertion_spans.get(local_id)
        start_index = getattr(span, "start_index", None)
        if isinstance(start_index, int):
            clause = self.graph.clause_for_token(start_index)
            if clause is not None:
                return clause.sentence_id
        assertion = self._by_id.get(local_id)
        evidence = assertion.evidence if assertion is not None else None
        if evidence is not None and evidence.start is not None:
            token = next(
                (
                    item for item in self.graph.tokens
                    if item.start <= evidence.start < item.end
                    or evidence.start <= item.start < (evidence.end or evidence.start)
                ),
                None,
            )
            if token is not None:
                clause = self.graph.clause_for_token(token.index)
                if clause is not None:
                    return clause.sentence_id
        return None

    @staticmethod
    def _nested_refs(assertions: Sequence[AssertionCandidate]) -> set[str]:
        out: set[str] = set()
        for parent in assertions:
            for actant in parent.actants:
                if actant.candidate_ref is not None:
                    out.add(actant.candidate_ref)
                if actant.proposition is not None:
                    out.update(actant.proposition.leaf_refs())
        return out

    def _shell_cues(
        self,
        assertions: Sequence[AssertionCandidate],
        assertion_spans: Mapping[str, object | None],
        sentence_target_counts: Mapping[int, int],
    ) -> list[_Cue]:
        cues: list[_Cue] = []
        for item in assertions:
            proposition_only_actants = bool(item.actants) and all(
                actant.candidate_ref is not None
                or actant.proposition is not None
                for actant in item.actants
            )
            if (
                item.status is not AssertionStatus.ASSERTED
                or item.quoted
                or (item.actants and not proposition_only_actants)
            ):
                continue
            sentence_id = self._sentence_id(item.local_id, assertion_spans)
            if sentence_id is None:
                continue
            if (
                not proposition_only_actants
                and sentence_target_counts.get(sentence_id, 0) < 2
            ):
                continue
            # The cue is the matrix predicate itself, not its complete subordinate
            # proposition evidence span.
            evidence = item.predicate.evidence or item.evidence
            if (
                evidence is None
                or evidence.start is None
                or evidence.end is None
                or not evidence.text.strip()
            ):
                continue
            cues.append(
                _Cue(
                    evidence.text.strip(),
                    int(evidence.start),
                    int(evidence.end),
                    sentence_id,
                    source_ref=item.local_id,
                )
            )
        return cues

    def _token_cues(
        self,
        assertions: Sequence[AssertionCandidate],
        assertion_spans: Mapping[str, object | None],
        sentence_target_counts: Mapping[int, int],
    ) -> list[_Cue]:
        occupied: list[tuple[int, int]] = []
        for item in assertions:
            for evidence in (
                item.predicate.evidence,
                *(actant.evidence for actant in item.actants),
            ):
                if (
                    evidence is not None
                    and evidence.start is not None
                    and evidence.end is not None
                ):
                    occupied.append((int(evidence.start), int(evidence.end)))

        def is_occupied(start: int, end: int) -> bool:
            return any(start < right and end > left for left, right in occupied)

        eligible: list[tuple[object, int]] = []
        for token in self.graph.tokens:
            if token.index in self.ignored_token_indices:
                continue
            if is_occupied(token.start, token.end):
                continue
            surface = (token.raw_text or token.text).strip()
            if not surface or not _WORD_RE.search(surface):
                continue
            if surface.casefold() in {"не", "ни"}:
                continue
            clause = self.graph.clause_for_token(token.index)
            if clause is None or sentence_target_counts.get(clause.sentence_id, 0) < 1:
                continue
            poses = {item.pos for item in token.analyses if item.pos}
            # Structural coordinators/connectors are proposition topology, not
            # modality, even when morphology also offers a rare adverbial parse.
            if poses & {"CONJ", "PREP"}:
                continue
            if not (poses & _MODAL_CUE_POS):
                continue
            eligible.append((token, clause.sentence_id))

        cues: list[_Cue] = []
        used: set[int] = set()
        by_index = {item.index: item for item in self.graph.tokens}
        for token, sentence_id in eligible:
            if token.index in used:
                continue
            # Grow through adjacent unoccupied word material so multiword
            # parentheticals are offered as one semantic cue, not nested wrappers.
            members = [token]
            for direction in (-1, 1):
                cursor = token.index + direction
                grown: list[object] = []
                while len(grown) < 3:
                    other = by_index.get(cursor)
                    if other is None or is_occupied(other.start, other.end):
                        break
                    surface = (other.raw_text or other.text).strip()
                    if not surface or not _WORD_RE.search(surface):
                        break
                    other_clause = self.graph.clause_for_token(other.index)
                    if other_clause is None or other_clause.sentence_id != sentence_id:
                        break
                    grown.append(other)
                    cursor += direction
                if direction < 0:
                    members = list(reversed(grown)) + members
                else:
                    members.extend(grown)
            members = sorted({item.index: item for item in members}.values(), key=lambda x: x.index)
            for item in members:
                used.add(item.index)
            start = min(item.start for item in members)
            end = max(item.end for item in members)
            text = self.graph.text[start:end].strip()
            if text:
                cues.append(_Cue(text, start, end, sentence_id))
        return cues

    @staticmethod
    def _prune_ref(
        expr: PropositionExprCandidate,
        ref: str,
    ) -> PropositionExprCandidate | None:
        if expr.operator is PropositionOperator.REF:
            return None if expr.ref == ref else expr
        members = tuple(
            item
            for child in expr.members
            if (item := ModalScopeBuilder._prune_ref(child, ref)) is not None
        )
        if len(members) == len(expr.members):
            return expr
        if not members:
            return None
        if expr.operator in {
            PropositionOperator.NOT,
            PropositionOperator.POSSIBLE,
            PropositionOperator.REQUIRED,
            PropositionOperator.PERMITTED,
        }:
            return members[0] if len(members) == 1 else None
        if expr.operator is PropositionOperator.IMPLIES:
            return None
        if len(members) == 1:
            return members[0]
        return PropositionExprCandidate(expr.operator, members=members)

    @staticmethod
    def _subexpressions(expr: PropositionExprCandidate) -> tuple[PropositionExprCandidate, ...]:
        out: list[PropositionExprCandidate] = []
        seen: set[str] = set()

        def visit(item: PropositionExprCandidate) -> None:
            key = ModalScopeBuilder._render(item)
            if key not in seen:
                seen.add(key)
                out.append(item)
            # Predicate-level negation is already a resolved local operator.
            # A sentence-level modal cue may wrap NOT(P), but must not silently
            # move below that boundary and turn it into NOT(MODAL(P)).
            if item.operator is PropositionOperator.NOT:
                return
            for child in item.members:
                visit(child)

        visit(expr)
        return tuple(out)

    @staticmethod
    def _replace_subexpr(
        expr: PropositionExprCandidate,
        target: PropositionExprCandidate,
        replacement: PropositionExprCandidate,
    ) -> PropositionExprCandidate:
        if expr == target:
            return replacement
        if expr.operator is PropositionOperator.REF:
            return expr
        members = tuple(
            ModalScopeBuilder._replace_subexpr(child, target, replacement)
            for child in expr.members
        )
        return expr if members == expr.members else PropositionExprCandidate(expr.operator, members=members)

    def build(
        self,
        source_text: str,
        assertions: Sequence[AssertionCandidate],
        assertion_spans: Mapping[str, object | None],
        roots: Sequence[PropositionRootCandidate] = (),
    ) -> ModalFormalizationResult:
        self._diagnostics = []
        self._unresolved = None
        self._by_id = {item.local_id: item for item in assertions}
        root_list = list(roots)
        nested = self._nested_refs(assertions)
        root_leafs = {
            ref for root in root_list for ref in root.expression.leaf_refs()
        }
        source_refs = {
            ref for root in root_list for ref in root.operator_source_refs
        }

        # Every sentence target is either an existing non-bare formula root or one
        # ordinary top-level assertion not already represented inside such a root.
        def target_count_for_sentence(sentence_id: int) -> int:
            count = 0
            for root in root_list:
                leaf = next(iter(root.expression.leaf_refs()), None)
                if leaf is not None and self._sentence_id(leaf, assertion_spans) == sentence_id:
                    count += 1
            for item in assertions:
                if (
                    item.local_id in root_leafs
                    or item.local_id in source_refs
                    or item.local_id in nested
                    or item.status is not AssertionStatus.ASSERTED
                    or item.quoted
                ):
                    continue
                if self._sentence_id(item.local_id, assertion_spans) == sentence_id:
                    count += 1
            return count

        sentence_ids = {
            sentence
            for item in assertions
            if (sentence := self._sentence_id(item.local_id, assertion_spans)) is not None
        }
        sentence_target_counts = {
            sentence: target_count_for_sentence(sentence)
            for sentence in sentence_ids
        }
        cues = self._shell_cues(
            assertions, assertion_spans, sentence_target_counts
        )
        cues.extend(
            self._token_cues(assertions, assertion_spans, sentence_target_counts)
        )
        cues.sort(key=lambda item: (item.start, item.end, item.source_ref or ""))

        created_index = 0
        for cue in cues:
            # Build current top-level expression owners for this sentence.
            owners: list[tuple[str, int | str, PropositionExprCandidate]] = []

            # An impersonal matrix operator may already govern proposition content
            # structurally (e.g. REQUIRED(content=P)). It remains eligible only
            # because _shell_cues proved that every actant is proposition-valued;
            # subject-bearing attitudes such as BELIEVES(A,P) never enter here.
            if cue.source_ref is not None:
                source = self._by_id.get(cue.source_ref)
                if source is not None:
                    for actant in source.actants:
                        content = actant.proposition
                        if content is None and actant.candidate_ref is not None:
                            content = PropositionExprCandidate.ref_expr(
                                actant.candidate_ref
                            )
                        if content is not None:
                            owners.append(
                                ("content", cue.source_ref, content)
                            )

            for index, root in enumerate(root_list):
                leaf = next(iter(root.expression.leaf_refs()), None)
                if leaf is None or self._sentence_id(leaf, assertion_spans) != cue.sentence_id:
                    continue
                expr = root.expression
                if cue.source_ref is not None and cue.source_ref in expr.leaf_refs():
                    pruned = self._prune_ref(expr, cue.source_ref)
                    if pruned is None:
                        continue
                    expr = pruned
                owners.append(("root", index, expr))

            current_root_leafs = {
                ref for root in root_list for ref in root.expression.leaf_refs()
            }
            current_source_refs = {
                ref for root in root_list for ref in root.operator_source_refs
            }
            for item in assertions:
                if (
                    item.local_id == cue.source_ref
                    or item.local_id in current_root_leafs
                    or item.local_id in current_source_refs
                    or item.local_id in nested
                    or item.status is not AssertionStatus.ASSERTED
                    or item.quoted
                ):
                    continue
                if self._sentence_id(item.local_id, assertion_spans) == cue.sentence_id:
                    atom = PropositionExprCandidate.ref_expr(item.local_id)
                    if item.negated:
                        atom = PropositionExprCandidate(
                            PropositionOperator.NOT,
                            members=(atom,),
                        )
                    owners.append(
                        (
                            "bare",
                            item.local_id,
                            atom,
                        )
                    )
            if not owners:
                continue

            operator_prompt = (
                f"TEXT:\n{source_text}\n"
                f"CUE:\n{cue.text}\n"
                "QUESTION:\nDoes this source cue change the truth commitment of a proposition "
                "to possibility, requirement/necessity, or permission?\n"
                "POSSIBLE: proposition is presented only as possible/probable/uncertain.\n"
                "REQUIRED: proposition is presented as required/necessary/obligatory.\n"
                "PERMITTED: proposition is presented as permitted/allowed.\n"
                "NONE: this cue does not create one of those proposition scopes.\n"
                "UNCLEAR: it does affect commitment but the type cannot be decided safely.\n"
                "CHOICES:\nPOSSIBLE\nREQUIRED\nPERMITTED\nNONE\nUNCLEAR"
            )
            decision = self.probe(
                "modal_operator", operator_prompt, self._OPERATOR_CHOICES
            )
            if decision == "NONE":
                continue
            if decision not in _MODAL_LABEL_TO_OPERATOR:
                self._unresolved = (
                    f"modal operator unresolved for source cue {cue.text!r}"
                )
                self._diagnostics.append(
                    f"MODAL:operator_unclear:{cue.start}:{cue.end}"
                )
                return ModalFormalizationResult(
                    (), tuple(self._diagnostics), self._unresolved
                )

            scoped: list[
                tuple[str, int | str, PropositionExprCandidate, PropositionExprCandidate]
            ] = []
            seen_scopes: set[tuple[str, str]] = set()
            for owner_kind, owner_id, expr in owners:
                for candidate in self._subexpressions(expr):
                    key = (f"{owner_kind}:{owner_id}", self._render(candidate))
                    if key in seen_scopes:
                        continue
                    seen_scopes.add(key)
                    scoped.append((owner_kind, owner_id, expr, candidate))
            if not scoped or len(scoped) > self._MAX_SCOPE_CHOICES:
                self._unresolved = (
                    f"modal scope candidate count is unsafe: {len(scoped)}"
                )
                self._diagnostics.append(
                    f"MODAL:scope_candidate_overflow:{len(scoped)}"
                )
                return ModalFormalizationResult(
                    (), tuple(self._diagnostics), self._unresolved
                )

            if len(scoped) == 1:
                selected = scoped[0]
            else:
                labels = tuple(f"C{index}" for index in range(1, len(scoped) + 1))
                scope_prompt = (
                    f"TEXT:\n{source_text}\n"
                    f"MODAL CUE:\n{cue.text}\n"
                    f"MODAL TYPE:\n{decision}\n"
                    "CANDIDATE PROPOSITION SCOPES:\n"
                    + "\n".join(
                        f"{label}: {self._render(item[3])}"
                        for label, item in zip(labels, scoped)
                    )
                )
                scope_decision = self.probe(
                    "modal_scope", scope_prompt, (*labels, "UNCLEAR")
                )
                if scope_decision not in labels:
                    self._unresolved = (
                        f"modal scope unresolved for source cue {cue.text!r}"
                    )
                    self._diagnostics.append(
                        f"MODAL:scope_unclear:{cue.start}:{cue.end}"
                    )
                    return ModalFormalizationResult(
                        (), tuple(self._diagnostics), self._unresolved
                    )
                selected = scoped[labels.index(scope_decision)]

            owner_kind, owner_id, owner_expr, target = selected
            wrapper = PropositionExprCandidate(
                _MODAL_LABEL_TO_OPERATOR[decision],
                members=(target,),
            )
            rewritten = self._replace_subexpr(owner_expr, target, wrapper)
            evidence = self._cover_evidence(
                source_text, rewritten.leaf_refs(), self._by_id
            )

            if owner_kind == "root":
                index = int(owner_id)
                current = root_list[index]
                operator_sources = list(current.operator_source_refs)
                if cue.source_ref is not None and cue.source_ref not in operator_sources:
                    operator_sources.append(cue.source_ref)
                root_list[index] = replace(
                    current,
                    expression=rewritten,
                    evidence=evidence or current.evidence,
                    operator_source_refs=tuple(operator_sources),
                )
            else:
                created_index += 1
                operator_sources = (
                    (cue.source_ref,) if cue.source_ref is not None else ()
                )
                root_list.append(
                    PropositionRootCandidate(
                        f"F_MODAL_{created_index}",
                        rewritten,
                        evidence=evidence,
                        operator_source_refs=operator_sources,
                    )
                )

            # If an operator shell was accidentally included as a truth-functional
            # leaf by the earlier generic logical pass, remove it now.
            if cue.source_ref is not None:
                for index, root in enumerate(root_list):
                    if cue.source_ref not in root.expression.leaf_refs():
                        continue
                    pruned = self._prune_ref(root.expression, cue.source_ref)
                    if pruned is None:
                        continue
                    sources = tuple(
                        dict.fromkeys((*root.operator_source_refs, cue.source_ref))
                    )
                    root_list[index] = replace(
                        root,
                        expression=pruned,
                        operator_source_refs=sources,
                    )

            self._diagnostics.append(
                f"MODAL:{decision}:{cue.start}:{cue.end}:{self._render(target)}"
            )

        return ModalFormalizationResult(
            tuple(root_list), tuple(self._diagnostics), self._unresolved
        )
