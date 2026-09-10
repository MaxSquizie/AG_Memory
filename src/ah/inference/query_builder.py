from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import Ref
from ah.perception import (
    ActRelationCandidate,
    AssertionStatus,
    PerceptionResult,
    PropositionExprCandidate,
    PropositionOperator,
    QueryCandidate,
    QueryMode,
)
from ah.integration.contracts import IntegrationCommit

from ah.integration.entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)

from .contracts import (
    AllOfGoal,
    CauseEntailmentGoal,
    ExistsGoal,
    GoalSpec,
    InferenceQuery,
    MultiRoleFillGoal,
    RelationGoal,
    RoleFillGoal,
)


@dataclass(frozen=True, slots=True)
class QueryBuildResult:
    goal: InferenceQuery | None
    diagnostics: tuple[str, ...] = ()
    # Runtime attention anchors discovered while resolving the query. This may
    # include the resolved referent and canonical supporting facts used by a
    # relational description (e.g. USER + ДРУГ -> N_ЕСТЬ -> МИША).
    attention_refs: tuple[Ref, ...] = ()


class QueryGoalBuilder:
    """Read-only QueryCandidate -> inference goal normalization for role/exists QA."""

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def _predicate_symbol_candidates(self, query: QueryCandidate):
        predicate = query.predicate
        lookup = predicate.lookup_form.strip()
        matches = self.core.store.find_symbols_by_form(lookup)
        if matches:
            return matches
        surface = predicate.surface.strip()
        if not surface:
            return ()
        if predicate.normalized_hint is not None and surface.casefold() != lookup.casefold():
            return ()
        return self.core.store.find_symbols_by_form(surface)

    def build(
        self,
        query: QueryCandidate,
        context: InteractionContext,
        identity_attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        required_roles = {a.role for a in query.actants}
        required_roles.update(query.requested_roles)
        selection = query.predicate.template_selection
        if selection is not None and selection.existing_template_uid is not None:
            # Sense resolution already happened against local UID-free options.
            # Trust the deterministic mapping, not another form->S->roles guess.
            try:
                template = self.core.store.get_template(selection.existing_template_uid)
                symbol = self.core.store.get_symbol(template.predicate.uid)
            except KeyError:
                return QueryBuildResult(None, ("selected_template_not_found",))
            lookup_forms = {item.casefold() for item in symbol.forms}
            surface = query.predicate.surface.strip()
            lookup = query.predicate.lookup_form.casefold()
            normalized_is_distinct = (
                query.predicate.normalized_hint is not None
                and surface
                and surface.casefold() != lookup
            )
            if normalized_is_distinct:
                predicate_matches = lookup in lookup_forms
            else:
                predicate_matches = (
                    lookup in lookup_forms
                    or surface.casefold() in lookup_forms
                )
            if not predicate_matches:
                return QueryBuildResult(None, ("selected_template_predicate_mismatch",))
            if not required_roles.issubset(set(template.roles)):
                return QueryBuildResult(None, ("selected_template_role_mismatch",))
        else:
            symbols = self._predicate_symbol_candidates(query)
            if not symbols:
                return QueryBuildResult(None, ("predicate_not_found",))
            templates = [
                t
                for symbol in symbols
                for t in self.core.store.find_templates_by_predicate(symbol.uid)
                if required_roles.issubset(set(t.roles))
            ]
            if len(templates) != 1:
                return QueryBuildResult(None, ("template_not_unique",))
            template = templates[0]

        resolver = EntityResolver(self.core)
        known: dict = {}
        discovered_attention_refs: list[Ref] = []
        for actant in query.actants:
            if actant.candidate_ref is not None:
                return QueryBuildResult(None, ("query_candidate_ref_not_supported_here",))
            resolution = resolver.resolve(
                actant,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                attention_refs=identity_attention_refs,
            )
            if not isinstance(resolution, ExistingEntity):
                if isinstance(resolution, AmbiguousEntityPlan):
                    diagnostic = f"ambiguous_actant:{actant.role.value}:{len(resolution.candidates)}"
                elif isinstance(resolution, EquivalentLiteralPlan):
                    diagnostic = f"equivalent_literal_not_canonicalized:{actant.role.value}"
                elif isinstance(resolution, NewEntityPlan):
                    diagnostic = f"actant_not_found:{actant.role.value}"
                else:
                    diagnostic = f"unresolved_actant:{actant.role.value}"
                return QueryBuildResult(None, (diagnostic,))
            known[actant.role] = resolution.ref
            for ref in (resolution.ref, *resolution.support_refs):
                if all(existing.uid != ref.uid for existing in discovered_attention_refs):
                    discovered_attention_refs.append(ref)

        tref = self.core.ref(template.uid)
        if query.query_mode is QueryMode.FILL_ROLE:
            if not query.requested_roles:
                return QueryBuildResult(None, ("requested_roles_missing",))
            if len(query.requested_roles) == 1:
                return QueryBuildResult(InferenceQuery(GoalSpec(RoleFillGoal(tref, known, query.requested_roles[0]))), attention_refs=tuple(discovered_attention_refs))
            return QueryBuildResult(InferenceQuery(GoalSpec(MultiRoleFillGoal(tref, known, query.requested_roles))), attention_refs=tuple(discovered_attention_refs))
        return QueryBuildResult(InferenceQuery(GoalSpec(ExistsGoal(tref, known))), attention_refs=tuple(discovered_attention_refs))


class SemanticGoalCompiler:
    """Compile semantic turn structure into typed deterministic inference goals.

    No surface word or intent marker selects an inference rule. Perception supplies
    speech-act scope, proposition composition and typed runtime relations; this
    compiler only resolves their local roles/refs against the canonical AH and
    constructs GoalSpec objects.
    """

    def __init__(self, core: AHCore, query_builder: QueryGoalBuilder | None = None) -> None:
        self.core = core
        self.query_builder = query_builder or QueryGoalBuilder(core)

    @staticmethod
    def _descendants(perception: PerceptionResult, root_ref: str) -> set[str]:
        adjacency: dict[str, list[str]] = {}
        for edge in perception.act_dependencies:
            if edge.kind.value == "QUOTED":
                continue
            adjacency.setdefault(edge.parent_ref, []).append(edge.child_ref)
        out: set[str] = set()
        queue = [root_ref]
        seen = {root_ref}
        while queue:
            parent = queue.pop()
            for child in adjacency.get(parent, ()):
                if child in seen:
                    continue
                seen.add(child)
                out.add(child)
                queue.append(child)
        return out

    def _build_direct_query(
        self,
        query: QueryCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...],
    ) -> QueryBuildResult:
        # Keep compatibility with injected test/custom builders that implement the
        # historical two-argument contract. The production QueryGoalBuilder accepts
        # the optional attention set used only for deterministic identity grounding.
        if isinstance(self.query_builder, QueryGoalBuilder):
            return self.query_builder.build(query, context, attention_refs)
        return self.query_builder.build(query, context)

    @staticmethod
    def _root_expressions(root) -> tuple[PropositionExprCandidate, ...]:
        expressions: list[PropositionExprCandidate] = []
        for actant in root.actants:
            if actant.proposition is not None:
                expressions.append(actant.proposition)
            elif actant.candidate_ref is not None:
                expressions.append(PropositionExprCandidate.ref_expr(actant.candidate_ref))
        return tuple(expressions)

    @staticmethod
    def _has_explicit_and(
        expressions: tuple[PropositionExprCandidate, ...], target_ids: set[str]
    ) -> bool:
        for expr in expressions:
            if (
                expr.operator is PropositionOperator.AND
                and set(expr.leaf_refs()) == target_ids
            ):
                return True
        return False

    @staticmethod
    def _explicit_modal_operator(
        expressions: tuple[PropositionExprCandidate, ...],
        target_ids: set[str],
    ) -> PropositionOperator | None:
        modal = {
            PropositionOperator.POSSIBLE,
            PropositionOperator.REQUIRED,
            PropositionOperator.PERMITTED,
        }

        def find(expr: PropositionExprCandidate) -> PropositionOperator | None:
            if (
                expr.operator in modal
                and set(expr.leaf_refs()) == target_ids
            ):
                return expr.operator
            for member in expr.members:
                found = find(member)
                if found is not None:
                    return found
            return None

        for expr in expressions:
            found = find(expr)
            if found is not None:
                return found
        return None

    @staticmethod
    def _has_explicit_alternative(
        expressions: tuple[PropositionExprCandidate, ...], target_ids: set[str]
    ) -> bool:
        for expr in expressions:
            if (
                expr.operator in {PropositionOperator.OR, PropositionOperator.XOR}
                and set(expr.leaf_refs()) == target_ids
            ):
                return True
        return False

    def _resolve_query_relation(
        self,
        query: QueryCandidate,
        relation: ActRelationCandidate,
        context: InteractionContext,
        attention_refs: tuple[Ref, ...] = (),
    ) -> QueryBuildResult:
        by_role = {item.role: item for item in query.actants}
        source_candidate = by_role.get(relation.source_role)
        target_candidate = by_role.get(relation.target_role)
        if source_candidate is None or target_candidate is None:
            return QueryBuildResult(None, ("semantic:relation_endpoint_missing",))

        resolver = EntityResolver(self.core)
        attention: list[Ref] = []
        endpoints: list[Ref] = []
        for candidate in (source_candidate, target_candidate):
            resolved = resolver.resolve(
                candidate,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                attention_refs=attention_refs,
            )
            if not isinstance(resolved, ExistingEntity):
                if isinstance(resolved, AmbiguousEntityPlan):
                    diagnostic = (
                        f"semantic:relation_endpoint_ambiguous:{candidate.role.value}:"
                        f"{len(resolved.candidates)}"
                    )
                elif isinstance(resolved, EquivalentLiteralPlan):
                    diagnostic = f"semantic:relation_endpoint_literal_not_canonicalized:{candidate.role.value}"
                elif isinstance(resolved, NewEntityPlan):
                    diagnostic = f"semantic:relation_endpoint_not_found:{candidate.role.value}"
                else:
                    diagnostic = f"semantic:relation_endpoint_unresolved:{candidate.role.value}"
                return QueryBuildResult(None, (diagnostic,))
            endpoints.append(resolved.ref)
            for ref in (resolved.ref, *resolved.support_refs):
                if all(existing.uid != ref.uid for existing in attention):
                    attention.append(ref)

        return QueryBuildResult(
            InferenceQuery(
                GoalSpec(RelationGoal(relation.canonical_relation_id, endpoints[0], endpoints[1]))
            ),
            (f"semantic:direct_relation:{relation.canonical_relation_id}",),
            tuple(attention),
        )

    def _ordinary_proposition_ref(self, integrated) -> Ref:
        """Map scoped proposition content back to its ordinary canonical N if known.

        EMBEDDED/QUOTED/CONDITIONAL mentions intentionally receive distinct N UIDs.
        Structural inference links, however, point at ordinary canonical situations.
        Matching by the canonical N signature (T + actants) is deterministic and does
        not assert a missing proposition: if no ordinary match exists, the scoped ref
        is returned and the reasoner will correctly fail to find a proof path.
        """
        if integrated.ref.kind.value != "N":
            return integrated.ref
        try:
            node = self.core.store.get_hypernode(integrated.ref.uid)
        except KeyError:
            return integrated.ref
        if not node.meta.get("semantic_scope"):
            return integrated.ref
        matches = [
            item for item in self.core.store.find_hypernodes_by_template(node.template.uid)
            if not item.meta.get("semantic_scope")
            and dict(item.actants) == dict(node.actants)
        ]
        if len(matches) == 1:
            return self.core.ref(matches[0].uid)
        return integrated.ref

    def _embedded_exists(
        self,
        integrated,
    ) -> QueryBuildResult:
        if integrated.ref.kind.value != "N":
            return QueryBuildResult(
                None,
                (f"semantic:embedded_unsupported:{integrated.ref.kind.value}",),
            )
        try:
            node = self.core.store.get_hypernode(integrated.ref.uid)
        except KeyError:
            return QueryBuildResult(None, ("semantic:embedded_target_missing",))
        attention: list[Ref] = []
        seen: set[str] = set()
        ground_actants = {
            role: value for role, value in node.actants.items() if isinstance(value, Ref)
        }
        if len(ground_actants) != len(node.actants):
            return QueryBuildResult(None, ("semantic:embedded_quantified_pattern",))
        for ref in ground_actants.values():
            if ref.uid not in seen:
                seen.add(ref.uid)
                attention.append(ref)
        return QueryBuildResult(
            InferenceQuery(GoalSpec(ExistsGoal(node.template, ground_actants))),
            ("evidence:embedded_proposition",),
            tuple(attention),
        )

    def _embedded_act_relation(
        self,
        integrated,
        relation: ActRelationCandidate,
    ) -> QueryBuildResult:
        if integrated.ref.kind.value != "N":
            return QueryBuildResult(None, ("semantic:relation_target_not_N",))
        try:
            node = self.core.store.get_hypernode(integrated.ref.uid)
        except KeyError:
            return QueryBuildResult(None, ("semantic:relation_target_missing",))
        source = node.actants.get(relation.source_role)
        target = node.actants.get(relation.target_role)
        if source is None or target is None:
            return QueryBuildResult(None, ("semantic:relation_endpoint_missing",))
        return QueryBuildResult(
            InferenceQuery(
                GoalSpec(RelationGoal(relation.canonical_relation_id, source, target))
            ),
            (f"semantic:embedded_relation:{relation.canonical_relation_id}",),
            (source, target),
        )

    @staticmethod
    def _merge_queries(
        parts: list[QueryBuildResult],
        *,
        conjunction: bool,
        diagnostic: str,
    ) -> list[QueryBuildResult]:
        valid = [item for item in parts if item.goal is not None]
        invalid = [item for item in parts if item.goal is None]
        if not conjunction or len(valid) < 2:
            return parts

        children = tuple(item.goal.goal.target for item in valid)
        premise_refs: list[Ref] = []
        attention_refs: list[Ref] = []
        seen_premises: set[str] = set()
        seen_attention: set[str] = set()
        diagnostics: list[str] = [diagnostic]
        for item in valid:
            diagnostics.extend(item.diagnostics)
            assert item.goal is not None
            for ref in item.goal.premise_refs:
                if ref.uid not in seen_premises:
                    seen_premises.add(ref.uid)
                    premise_refs.append(ref)
            for ref in item.attention_refs:
                if ref.uid not in seen_attention:
                    seen_attention.add(ref.uid)
                    attention_refs.append(ref)
        merged = QueryBuildResult(
            InferenceQuery(
                GoalSpec(AllOfGoal(children)),
                premise_refs=tuple(premise_refs),
            ),
            tuple(diagnostics),
            tuple(attention_refs),
        )
        return [merged, *invalid]

    def _compile_scope(
        self,
        *,
        root,
        target_ids: set[str],
        perception: PerceptionResult,
        integrated_by_id: dict[str, object],
    ) -> list[QueryBuildResult]:
        if not target_ids:
            return []

        expressions = self._root_expressions(root)
        modal_operator = self._explicit_modal_operator(
            expressions, target_ids
        )
        if modal_operator is not None:
            # Until a dedicated modal query goal exists, never compile M(P) as a
            # request to prove ordinary P. This is the query-side counterpart of
            # the canonical nonfactivity barrier in GroundFormulaReasoner.
            return [
                QueryBuildResult(
                    None,
                    (
                        f"semantic:{modal_operator.value}_goal_not_supported",
                    ),
                )
            ]
        if self._has_explicit_alternative(expressions, target_ids):
            operator = next(
                (
                    expr.operator.value
                    for expr in expressions
                    if expr.operator in {
                        PropositionOperator.OR, PropositionOperator.XOR
                    }
                    and set(expr.leaf_refs()) == target_ids
                ),
                "ALTERNATIVE",
            )
            return [
                QueryBuildResult(
                    None,
                    (f"semantic:{operator}_goal_not_supported",),
                )
            ]
        explicit_and = self._has_explicit_and(expressions, target_ids)
        parts: list[QueryBuildResult] = []
        covered: set[str] = set()

        act_relation_by_ref = {item.act_ref: item for item in perception.act_relations}
        for local_id in sorted(target_ids):
            relation = act_relation_by_ref.get(local_id)
            integrated = integrated_by_id.get(local_id)
            if relation is None or integrated is None:
                continue
            parts.append(self._embedded_act_relation(integrated, relation))
            covered.add(local_id)

        assertion_by_id = {item.local_id: item for item in perception.assertions}
        for relation in perception.relations:
            source_item = assertion_by_id.get(relation.source_ref)
            target_item = assertion_by_id.get(relation.target_ref)
            source_integrated = integrated_by_id.get(relation.source_ref)
            target_integrated = integrated_by_id.get(relation.target_ref)
            if source_item is None or target_item is None or source_integrated is None or target_integrated is None:
                continue

            source_is_target = relation.source_ref in target_ids
            target_is_target = relation.target_ref in target_ids
            if source_is_target and target_is_target:
                # The semantic target is the structural relation itself. CAUSE is
                # intentionally *not* made transitive here; that would invent a rule
                # the architecture explicitly rejects.
                parts.append(
                    QueryBuildResult(
                        InferenceQuery(
                            GoalSpec(
                                RelationGoal(
                                    relation.canonical_relation_id,
                                    self._ordinary_proposition_ref(source_integrated),
                                    self._ordinary_proposition_ref(target_integrated),
                                )
                            )
                        ),
                        (f"semantic:situation_relation:{relation.canonical_relation_id}",),
                        (
                            self._ordinary_proposition_ref(source_integrated),
                            self._ordinary_proposition_ref(target_integrated),
                        ),
                    )
                )
                covered.update((relation.source_ref, relation.target_ref))
                continue

            if (
                relation.canonical_relation_id == "CAUSE"
                and not source_is_target
                and target_is_target
                and source_item.status is AssertionStatus.ASSERTED
            ):
                # Here the source proposition is actually asserted/given in this
                # turn, while the effect is epistemic content. This is the MP-style
                # CAUSE goal used by the reasoner, with the source as an explicit
                # premise. Multi-hop CAUSE remains rule-driven inside the engine.
                parts.append(
                    QueryBuildResult(
                        InferenceQuery(
                            GoalSpec(CauseEntailmentGoal(self._ordinary_proposition_ref(target_integrated))),
                            premise_refs=(self._ordinary_proposition_ref(source_integrated),),
                        ),
                        ("semantic:cause_entailment",),
                        (
                            self._ordinary_proposition_ref(source_integrated),
                            self._ordinary_proposition_ref(target_integrated),
                        ),
                    )
                )
                covered.add(relation.target_ref)

        for local_id in sorted(target_ids - covered):
            integrated = integrated_by_id.get(local_id)
            if integrated is not None:
                parts.append(self._embedded_exists(integrated))

        return self._merge_queries(
            parts,
            conjunction=explicit_and,
            diagnostic="semantic:explicit_AND",
        )

    def build(
        self,
        integration: IntegrationCommit,
        context: InteractionContext,
        perception: PerceptionResult | None = None,
        attention_refs: tuple[Ref, ...] = (),
    ) -> tuple[QueryBuildResult, ...]:
        # Compatibility for callers that only have IntegrationCommit: only
        # explicit user queries are inference goals.  An "EMBEDDED" assertion is
        # semantic content of another act, not a request to prove that content.
        # Without PerceptionResult we cannot establish a QUERY/COMMAND dependency
        # root, so compiling orphan EMBEDDED facts would turn ordinary statements
        # into hidden inference requests and pollute the public query outcomes.
        if perception is None:
            return tuple(
                self._build_direct_query(query, context, attention_refs)
                for query in integration.unresolved_queries
            )

        integrated_by_id = {item.local_id: item for item in integration.assertions}
        assertion_by_id = {item.local_id: item for item in perception.assertions}
        act_relation_by_ref = {item.act_ref: item for item in perception.act_relations}
        results: list[QueryBuildResult] = []
        covered_embedded: set[str] = set()

        roots = [
            item for item in (*perception.queries, *perception.commands)
            if item.local_id is not None and not item.quoted
        ]
        unresolved_query_by_id = {
            item.local_id: item
            for item in integration.unresolved_queries
            if item.local_id is not None
        }

        for root in roots:
            descendants = self._descendants(perception, root.local_id)
            target_ids = {
                local_id
                for local_id in descendants
                if local_id in assertion_by_id
                and assertion_by_id[local_id].status is AssertionStatus.EMBEDDED
                and not assertion_by_id[local_id].quoted
            }
            if target_ids:
                scope_results = self._compile_scope(
                    root=root,
                    target_ids=target_ids,
                    perception=perception,
                    integrated_by_id=integrated_by_id,
                )
                results.extend(scope_results)
                covered_embedded.update(target_ids)
                continue

            # A direct EXISTS query may itself be a typed structural relation.
            if isinstance(root, QueryCandidate):
                resolved_query = unresolved_query_by_id.get(root.local_id, root)
                relation = act_relation_by_ref.get(root.local_id)
                if relation is not None:
                    results.append(
                        self._resolve_query_relation(
                            resolved_query, relation, context, attention_refs
                        )
                    )
                else:
                    results.append(self._build_direct_query(resolved_query, context, attention_refs))

        # Queries without local ids cannot participate in structural dependency
        # scoping but remain valid ordinary role/exists queries.
        for query in integration.unresolved_queries:
            if query.local_id is None:
                results.append(self._build_direct_query(query, context, attention_refs))

        # No orphan-EMBEDDED fallback by design.  Only descendants of an explicit
        # QUERY/COMMAND root above become inference goals.  Embedded content under
        # an ASSERTION remains memory content/premise material and must never show
        # up as a user query merely because its semantic scope is EMBEDDED.
        return tuple(results)


# Compatibility name retained for external/tests written before semantic goal
# compilation grew beyond QueryCandidate/ExistsGoal.
TurnGoalBuilder = SemanticGoalCompiler
