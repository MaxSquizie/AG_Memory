from __future__ import annotations

from dataclasses import dataclass, replace
import re

from ah.agent import InteractionContext
from ah.integration.contracts import IntegrationCommit
from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from ah.model import FunctionSymbol, Ref, RefKind
from ah.perception import (
    ActRelationCandidate,
    ActantCandidate,
    AssociationActRelationCandidate,
    AssociationEndpointSelector,
    CommandCandidate,
    PerceptionResult,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
)

from .contracts import AssociationGoal
from .modal_dispatch import ModalTurnGoalCompiler
from .query_builder import QueryBuildResult


@dataclass(frozen=True, slots=True)
class AssociationQueryBuildResult(QueryBuildResult):
    """GoalCompiler result executed by AssociationCoordinator, never InferenceEngine."""

    association_goal: AssociationGoal | None = None


@dataclass(frozen=True, slots=True)
class _EndpointResolution:
    ref: Ref | None
    support_refs: tuple[Ref, ...] = ()
    diagnostic: str | None = None


class AssociationTurnGoalCompiler(ModalTurnGoalCompiler):
    """Compile typed ASSOCIATION acts into AssociationGoal(A, B).

    Perception owns only association intent and parser-local endpoint selection.
    Canonicalization here is read-only and source-grounded: local proposition refs
    become their already integrated N/g, entity descriptions use EntityResolver,
    and a missing entity may fall back only to an already indexed lexical S. The
    compiler never creates M/g/T/N and never scans AH for a merely plausible node.
    """

    _LEXICAL_FORM_RE = re.compile(r"^[^\W_]+(?:[-'][^\W_]+)*$", re.UNICODE)

    @staticmethod
    def _selected_candidate(
        root: QueryCandidate | CommandCandidate,
        selector: AssociationEndpointSelector,
    ) -> ActantCandidate | None:
        matches = tuple(item for item in root.actants if item.role is selector.role)
        if len(matches) != 1:
            return None
        actant = matches[0]
        if selector.member_index is None:
            return None if actant.composition is not None else actant
        if actant.composition is None:
            return None
        if selector.member_index >= len(actant.composition.members):
            return None
        member = actant.composition.members[selector.member_index]
        return ActantCandidate(
            role=actant.role,
            mention=member.mention,
            normalized_hint=member.normalized_hint,
            semantic_hint=member.semantic_hint,
            evidence=member.evidence,
        )

    @staticmethod
    def _local_ref_map(integration: IntegrationCommit) -> dict[str, Ref]:
        refs = {item.local_id: item.ref for item in integration.assertions}
        refs.update({item.local_id: item.ref for item in integration.formulas})
        refs.update({item.local_id: item.ref for item in integration.quantified_queries})
        return refs

    def _resolve_formula_ref(
        self,
        expr: PropositionExprCandidate,
        integration: IntegrationCommit,
        attention_refs: tuple[Ref, ...],
    ) -> _EndpointResolution:
        local_refs = self._local_ref_map(integration)
        if expr.operator is PropositionOperator.REF:
            assert expr.ref is not None
            ref = local_refs.get(expr.ref)
            if ref is None:
                return _EndpointResolution(
                    None,
                    diagnostic="semantic:association_endpoint_local_ref_missing",
                )
            if ref.kind is RefKind.L:
                return _EndpointResolution(
                    None,
                    diagnostic="semantic:association_endpoint_nonexcitable",
                )
            return _EndpointResolution(ref)

        members: list[Ref] = []
        supports: list[Ref] = []
        for member in expr.members:
            resolved = self._resolve_formula_ref(member, integration, attention_refs)
            if resolved.ref is None:
                return resolved
            members.append(resolved.ref)
            supports.extend(resolved.support_refs)

        function_id = (
            "NOT"
            if expr.operator is PropositionOperator.FALSE
            else expr.operator.value
        )
        if not members:
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_formula_empty",
            )

        # Reverse operand index gives only functions that already use the first
        # resolved operand. Filter that bounded set by exact operator+operand tuple;
        # no global function scan and no ensure_function write is permitted here.
        matches = tuple(
            parent
            for parent in self.core.store.function_parents(members[0].uid)
            if (
                isinstance(parent, FunctionSymbol)
                and parent.function_id.upper() == function_id
                and parent.operands == tuple(members)
            )
        )
        if len(matches) == 1:
            return _EndpointResolution(
                self.core.ref(matches[0].uid),
                tuple(dict.fromkeys(supports)),
            )
        if len(matches) > 1:
            active = {ref.uid for ref in attention_refs}
            active_matches = tuple(item for item in matches if item.uid in active)
            if len(active_matches) == 1:
                return _EndpointResolution(
                    self.core.ref(active_matches[0].uid),
                    tuple(dict.fromkeys(supports)),
                )
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_formula_ambiguous",
            )
        return _EndpointResolution(
            None,
            diagnostic="semantic:association_endpoint_formula_not_canonical",
        )

    def _lexical_symbol_ref(
        self,
        candidate: ActantCandidate,
        attention_refs: tuple[Ref, ...],
    ) -> _EndpointResolution:
        forms: list[str] = []
        for raw in (candidate.normalized_hint, candidate.mention):
            value = (raw or "").strip()
            if (
                value
                and self._LEXICAL_FORM_RE.fullmatch(value)
                and value.casefold() not in {item.casefold() for item in forms}
            ):
                forms.append(value)
        matches: dict[str, object] = {}
        for form in forms:
            for symbol in self.core.store.find_symbols_by_form(form):
                matches[symbol.uid] = symbol
        if len(matches) == 1:
            uid = next(iter(matches))
            return _EndpointResolution(self.core.ref(uid))
        if len(matches) > 1:
            active = {ref.uid for ref in attention_refs if ref.kind is RefKind.S}
            active_matches = tuple(uid for uid in matches if uid in active)
            if len(active_matches) == 1:
                return _EndpointResolution(self.core.ref(active_matches[0]))
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_symbol_ambiguous",
            )
        return _EndpointResolution(
            None,
            diagnostic="semantic:association_endpoint_not_found",
        )

    def _resolve_endpoint(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        integration: IntegrationCommit,
        attention_refs: tuple[Ref, ...],
    ) -> _EndpointResolution:
        if candidate.candidate_ref is not None:
            ref = self._local_ref_map(integration).get(candidate.candidate_ref)
            if ref is None:
                return _EndpointResolution(
                    None,
                    diagnostic="semantic:association_endpoint_local_ref_missing",
                )
            if ref.kind is RefKind.L:
                return _EndpointResolution(
                    None,
                    diagnostic="semantic:association_endpoint_nonexcitable",
                )
            return _EndpointResolution(ref)

        if candidate.proposition is not None:
            return self._resolve_formula_ref(
                candidate.proposition, integration, attention_refs
            )

        if not candidate.lookup_text:
            # entity_ref is parser-local identity/quantifier state, not a canonical
            # UID. Without source text or a proposition binding there is no safe
            # read-only canonicalization path here.
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_unresolved_handle",
            )

        resolved = EntityResolver(self.core).resolve(
            candidate,
            context,
            first_person_ref=context.user_ref,
            second_person_ref=context.self_ref,
            attention_refs=attention_refs,
        )
        if isinstance(resolved, ExistingEntity):
            return _EndpointResolution(resolved.ref, resolved.support_refs)
        if isinstance(resolved, AmbiguousEntityPlan):
            return _EndpointResolution(
                None,
                diagnostic=(
                    "semantic:association_endpoint_entity_ambiguous:"
                    f"{len(resolved.candidates)}"
                ),
            )
        if isinstance(resolved, EquivalentLiteralPlan):
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_literal_not_canonicalized",
            )
        if isinstance(resolved, NewEntityPlan):
            # A query must not create a semantic entity. A pre-existing lexical S is
            # nevertheless a legitimate excitable concept origin and is found by the
            # canonical form index, not by a whole-graph similarity search.
            return self._lexical_symbol_ref(candidate, attention_refs)
        return _EndpointResolution(
            None,
            diagnostic="semantic:association_endpoint_unresolved",
        )

    def _resolve_association_root(
        self,
        root: QueryCandidate | CommandCandidate,
        relation: ActRelationCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...] = (),
    ) -> AssociationQueryBuildResult:
        if not isinstance(relation, AssociationActRelationCandidate):
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_relation_contract_invalid",),
            )
        integration = getattr(self, "_association_integration", None)
        if not isinstance(integration, IntegrationCommit):
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_integration_context_missing",),
            )

        source_candidate = self._selected_candidate(root, relation.source_selector)
        target_candidate = self._selected_candidate(root, relation.target_selector)
        if source_candidate is None or target_candidate is None:
            return AssociationQueryBuildResult(
                None,
                ("semantic:association_endpoint_selector_invalid",),
            )

        endpoints: list[Ref] = []
        attention: list[Ref] = []
        seen: set[tuple[str, str]] = set()

        def add_attention(ref: Ref) -> None:
            key = (ref.kind.value, ref.uid)
            if key not in seen:
                seen.add(key)
                attention.append(ref)

        for ref in attention_refs:
            add_attention(ref)

        for candidate in (source_candidate, target_candidate):
            resolved = self._resolve_endpoint(
                candidate,
                context,
                integration,
                attention_refs,
            )
            if resolved.ref is None:
                suffix = f":{candidate.role.value}"
                diagnostic = resolved.diagnostic or "semantic:association_endpoint_unresolved"
                return AssociationQueryBuildResult(
                    None,
                    (diagnostic + suffix,),
                    tuple(attention),
                )
            endpoints.append(resolved.ref)
            add_attention(resolved.ref)
            for support in resolved.support_refs:
                add_attention(support)

        # Equal canonical origins are valid: expand(A) intersects expand(A) at
        # depth zero. Distinct parser selectors are enforced upstream, while the
        # coordinator intentionally owns this trivial convergence case.
        goal = AssociationGoal(endpoints[0], endpoints[1])
        return AssociationQueryBuildResult(
            None,
            ("semantic:association_goal",),
            tuple(attention),
            association_goal=goal,
        )

    def _resolve_query_relation(
        self,
        query: QueryCandidate,
        relation: ActRelationCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        if relation.canonical_relation_id == "ASSOCIATION":
            return self._resolve_association_root(
                query, relation, context, attention_refs
            )
        return super()._resolve_query_relation(
            query, relation, context, attention_refs
        )

    def build(
        self,
        integration: IntegrationCommit,
        context: InteractionContext,
        perception: PerceptionResult | None = None,
        attention_refs: tuple[Ref, ...] = (),
    ) -> tuple[QueryBuildResult, ...]:
        if perception is None:
            return super().build(
                integration,
                context,
                perception=None,
                attention_refs=attention_refs,
            )

        association_relations = {
            item.act_ref: item
            for item in perception.act_relations
            if item.canonical_relation_id == "ASSOCIATION"
        }
        association_command_ids = {
            item.local_id
            for item in perception.commands
            if item.local_id in association_relations and not item.quoted
        }

        base_perception = (
            perception
            if not association_command_ids
            else replace(
                perception,
                commands=tuple(
                    item
                    for item in perception.commands
                    if item.local_id not in association_command_ids
                ),
            )
        )

        previous_integration = getattr(self, "_association_integration", None)
        self._association_integration = integration
        try:
            results = list(
                super().build(
                    integration,
                    context,
                    base_perception,
                    attention_refs=attention_refs,
                )
            )
            for command in perception.commands:
                relation = association_relations.get(command.local_id)
                if relation is None or command.quoted:
                    continue
                results.append(
                    self._resolve_association_root(
                        command, relation, context, attention_refs
                    )
                )
            return tuple(results)
        finally:
            self._association_integration = previous_integration
