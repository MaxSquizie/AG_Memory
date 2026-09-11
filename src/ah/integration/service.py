from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import re

from ah.config import IntegrationSettings
from ah.conflict import ConflictEngine

from ah.agent import ExistentialDiscourseAnchor, InteractionContext
from ah.core import AHCore
from ah.core.signatures import hypernode_signature
from ah.model import (
    ActantRole, BoundVar, Domain, FunctionSymbol, Group, Hypernode, Property, Ref,
    RefKind, SemanticEntity, Template, VariableSort,
)
from ah.perception.scoping import apply_speech_act_scoping
from ah.inference.schema import InferenceSchemaRegistry
from ah.temporal import StateTracker, ensure_time_entity, exact_datetime_from_ref
from ah.perception.morphology import Morphology, build_morphology, material_analyses
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QueryQuantifierOperator,
    StructuralClarificationSpec,
    NominalRelationKind,
    TemplateCandidate,
    TemplateSelection,
)

from .candidate_validator import CandidateValidator
from .contracts import (
    ActivationSeedRequest,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResolutionCommit,
    ClarificationUse,
    IdentityMergeResult,
    IntegratedAssertion,
    IntegratedConditional,
    IntegratedExistential,
    IntegratedFormula,
    IntegratedQuantifiedQuery,
    IntegratedConflict,
    IntegratedRelation,
    IntegrationCommit,
    RefutationRequest,
    SeedReason,
    TemplateRequest,
    TemplateSenseOption,
)
from .correction import SemanticCorrectionService
from .domain_router import DomainRouter
from .entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    EquivalentLiteralPlan,
    ExistingEntity,
    NewEntityPlan,
)
from .errors import (
    CandidateValidationError, IntegrationError, UnresolvedDiscourseReferenceError,
    UnresolvedTemporalReferenceError,
)
from .experience_mapper import ExperienceMapper
from .formalization import BatchKind, FormalizationBatch, MutationPlan, SemanticConsolidator
from .template_resolver import TemplateResolver


_ENTITY_PRONOUNS = {
    "я", "мы", "ты", "вы", "он", "она", "оно", "они",
    "меня", "мне", "мной", "нас", "нам", "нами",
    "тебя", "тебе", "тобой", "вас", "вам", "вами",
    "его", "ему", "им", "неё", "нее", "ей", "ею", "её",
    "их", "им", "ими",
}

# Cross-turn discourse anchors deliberately cover only nominative third-person
# personal pronouns.  These forms are morphologically unambiguous enough to be
# carried in InteractionContext without inventing a second coreference engine.
# Oblique/possessive forms remain with the richer local coreference machinery until
# a role-aware cross-turn ambiguity representation is implemented.
_NOMINATIVE_PRONOUN_BY_SIGNATURE: dict[tuple[str, str | None], str] = {
    ("sing", "masc"): "он",
    ("sing", "femn"): "она",
    ("sing", "neut"): "оно",
    ("plur", None): "они",
}


@dataclass(frozen=True, slots=True)
class _CompositionPlan:
    operator: str
    members: tuple[Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan, ...]


@dataclass(frozen=True, slots=True)
class _ReferenceAlternativesPlan:
    """Canonicalization plan for one role with several runtime entity readings."""

    mention: str
    members: tuple[
        tuple[str | None, Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan], ...
    ]


@dataclass(frozen=True, slots=True)
class IntegrationConfig:
    initial_hypernode_weight: float
    experience_hypernode_weight: float
    follow_link_weight: float
    cause_link_weight: float = 0.2
    is_a_link_weight: float = 0.2
    nominal_relation_link_weight: float = 0.2

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_hypernode_weight", self.initial_hypernode_weight),
            ("experience_hypernode_weight", self.experience_hypernode_weight),
            ("follow_link_weight", self.follow_link_weight),
            ("cause_link_weight", self.cause_link_weight),
            ("is_a_link_weight", self.is_a_link_weight),
            ("nominal_relation_link_weight", self.nominal_relation_link_weight),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    @classmethod
    def from_settings(cls, settings: IntegrationSettings) -> "IntegrationConfig":
        return cls(
            initial_hypernode_weight=settings.initial_hypernode_weight,
            experience_hypernode_weight=settings.experience_hypernode_weight,
            follow_link_weight=settings.follow_link_weight,
            cause_link_weight=settings.cause_link_weight,
            is_a_link_weight=settings.is_a_link_weight,
            nominal_relation_link_weight=settings.nominal_relation_link_weight,
        )


class IntegrationService:
    def __init__(
        self,
        core: AHCore,
        config: IntegrationConfig,
        *,
        discourse_morphology: Morphology | None = None,
        schema_registry: InferenceSchemaRegistry | None = None,
    ) -> None:
        self.core = core
        self.config = config
        self.schema_registry = schema_registry or InferenceSchemaRegistry.default()
        self.validator = CandidateValidator()
        # Runtime discourse anchoring uses dictionary morphology only. It does not
        # create canonical identity or semantic relations. Injection is supported
        # for deterministic tests; production follows the same auto morphology as
        # the parser environment.
        self._discourse_morphology = discourse_morphology or build_morphology("auto")
        self.consolidator = SemanticConsolidator(
            self.validator, morphology=self._discourse_morphology
        )

    @staticmethod
    def _predicate_occurrence_key(predicate, source_context: str) -> tuple[object, ...]:
        evidence = predicate.evidence
        return (
            predicate.lookup_form.casefold(),
            None if evidence is None else evidence.start,
            None if evidence is None else evidence.end,
            (predicate.sense_hint or "").casefold(),
            source_context,
        )

    @staticmethod
    def _is_structural_predicate_sense(predicate) -> bool:
        hint = (predicate.sense_hint or "").strip().upper()
        return hint == "IMPLICIT" or hint.startswith("STRUCTURAL_")

    def _predicate_symbol_candidates(self, predicate) -> tuple:
        """Return lexical S candidates without collapsing a homographic surface.

        A semantic/morphological ``normalized_hint`` is stronger than the observed
        surface for lexical identity.  If that normalized lexeme is not known yet,
        we deliberately do *not* fall back to a different S merely because it shares
        the surface wordform: Integration may need to create a new lexical S for the
        newly resolved paradigm.
        """
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

    def _template_ref_label(self, ref: Ref) -> str:
        """Return a UID-free semantic label for one canonical reference."""
        try:
            if ref.kind is RefKind.M:
                entity = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(entity, SemanticEntity):
                    name = entity.properties.get("name")
                    if name is not None and isinstance(name.value, str) and name.value.strip():
                        return name.value.strip()
                    aliases = entity.properties.get("aliases")
                    if aliases is not None:
                        raw = aliases.value
                        if isinstance(raw, str) and raw.strip():
                            return raw.strip()
                        if isinstance(raw, (tuple, list, set, frozenset)) and raw:
                            return str(next(iter(raw)))
                return "entity"
            if ref.kind is RefKind.G:
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, FunctionSymbol):
                    return element.function_id
                return "functional expression"
            if ref.kind is RefKind.K:
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, Group):
                    name = element.properties.get("name")
                    if name is not None and isinstance(name.value, str) and name.value.strip():
                        return name.value.strip()
                return "group"
            if ref.kind is RefKind.N:
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, Hypernode):
                    template = self.core.store.get_template(element.template.uid)
                    symbol = self.core.store.get_symbol(template.predicate.uid)
                    form = sorted(symbol.forms, key=lambda item: (len(item), item.casefold()))[0]
                    return f"{form} situation"
                return "situation"
            if ref.kind is RefKind.S:
                symbol = self.core.store.get_symbol(ref.uid)
                return sorted(symbol.forms, key=lambda item: (len(item), item.casefold()))[0]
            if ref.kind is RefKind.T:
                template = self.core.store.get_template(ref.uid)
                symbol = self.core.store.get_symbol(template.predicate.uid)
                return sorted(symbol.forms, key=lambda item: (len(item), item.casefold()))[0]
        except (KeyError, ValueError):
            pass
        return ref.kind.value.lower()

    def _template_sense_description(self, template: Template) -> str:
        roles = ", ".join(role.value for role in template.roles) or "no explicit roles"
        examples: list[str] = []
        for element in self.core.store.all_elements():
            if (
                not isinstance(element, Hypernode)
                or element.template.uid != template.uid
                or element.meta.get("semantic_scope")
            ):
                continue
            bindings = ", ".join(
                f"{role.value}={self._template_ref_label(ref)}"
                for role, ref in element.actants.items()
                if isinstance(ref, Ref)
            )
            if bindings:
                examples.append(bindings)
            if len(examples) >= 2:
                break
        if examples:
            return f"roles: {roles}; observed uses: " + " | ".join(examples)
        return f"roles: {roles}; no observed fact example yet"

    def template_requests(self, result: PerceptionResult) -> tuple[TemplateRequest, ...]:
        """Return runtime schema/sense decisions required before integration.

        Unknown predicates still request only an explicit ``TemplateCandidate``.
        Known lexical predicates additionally receive a bounded sense-resolution
        request. Existing T are exposed to Perception only through local labels and
        UID-free usage summaries; the orchestrator maps the chosen label back to a
        canonical T. This is what prevents a new sense with the same role set from
        being silently collapsed into an old T.
        """
        grouped: dict[tuple[object, ...], dict[str, object]] = {}

        def binding_text(actant: ActantCandidate) -> str | None:
            if actant.lookup_text:
                return actant.lookup_text
            if actant.composition is not None:
                joiner = f" {actant.composition.operator.value} "
                return joiner.join(member.lookup_text for member in actant.composition.members)
            if actant.candidate_ref is not None:
                return "[nested situation]"
            if actant.entity_ref is not None:
                return "[context-resolved entity]"
            return None

        def add(
            predicate,
            actants: tuple[ActantCandidate, ...],
            *,
            extra_roles: tuple[ActantRole, ...] = (),
            source_context: str | None = None,
        ) -> None:
            context_text = source_context or result.source_text
            key = self._predicate_occurrence_key(predicate, context_text)
            entry = grouped.get(key)
            if entry is None:
                entry = {
                    "predicate": predicate,
                    "roles": [],
                    "has_candidate": predicate.template_candidate is not None,
                    "source_context": context_text,
                    "bindings": [],
                }
                grouped[key] = entry
            else:
                entry["has_candidate"] = bool(entry["has_candidate"]) or predicate.template_candidate is not None

            roles = entry["roles"]
            bindings = entry["bindings"]
            assert isinstance(roles, list) and isinstance(bindings, list)
            for actant in actants:
                if actant.role not in roles:
                    roles.append(actant.role)
                value = binding_text(actant)
                pair = (actant.role, value) if value else None
                if pair is not None and pair not in bindings:
                    bindings.append(pair)
            for role in extra_roles:
                if role not in roles:
                    roles.append(role)

        for assertion in result.assertions:
            variants = (assertion, *assertion.alternatives)
            for variant in variants:
                add(
                    variant.predicate,
                    variant.actants,
                    source_context=(variant.evidence.text if variant.evidence is not None else result.source_text),
                )
        for query in result.queries:
            add(
                query.predicate, query.actants,
                extra_roles=query.requested_roles, source_context=result.source_text
            )
        for command in result.commands:
            add(command.predicate, command.actants, source_context=result.source_text)

        requests: list[TemplateRequest] = []
        for entry in grouped.values():
            predicate = entry["predicate"]
            roles = entry["roles"]
            has_candidate = bool(entry["has_candidate"])
            source_context = str(entry["source_context"])
            bindings = entry["bindings"]
            assert isinstance(roles, list) and isinstance(bindings, list)

            if predicate.template_selection is not None:
                continue

            symbols = self._predicate_symbol_candidates(predicate)
            existing = tuple(
                template
                for symbol in symbols
                for template in self.core.store.find_templates_by_predicate(symbol.uid)
            )
            required_roles = set(roles)
            compatible = tuple(
                template for template in existing
                if required_roles.issubset(set(template.roles))
            )

            if existing and not self._is_structural_predicate_sense(predicate):
                # Narrow deterministically by the roles already extracted from the
                # current act before asking Perception to choose a lexical sense.
                # A sense that cannot host the explicit roles is not a semantic
                # candidate for this occurrence.
                sense_candidates = compatible or existing
                options = tuple(
                    TemplateSenseOption(
                        label=f"C{index}",
                        template_uid=template.uid,
                        description=self._template_sense_description(template),
                    )
                    for index, template in enumerate(sense_candidates, start=1)
                )
                requests.append(
                    TemplateRequest(
                        predicate,
                        tuple(roles),
                        source_context,
                        tuple(bindings),
                        options,
                    )
                )
                continue

            if existing:
                # Structural/implicit predicates are not exempt from semantic
                # ambiguity. If more than one canonical T can host the already
                # parsed roles, leaving template_selection empty later makes a
                # perfectly valid polar query fail with ``template_not_unique`` and
                # lets the language model answer from ACTIVE MEMORY without proof.
                # Resolve only that genuinely remaining ambiguity with the same
                # UID-free bounded sense protocol used for lexical predicates.
                if len(compatible) > 1:
                    options = tuple(
                        TemplateSenseOption(
                            label=f"C{index}",
                            template_uid=template.uid,
                            description=self._template_sense_description(template),
                        )
                        for index, template in enumerate(compatible, start=1)
                    )
                    requests.append(
                        TemplateRequest(
                            predicate,
                            tuple(roles),
                            source_context,
                            tuple(bindings),
                            options,
                        )
                    )
                continue
            if has_candidate:
                continue
            requests.append(
                TemplateRequest(
                    predicate,
                    tuple(roles),
                    source_context,
                    tuple(bindings),
                )
            )
        return tuple(requests)

    @staticmethod
    def _emit_plan_diagnostics(plan: MutationPlan, *, source: str) -> None:
        from ah.diagnostics.session_log import emit

        ir = plan.candidate_ir
        emit(
            "pipeline_candidate_ir",
            source=source,
            source_text=ir.source_text,
            batch_kind=ir.batch_kind.value,
            source_ref=ir.source_ref,
            ordered_assertion_ids=list(ir.ordered_assertion_ids),
            discourse_refs=[item.local_id for item in ir.discourse_refs],
            existential_variable_ids=[item.variable_id for item in ir.existential_bindings],
            universal_variable_ids=[item.variable_id for item in ir.universal_bindings],
            unresolved_temporal_refs=[item.local_id for item in ir.temporal_refs],
            query_count=len(ir.perception.queries),
            quantified_query_count=sum(
                1 for item in ir.perception.queries
                if item.quantified is not None
            ),
            command_count=len(ir.perception.commands),
            relation_count=len(ir.perception.relations),
            conditional_count=len(ir.perception.conditionals),
        )
        emit(
            "pipeline_mutation_plan",
            source=source,
            forced_domain=None if plan.forced_domain is None else plan.forced_domain.value,
            speaker_uid=plan.speaker_ref.uid,
            existing_experience_uid=(
                None if plan.existing_experience_ref is None else plan.existing_experience_ref.uid
            ),
            ordered_assertion_ids=list(ir.ordered_assertion_ids),
        )

    def prepare_external_plan(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        batch_kind: BatchKind = BatchKind.MESSAGE,
        source_ref: str | None = None,
        source_timestamp: datetime | None = None,
        existing_experience_ref: Ref | None = None,
    ) -> MutationPlan:
        """Build the complete validated staging plan without mutating canonical AH."""
        if context.user_ref is None:
            raise IntegrationError("External integration requires context.user_ref")
        plan = self.consolidator.prepare(
            result,
            speaker_ref=context.user_ref,
            forced_domain=None,
            context=context,
            existing_experience_ref=existing_experience_ref,
            batch_kind=batch_kind,
            source_ref=source_ref,
            source_timestamp=source_timestamp,
            experience_timestamp=(
                exact_datetime_from_ref(self.core, context.now_ref)
                if context.now_ref is not None else None
            ),
        )
        self._emit_plan_diagnostics(plan, source="EXTERNAL")
        return plan

    def prepare_external_batch_plan(
        self,
        batch: FormalizationBatch,
        context: InteractionContext,
        *,
        existing_experience_ref: Ref | None = None,
    ) -> MutationPlan:
        """Validate/consolidate a complete message/document batch before writing AH."""
        if context.user_ref is None:
            raise IntegrationError("External integration requires context.user_ref")
        plan = self.consolidator.prepare_batch(
            batch,
            speaker_ref=context.user_ref,
            forced_domain=None,
            context=context,
            existing_experience_ref=existing_experience_ref,
            experience_timestamp=(
                exact_datetime_from_ref(self.core, context.now_ref)
                if context.now_ref is not None else None
            ),
        )
        self._emit_plan_diagnostics(plan, source="EXTERNAL_BATCH")
        return plan

    def integrate_external_batch(
        self,
        batch: FormalizationBatch,
        context: InteractionContext,
    ) -> IntegrationCommit:
        return self.integrate_plan(self.prepare_external_batch_plan(batch, context), context)

    def prepare_h_plan(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        batch_kind: BatchKind = BatchKind.MESSAGE,
        source_ref: str | None = None,
        source_timestamp: datetime | None = None,
    ) -> MutationPlan:
        if context.self_ref is None:
            raise IntegrationError("H-only agent integration requires context.self_ref")
        plan = self.consolidator.prepare(
            result,
            speaker_ref=context.self_ref,
            forced_domain=Domain.H,
            context=context,
            batch_kind=batch_kind,
            source_ref=source_ref,
            source_timestamp=source_timestamp,
            experience_timestamp=(
                exact_datetime_from_ref(self.core, context.now_ref)
                if context.now_ref is not None else None
            ),
        )
        self._emit_plan_diagnostics(plan, source="AGENT_H")
        return plan

    def bind_discourse_ref(
        self,
        plan: MutationPlan,
        discourse_ref_id: str,
        entity_ref: str,
        context: InteractionContext,
    ) -> MutationPlan:
        """Apply an explicit batch-local discourse binding without touching AH."""
        return self.consolidator.bind_discourse_ref(
            plan, discourse_ref_id, entity_ref, context=context
        )

    def integrate_plan(
        self,
        plan: MutationPlan,
        context: InteractionContext,
    ) -> IntegrationCommit:
        """Execute one immutable plan through a single canonical transaction.

        An unresolved ``DiscourseRef`` is staging state, not a semantic entity.
        Failing closed here prevents an unbound personal pronoun from silently
        becoming ``m_ОН``/``m_ОНА`` merely because EntityResolver needs a filler.
        The caller may retain the plan for later document consolidation or request
        clarification; no canonical mutation has happened yet.
        """
        if plan.candidate_ir.discourse_refs:
            raise UnresolvedDiscourseReferenceError(plan.candidate_ir.discourse_refs)
        if plan.candidate_ir.temporal_refs:
            raise UnresolvedTemporalReferenceError(plan.candidate_ir.temporal_refs)
        return self._integrate_plan(plan, context)

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        source_timestamp: datetime | None = None,
    ) -> IntegrationCommit:
        return self.integrate_plan(
            self.prepare_external_plan(
                result,
                context,
                source_timestamp=source_timestamp,
            ),
            context,
        )

    def integrate_external_resolution(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        existing_experience_ref: Ref,
    ) -> IntegrationCommit:
        """Integrate delayed semantics into the original external H experience."""
        plan = self.prepare_external_plan(
            result, context, existing_experience_ref=existing_experience_ref
        )
        return self.integrate_plan(plan, context)

    def integrate_to_h(
        self,
        result: PerceptionResult,
        context: InteractionContext,
    ) -> IntegrationCommit:
        return self.integrate_plan(self.prepare_h_plan(result, context), context)

    def integrate_discourse_relation(
        self,
        relation_id: str,
        source: Ref,
        target: Ref,
    ) -> IntegratedRelation:
        """Materialize one validated cross-turn relation between semantic events.

        The semantic selector is runtime-only and UID-free.  This method is the
        deterministic trust boundary that maps its local decision back to canonical
        AH refs.  Only ordinary asserted C/P hypernodes are eligible; H dialogue
        event carriers and EMBEDDED/CONDITIONAL/QUOTED propositions cannot become
        world CAUSE/FOLLOW endpoints through discourse refinement.
        """
        canonical_relation = relation_id.strip().upper()
        if canonical_relation not in {"CAUSE", "FOLLOW"}:
            raise IntegrationError(
                f"Unsupported discourse relation: {relation_id!r}"
            )
        if source == target:
            raise IntegrationError("Discourse relation cannot be reflexive")

        with self.core.transaction() as tx:
            for label, ref in (("source", source), ("target", target)):
                if ref.kind is not RefKind.N or not tx.store.has_uid(ref.uid):
                    raise IntegrationError(
                        f"Discourse relation {label} must be an existing canonical N"
                    )
                domain = tx.store.domain_of(ref.uid)
                if domain not in {Domain.C, Domain.P}:
                    raise IntegrationError(
                        f"Discourse relation {label} must belong to C/P semantic memory"
                    )
                node = tx.store.get_hypernode(ref.uid)
                if bool(node.meta.get("event_instance", False)):
                    raise IntegrationError(
                        f"Discourse relation {label} cannot be an H dialogue event"
                    )
                if node.meta.get("semantic_scope") is not None:
                    raise IntegrationError(
                        f"Discourse relation {label} must be ordinary asserted content"
                    )

            # FOLLOW is interpreted transitively by the reasoner.  Creating an edge
            # that closes a directed FOLLOW cycle would violate that semantics even
            # if the model selected it, so reject it deterministically.
            if canonical_relation == "FOLLOW":
                agenda = [target.uid]
                visited: set[str] = set()
                while agenda:
                    uid = agenda.pop()
                    if uid == source.uid:
                        raise IntegrationError("Discourse FOLLOW would create a cycle")
                    if uid in visited:
                        continue
                    visited.add(uid)
                    agenda.extend(
                        link.target.uid
                        for link in tx.store.outgoing_links(uid, "FOLLOW")
                    )

            weight = (
                self.config.cause_link_weight
                if canonical_relation == "CAUSE"
                else self.config.follow_link_weight
            )
            link, created = tx.ensure_link(
                canonical_relation,
                source,
                target,
                weight,
            )
            return IntegratedRelation(
                relation_id=canonical_relation,
                source=source,
                target=target,
                ref=tx.ref(link.uid),
                created=created,
            )

    @staticmethod
    def _materialize_proposition_expr(
        core: AHCore,
        expr: PropositionExprCandidate,
        local_refs: dict[str, Ref],
        forced_domain: Domain | None,
    ) -> tuple[Ref, bool]:
        """Materialize one validated proposition AST without asserting its leaves."""
        if expr.operator is PropositionOperator.REF:
            assert expr.ref is not None
            try:
                return local_refs[expr.ref], False
            except KeyError as exc:
                raise CandidateValidationError(
                    f"proposition ref not integrated yet: {expr.ref}"
                ) from exc
        members: list[Ref] = []
        created_any = False
        for member in expr.members:
            ref, created = IntegrationService._materialize_proposition_expr(
                core, member, local_refs, forced_domain
            )
            members.append(ref)
            created_any = created_any or created
        domain = (
            forced_domain
            if forced_domain is not None
            else DomainRouter(core).route_external(tuple(members))
        )
        function_id = (
            "NOT"
            if expr.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}
            else expr.operator.value
        )
        function, created = core.ensure_function(domain, function_id, tuple(members))
        return core.ref(function.uid), created_any or created

    def _integrate_plan(
        self,
        plan: MutationPlan,
        context: InteractionContext,
    ) -> IntegrationCommit:
        # All source-level scoping and graph validation has already happened in the
        # immutable MutationPlan. Canonical UID allocation and entity/template
        # materialization start only inside the transaction below.
        result = plan.perception
        ordered = plan.ordered_assertions
        forced_domain = plan.forced_domain
        speaker_ref = plan.speaker_ref
        existing_experience_ref = plan.existing_experience_ref

        assertions: list[IntegratedAssertion] = []
        seeds: list[ActivationSeedRequest] = []
        refutations: list[RefutationRequest] = []
        relations: list[IntegratedRelation] = []
        conditionals: list[IntegratedConditional] = []
        formulas: list[IntegratedFormula] = []
        existentials: list[IntegratedExistential] = []
        universals: list[IntegratedExistential] = []
        quantified_queries: list[IntegratedQuantifiedQuery] = []
        conflicts: list[IntegratedConflict] = []
        local_refs: dict[str, Ref] = {}
        entity_local_refs: dict[str, Ref] = {}
        entity_anchors = self._entity_anchors(result)
        existential_bindings = {
            item.entity_ref: item for item in plan.candidate_ir.existential_bindings
        }
        universal_bindings = {
            item.entity_ref: item for item in plan.candidate_ir.universal_bindings
        }
        existential_vars = {
            item.entity_ref: BoundVar(item.variable_id, item.sort)
            for item in plan.candidate_ir.existential_bindings
        }
        universal_vars = {
            item.entity_ref: BoundVar(item.variable_id, item.sort)
            for item in plan.candidate_ir.universal_bindings
        }
        bound_vars = {**existential_vars, **universal_vars}

        assertion_by_id = {item.local_id: item for item in ordered}
        ordinary_formula_roots = tuple(
            root
            for root in result.proposition_roots
            if not all(
                assertion_by_id[ref].status is AssertionStatus.CONDITIONAL
                for ref in root.expression.leaf_refs()
            )
        )
        formula_leaf_ids = {
            ref for root in ordinary_formula_roots for ref in root.expression.leaf_refs()
        }
        formula_operator_source_ids = {
            ref for root in ordinary_formula_roots for ref in root.operator_source_refs
        }

        def candidate_bound_refs(
            candidate: AssertionCandidate, mapping: dict[str, BoundVar]
        ) -> tuple[str, ...]:
            refs: list[str] = []
            variants = candidate.alternatives or (candidate,)
            for variant in variants:
                for actant in variant.actants:
                    if actant.entity_ref in mapping and actant.entity_ref not in refs:
                        refs.append(actant.entity_ref)
            return tuple(refs)

        existential_assertion_vars = {
            candidate.local_id: candidate_bound_refs(candidate, existential_vars)
            for candidate in ordered
            if candidate_bound_refs(candidate, existential_vars)
        }
        universal_assertion_vars = {
            candidate.local_id: candidate_bound_refs(candidate, universal_vars)
            for candidate in ordered
            if candidate_bound_refs(candidate, universal_vars)
        }
        overlap = set(existential_assertion_vars) & set(universal_assertion_vars)
        if overlap:
            raise CandidateValidationError(
                "One assertion cannot mix existential and universal participants: "
                + ", ".join(sorted(overlap))
            )
        experience_ref: Ref | None = None
        resolved_queries = []
        resolved_commands = []

        with self.core.transaction() as tx:
            addressee_ref = context.self_ref if speaker_ref == context.user_ref else context.user_ref
            local_domain_overrides = self._local_assertion_domain_overrides(
                tx,
                ordered,
                context,
                forced_domain=forced_domain,
                speaker_ref=speaker_ref,
                addressee_ref=addressee_ref,
            )
            # Query mentions do not create world facts, but canonical maintenance
            # may still repair an already-existing literal identity collision. A
            # NUMBER(5) duplicated across C/P is one value, not a clarification
            # choice. This pass never creates an unseen literal from a question.
            literal_resolver = EntityResolver(tx)
            for semantic_act in (*result.queries, *result.commands):
                for actant in semantic_act.actants:
                    if (
                        actant.candidate_ref is not None
                        or actant.entity_ref is not None
                        or actant.composition is not None
                        or actant.proposition is not None
                    ):
                        continue
                    literal_plan = literal_resolver.resolve(
                        actant,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                    )
                    if isinstance(literal_plan, EquivalentLiteralPlan):
                        self._materialize_equivalent_literal(tx, literal_plan)

            # Predicate/T resolution precedes actant/entity resolution for every
            # semantic act, not only assertions. Query/Command candidates do not
            # create N facts here, but an unknown predicate can still register the
            # validated representational T required by downstream query/behavioral
            # handling.
            for query in result.queries:
                selection = query.predicate.template_selection
                if selection is not None and selection.existing_template_uid is not None:
                    # Queries may ask for an explicit missing role, but their known
                    # fillers are not authoritative evidence for expanding an
                    # existing canonical valency.  TemplateCompletion has already
                    # reconciled known fillers against the selected T where
                    # possible; any remaining out-of-schema label must fail closed
                    # in QueryGoalBuilder rather than permanently mutating T.
                    selected = tx.store.get_template(selection.existing_template_uid)
                    selected_roles = set(selected.roles)
                    query_roles = [
                        actant.role for actant in query.actants
                        if actant.role in selected_roles
                    ]
                else:
                    query_roles = [actant.role for actant in query.actants]
                for requested_role in query.requested_roles:
                    if requested_role not in query_roles:
                        query_roles.append(requested_role)
                resolution = TemplateResolver(tx, template_domain=Domain.C).resolve(
                    query.predicate, tuple(query_roles)
                )
                resolved_queries.append(
                    replace(
                        query,
                        predicate=replace(
                            query.predicate,
                            template_selection=TemplateSelection(
                                existing_template_uid=resolution.template.uid
                            ),
                        ),
                    )
                )
            for command in result.commands:
                resolution = TemplateResolver(tx, template_domain=Domain.C).resolve(
                    command.predicate, tuple(actant.role for actant in command.actants)
                )
                resolved_commands.append(
                    replace(
                        command,
                        predicate=replace(
                            command.predicate,
                            template_selection=TemplateSelection(
                                existing_template_uid=resolution.template.uid
                            ),
                        ),
                    )
                )

            for candidate in ordered:
                # Some matrix frames are consumed by a validated logical wrapper
                # (for example a truth-negating construction).  They are linguistic
                # operator evidence, not independent world propositions.
                if candidate.local_id in formula_operator_source_ids:
                    continue

                formula_leaf = candidate.local_id in formula_leaf_ids
                quantified = (
                    candidate.local_id in existential_assertion_vars
                    or candidate.local_id in universal_assertion_vars
                )
                if quantified:
                    # A quantified participant is not a semantic entity. Source
                    # assertions become QUANTIFIED pattern N and are asserted only
                    # through EXISTS/FORALL formulae built after the connected
                    # component exists.
                    if (
                        candidate.quoted
                        or candidate.status is not AssertionStatus.ASSERTED
                        or candidate.transition_operator is not None
                    ):
                        raise CandidateValidationError(
                            "Quantified discourse participants are currently supported only "
                            "in ordinary asserted, non-transition propositions"
                        )
                    integrated = self._integrate_assertion(
                        tx,
                        candidate,
                        context,
                        local_refs,
                        entity_local_refs,
                        local_domain_overrides.get(candidate.local_id, forced_domain),
                        entity_anchors=entity_anchors,
                        speaker_ref=speaker_ref,
                        addressee_ref=addressee_ref,
                        count_occurrence=False,
                        semantic_scope="QUANTIFIED",
                        existential_vars=bound_vars,
                    )
                    proposition_ref = integrated.ref
                    created = integrated.created
                    if candidate.negated:
                        not_g, not_created = tx.ensure_function(
                            integrated.domain, "NOT", (proposition_ref,)
                        )
                        proposition_ref = tx.ref(not_g.uid)
                        created = created or not_created
                    final = IntegratedAssertion(
                        local_id=integrated.local_id,
                        ref=proposition_ref,
                        domain=integrated.domain,
                        created=created,
                        ambiguous=integrated.ambiguous,
                        semantic_scope="QUANTIFIED",
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    continue

                # Quoted proposition content is canonicalized so a matrix speech
                # predicate may reference it, but it is never an ordinary asserted
                # world fact. Quotation is orthogonal to conditional status.
                if candidate.quoted:
                    integrated = self._integrate_assertion(
                        tx,
                        candidate,
                        context,
                        local_refs,
                        entity_local_refs,
                        local_domain_overrides.get(candidate.local_id, forced_domain),
                        entity_anchors=entity_anchors,
                        speaker_ref=speaker_ref,
                        addressee_ref=addressee_ref,
                        count_occurrence=False,
                        semantic_scope="QUOTED",
                    )
                    proposition_ref = integrated.ref
                    created = integrated.created
                    if candidate.negated:
                        not_g, not_created = tx.ensure_function(
                            integrated.domain, "NOT", (proposition_ref,)
                        )
                        proposition_ref = tx.ref(not_g.uid)
                        created = created or not_created
                    final = IntegratedAssertion(
                        local_id=integrated.local_id,
                        ref=proposition_ref,
                        domain=integrated.domain,
                        created=created,
                        ambiguous=integrated.ambiguous,
                        semantic_scope="QUOTED",
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    continue

                # Embedded / hypothetical / modal proposition content must exist
                # canonically for matrix references, but mention/scope alone does
                # not assert it as an ordinary world fact.  The scope is attached
                # to the proposition N, not smuggled into truth/confidence fields.
                if candidate.status in {
                    AssertionStatus.EMBEDDED,
                    AssertionStatus.HYPOTHETICAL,
                    AssertionStatus.MODAL,
                }:
                    semantic_scope = "LOGICAL" if formula_leaf else candidate.status.value
                    integrated = self._integrate_assertion(
                        tx, candidate, context, local_refs, entity_local_refs,
                        local_domain_overrides.get(candidate.local_id, forced_domain),
                        entity_anchors=entity_anchors, speaker_ref=speaker_ref,
                        addressee_ref=addressee_ref, count_occurrence=False,
                        semantic_scope=semantic_scope,
                    )
                    proposition_ref = integrated.ref
                    created = integrated.created
                    if candidate.negated and not formula_leaf:
                        not_g, not_created = tx.ensure_function(
                            integrated.domain, "NOT", (proposition_ref,)
                        )
                        proposition_ref = tx.ref(not_g.uid)
                        created = created or not_created
                    final = IntegratedAssertion(
                        local_id=integrated.local_id, ref=proposition_ref,
                        domain=integrated.domain, created=created,
                        ambiguous=integrated.ambiguous, semantic_scope=semantic_scope,
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    continue

                # Conditional branches are propositions under a semantic operator,
                # not ordinary world assertions. Skip them here; they are
                # canonicalized below as scoped operands of g_IMPLIES.
                if candidate.status is not AssertionStatus.ASSERTED:
                    continue

                if candidate.transition_operator is not None:
                    if candidate.negated:
                        raise CandidateValidationError(
                            "Negated transition wrapper is not a canonical state transition"
                        )
                    integrated = self._integrate_assertion(
                        tx,
                        candidate,
                        context,
                        local_refs,
                        entity_local_refs,
                        local_domain_overrides.get(candidate.local_id, forced_domain),
                        entity_anchors=entity_anchors,
                        speaker_ref=speaker_ref,
                        addressee_ref=addressee_ref,
                        count_occurrence=False,
                        semantic_scope="TRANSITION_OPERAND",
                    )
                    node = tx.store.get_hypernode(integrated.ref.uid)
                    time_ref = node.actants.get(ActantRole.TIME)
                    if isinstance(time_ref, Ref) and time_ref.kind is RefKind.M:
                        transition_ref = StateTracker(
                            tx, default_weight=self.config.initial_hypernode_weight
                        ).apply(
                            integrated.ref,
                            candidate.transition_operator,
                            time_ref,
                        ).transition_ref
                        transition_created = True
                    else:
                        # The transition proposition itself is source-explicit even
                        # when no calendar anchor is stated.  Materialize g_OP(P)
                        # without inventing a TIME point or mutating state intervals;
                        # StateTracker remains the sole authority for interval
                        # effects once an explicit/resolved TIME exists.
                        transition_g, transition_created = tx.ensure_function(
                            integrated.domain,
                            candidate.transition_operator.value,
                            (integrated.ref,),
                        )
                        transition_ref = tx.ref(transition_g.uid)
                    final = IntegratedAssertion(
                        local_id=integrated.local_id,
                        ref=transition_ref,
                        domain=integrated.domain,
                        created=integrated.created or transition_created,
                        ambiguous=integrated.ambiguous,
                        semantic_scope=("LOGICAL" if formula_leaf else None),
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    if not formula_leaf:
                        seeds.append(ActivationSeedRequest(final.ref, SeedReason.NEW_FACT))
                    continue

                integrated = self._integrate_assertion(
                    tx,
                    candidate,
                    context,
                    local_refs,
                    entity_local_refs,
                    local_domain_overrides.get(candidate.local_id, forced_domain),
                    entity_anchors=entity_anchors,
                    speaker_ref=speaker_ref,
                    addressee_ref=addressee_ref,
                    count_occurrence=(not candidate.negated and not formula_leaf),
                    semantic_scope=("LOGICAL" if formula_leaf else None),
                )

                if candidate.negated and formula_leaf:
                    # Local negation is represented explicitly inside the
                    # PropositionExprCandidate AST.  Keep REF(local_id) bound to
                    # the positive scoped N so NOT scope is materialized exactly
                    # once at the formula root.
                    assertions.append(integrated)
                    local_refs[candidate.local_id] = integrated.ref
                elif candidate.negated:
                    # Object-level negation is canonical NOT(P), not FALSE(N).
                    # FALSE is reserved for explicit correction/refutation of one
                    # already stored proposition/support.  A negative statement
                    # therefore does not trigger correction plasticity on P.
                    not_g, not_created = tx.ensure_function(
                        integrated.domain, "NOT", (integrated.ref,)
                    )
                    not_ref = tx.ref(not_g.uid)
                    final = IntegratedAssertion(
                        local_id=integrated.local_id,
                        ref=not_ref,
                        domain=integrated.domain,
                        created=integrated.created or not_created,
                        ambiguous=integrated.ambiguous,
                        semantic_scope=("LOGICAL" if formula_leaf else None),
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    if not formula_leaf:
                        seeds.append(
                            ActivationSeedRequest(
                                not_ref,
                                SeedReason.NEW_FACT if not_created else SeedReason.REACTIVATED_FACT,
                            )
                        )
                else:
                    assertions.append(integrated)
                    local_refs[candidate.local_id] = integrated.ref
                    if not formula_leaf:
                        seeds.append(
                            ActivationSeedRequest(
                                integrated.ref,
                                SeedReason.NEW_FACT if integrated.created else SeedReason.REACTIVATED_FACT,
                            )
                        )

            # Build asserted existential formulae from connected components of
            # batch-local unknown participants.  An assertion that shares two
            # existential handles joins their variables into one scope; disconnected
            # unknowns remain separate EXISTS roots rather than being conflated.
            if existential_assertion_vars:
                parent = {key: key for key in existential_vars}

                def find(key: str) -> str:
                    while parent[key] != key:
                        parent[key] = parent[parent[key]]
                        key = parent[key]
                    return key

                def union(left: str, right: str) -> None:
                    lroot, rroot = find(left), find(right)
                    if lroot != rroot:
                        parent[rroot] = lroot

                for refs in existential_assertion_vars.values():
                    if refs:
                        for ref_id in refs[1:]:
                            union(refs[0], ref_id)

                components: dict[str, set[str]] = {}
                for ref_id in existential_vars:
                    components.setdefault(find(ref_id), set()).add(ref_id)

                for root_id in sorted(components, key=lambda item: existential_vars[item].local_id):
                    variable_refs = components[root_id]
                    member_ids = tuple(
                        candidate.local_id
                        for candidate in ordered
                        if variable_refs.intersection(existential_assertion_vars.get(candidate.local_id, ()))
                    )
                    if not member_ids:
                        continue
                    current_member_refs = tuple(local_refs[item] for item in member_ids)
                    prior_member_refs: list[Ref] = []
                    prior_anchor_refs: set[Ref] = set()
                    for variable_ref in variable_refs:
                        binding = existential_bindings[variable_ref]
                        if binding.anchor_ref is None:
                            continue
                        if not tx.store.has_uid(binding.anchor_ref.uid):
                            raise CandidateValidationError(
                                "Cross-turn existential anchor no longer exists in canonical AH"
                            )
                        prior_anchor_refs.add(binding.anchor_ref)
                        for member_ref in binding.anchor_member_refs:
                            if not tx.store.has_uid(member_ref.uid):
                                raise CandidateValidationError(
                                    "Cross-turn existential member no longer exists in canonical AH"
                                )
                            if member_ref not in prior_member_refs:
                                prior_member_refs.append(member_ref)
                    if len(prior_anchor_refs) > 1:
                        raise CandidateValidationError(
                            "One existential component cannot silently merge distinct cross-turn scopes"
                        )
                    member_refs = tuple(
                        dict.fromkeys((*prior_member_refs, *current_member_refs))
                    )
                    domain = (
                        forced_domain
                        if forced_domain is not None
                        else DomainRouter(tx).route_external(member_refs)
                    )
                    body_ref = member_refs[0]
                    created_any = False
                    if len(member_refs) > 1:
                        and_g, and_created = tx.ensure_function(domain, "AND", member_refs)
                        body_ref = tx.ref(and_g.uid)
                        created_any = created_any or and_created
                    ordered_vars = tuple(
                        sorted((existential_vars[item] for item in variable_refs), key=lambda var: var.local_id)
                    )
                    for variable in reversed(ordered_vars):
                        handle = next(
                            item
                            for item in variable_refs
                            if existential_vars[item].local_id == variable.local_id
                        )
                        restriction_lemma = existential_bindings[
                            handle
                        ].restriction_lemma
                        if restriction_lemma:
                            restriction = self._ensure_class_pattern(
                                tx,
                                restriction_lemma,
                                variable,
                                domain,
                            )
                            restricted_g, restricted_created = tx.ensure_function(
                                domain, "AND", (restriction, body_ref)
                            )
                            body_ref = tx.ref(restricted_g.uid)
                            created_any = created_any or restricted_created
                        exists_g, exists_created = tx.ensure_function(
                            domain, "EXISTS", (variable, body_ref)
                        )
                        body_ref = tx.ref(exists_g.uid)
                        created_any = created_any or exists_created
                    if any(existential_bindings[item].negative for item in variable_refs):
                        if not all(existential_bindings[item].negative for item in variable_refs):
                            raise CandidateValidationError(
                                "Cannot mix negative and positive existential binders in one scope"
                            )
                        not_g, not_created = tx.ensure_function(domain, "NOT", (body_ref,))
                        body_ref = tx.ref(not_g.uid)
                        created_any = created_any or not_created
                    existentials.append(
                        IntegratedExistential(
                            ref=body_ref,
                            member_refs=member_refs,
                            variable_ids=tuple(item.local_id for item in ordered_vars),
                            created=created_any,
                        )
                    )
                    seeds.append(
                        ActivationSeedRequest(
                            body_ref,
                            SeedReason.NEW_FACT if created_any else SeedReason.REACTIVATED_FACT,
                        )
                    )

            if universal_assertion_vars:
                parent = {key: key for key in universal_vars}

                def ufind(key: str) -> str:
                    while parent[key] != key:
                        parent[key] = parent[parent[key]]
                        key = parent[key]
                    return key

                def uunion(left: str, right: str) -> None:
                    lroot, rroot = ufind(left), ufind(right)
                    if lroot != rroot:
                        parent[rroot] = lroot

                for refs in universal_assertion_vars.values():
                    if refs:
                        for ref_id in refs[1:]:
                            uunion(refs[0], ref_id)

                u_components: dict[str, set[str]] = {}
                for ref_id in universal_vars:
                    u_components.setdefault(ufind(ref_id), set()).add(ref_id)

                for root_id in sorted(u_components, key=lambda item: universal_vars[item].local_id):
                    variable_refs = u_components[root_id]
                    member_ids = tuple(
                        candidate.local_id
                        for candidate in ordered
                        if variable_refs.intersection(universal_assertion_vars.get(candidate.local_id, ()))
                    )
                    if not member_ids:
                        continue
                    member_refs = tuple(local_refs[item] for item in member_ids)
                    domain = (
                        forced_domain
                        if forced_domain is not None
                        else DomainRouter(tx).route_external(member_refs)
                    )
                    body_ref = member_refs[0]
                    created_any = False
                    if len(member_refs) > 1:
                        and_g, and_created = tx.ensure_function(domain, "AND", member_refs)
                        body_ref = tx.ref(and_g.uid)
                        created_any = created_any or and_created
                    ordered_vars = tuple(
                        sorted((universal_vars[item] for item in variable_refs), key=lambda var: var.local_id)
                    )
                    negate_quantifier = any(
                        universal_bindings[item].negate_quantifier for item in variable_refs
                    )
                    if negate_quantifier and len(ordered_vars) > 1:
                        raise CandidateValidationError(
                            "«не все» is supported only for a single quantified variable"
                        )
                    for variable in reversed(ordered_vars):
                        handle = next(
                            item for item in variable_refs if universal_vars[item].local_id == variable.local_id
                        )
                        restriction = self._ensure_class_pattern(
                            tx,
                            universal_bindings[handle].restriction_lemma,
                            variable,
                            domain,
                        )
                        implies_g, implies_created = tx.ensure_function(
                            domain, "IMPLIES", (restriction, body_ref)
                        )
                        body_ref = tx.ref(implies_g.uid)
                        created_any = created_any or implies_created
                        forall_g, forall_created = tx.ensure_function(
                            domain, "FORALL", (variable, body_ref)
                        )
                        body_ref = tx.ref(forall_g.uid)
                        created_any = created_any or forall_created
                    if negate_quantifier:
                        not_g, not_created = tx.ensure_function(domain, "NOT", (body_ref,))
                        body_ref = tx.ref(not_g.uid)
                        created_any = created_any or not_created
                    universals.append(
                        IntegratedExistential(
                            ref=body_ref,
                            member_refs=member_refs,
                            variable_ids=tuple(item.local_id for item in ordered_vars),
                            created=created_any,
                        )
                    )
                    seeds.append(
                        ActivationSeedRequest(
                            body_ref,
                            SeedReason.NEW_FACT if created_any else SeedReason.REACTIVATED_FACT,
                        )
                    )

            # Quantified queries are canonicalized only as non-occurring formula
            # targets. They deliberately reuse the same QUANTIFIED pattern identity
            # as quantified assertions, so an exact previously asserted formula can
            # be recognized by the reasoner. The query turn itself is never attached
            # to H as assertion evidence for this formula.
            for query in resolved_queries:
                spec = query.quantified
                if spec is None:
                    continue
                if query.local_id is None:
                    raise CandidateValidationError(
                        "Quantified query reached Integration without local_id"
                    )
                selection = query.predicate.template_selection
                if selection is None or selection.existing_template_uid is None:
                    continue
                try:
                    template = tx.store.get_template(
                        selection.existing_template_uid
                    )
                except KeyError:
                    continue

                variables = {
                    binding.entity_ref: BoundVar(
                        binding.variable_id, binding.sort
                    )
                    for binding in spec.bindings
                }
                query_actants: dict[ActantRole, Ref | BoundVar] = {}
                query_resolution_failed = False
                resolver = EntityResolver(tx)

                for actant in query.actants:
                    variable = variables.get(actant.entity_ref or "")
                    if variable is not None:
                        query_actants[actant.role] = variable
                        continue

                    if (
                        actant.candidate_ref is not None
                        or actant.composition is not None
                        or actant.proposition is not None
                    ):
                        query_resolution_failed = True
                        break

                    if (
                        actant.entity_ref is not None
                        and actant.entity_ref in entity_local_refs
                    ):
                        query_actants[actant.role] = entity_local_refs[
                            actant.entity_ref
                        ]
                        continue

                    resolved = resolver.resolve(
                        actant,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                    )
                    if not isinstance(resolved, ExistingEntity):
                        # Ordinary unresolved queries fail at GoalCompiler rather
                        # than inventing entities. Quantified queries keep exactly
                        # the same policy: no M is created merely to ask a question.
                        query_resolution_failed = True
                        break
                    query_actants[actant.role] = resolved.ref

                if query_resolution_failed:
                    continue

                concrete_refs = tuple(
                    value
                    for value in query_actants.values()
                    if isinstance(value, Ref)
                )
                query_domain = (
                    forced_domain
                    if forced_domain is not None
                    else DomainRouter(tx).route_external(concrete_refs)
                )
                body_node, body_created = tx.add_or_enrich_hypernode(
                    query_domain,
                    tx.ref(template.uid),
                    query_actants,
                    weight=self.config.initial_hypernode_weight,
                    meta={"semantic_scope": "QUANTIFIED"},
                    count_occurrence=False,
                )
                body_member_ref = tx.ref(body_node.uid)
                body_ref = body_member_ref
                created_any = body_created

                if spec.body_negated:
                    not_g, not_created = tx.ensure_function(
                        query_domain, "NOT", (body_ref,)
                    )
                    body_ref = tx.ref(not_g.uid)
                    created_any = created_any or not_created

                for binding in reversed(spec.bindings):
                    variable = variables[binding.entity_ref]
                    if binding.restriction_lemma is not None:
                        restriction = self._ensure_class_pattern(
                            tx,
                            binding.restriction_lemma,
                            variable,
                            query_domain,
                        )
                        connective = (
                            "IMPLIES"
                            if binding.operator is QueryQuantifierOperator.FORALL
                            else "AND"
                        )
                        scoped_g, scoped_created = tx.ensure_function(
                            query_domain,
                            connective,
                            (restriction, body_ref),
                        )
                        body_ref = tx.ref(scoped_g.uid)
                        created_any = created_any or scoped_created

                    quantifier_g, quantifier_created = tx.ensure_function(
                        query_domain,
                        binding.operator.value,
                        (variable, body_ref),
                    )
                    body_ref = tx.ref(quantifier_g.uid)
                    created_any = created_any or quantifier_created

                    if binding.negated:
                        not_g, not_created = tx.ensure_function(
                            query_domain, "NOT", (body_ref,)
                        )
                        body_ref = tx.ref(not_g.uid)
                        created_any = created_any or not_created

                quantified_queries.append(
                    IntegratedQuantifiedQuery(
                        local_id=query.local_id,
                        ref=body_ref,
                        member_refs=(body_member_ref,),
                        variable_ids=tuple(
                            binding.variable_id for binding in spec.bindings
                        ),
                        created=created_any,
                    )
                )

            # Materialize top-level logical formula roots only after every leaf
            # proposition has a canonical scoped ref.  The H occurrence will assert
            # these roots; leaf N/G refs deliberately remain non-occurring operands.
            for root in ordinary_formula_roots:
                root_ref, created = self._materialize_proposition_expr(
                    tx, root.expression, local_refs, forced_domain
                )
                member_refs = tuple(
                    local_refs[ref] for ref in root.expression.leaf_refs()
                )
                formulas.append(
                    IntegratedFormula(
                        local_id=root.local_id,
                        ref=root_ref,
                        member_refs=member_refs,
                        created=created,
                    )
                )
                seeds.append(
                    ActivationSeedRequest(
                        root_ref,
                        SeedReason.NEW_FACT if created else SeedReason.REACTIVATED_FACT,
                    )
                )

            # Conditional branches are canonical proposition content but are not
            # ordinary asserted world facts.  Integrate them as scoped N/G operands,
            # then bind the antecedent and consequent through deterministic IMPLIES.
            # A multi-member side uses AND, preserving conjunction semantics such as
            # (A AND B) -> C instead of the incorrect pairwise A->C / B->C reading.
            conditional_local_refs: dict[str, Ref] = {}
            conditional_assertions_by_id = {
                item.local_id: item
                for item in ordered
                if item.status is AssertionStatus.CONDITIONAL
            }
            for conditional in result.conditionals:
                endpoint_ids = tuple(dict.fromkeys((*conditional.antecedent_refs, *conditional.consequent_refs)))
                for local_id in endpoint_ids:
                    if local_id in conditional_local_refs:
                        continue
                    candidate = conditional_assertions_by_id[local_id]
                    if candidate.quoted and local_id in local_refs:
                        conditional_local_refs[local_id] = local_refs[local_id]
                        continue
                    integrated = self._integrate_assertion(
                        tx,
                        candidate,
                        context,
                        {**local_refs, **conditional_local_refs},
                        entity_local_refs,
                        local_domain_overrides.get(candidate.local_id, forced_domain),
                        entity_anchors=entity_anchors,
                        speaker_ref=speaker_ref,
                        addressee_ref=addressee_ref,
                        count_occurrence=False,
                        semantic_scope="CONDITIONAL",
                    )
                    proposition_ref = integrated.ref
                    if candidate.negated:
                        not_g, _not_created = tx.ensure_function(
                            integrated.domain, "NOT", (proposition_ref,)
                        )
                        proposition_ref = tx.ref(not_g.uid)
                    conditional_local_refs[local_id] = proposition_ref

                antecedent_members = tuple(conditional_local_refs[item] for item in conditional.antecedent_refs)
                consequent_members = tuple(conditional_local_refs[item] for item in conditional.consequent_refs)

                def materialize_expr(
                    expr: PropositionExprCandidate | None,
                    fallback: tuple[str, ...],
                ) -> Ref:
                    if expr is None:
                        expr = (
                            PropositionExprCandidate.ref_expr(fallback[0])
                            if len(fallback) == 1
                            else PropositionExprCandidate(
                                PropositionOperator.AND,
                                members=tuple(
                                    PropositionExprCandidate.ref_expr(ref)
                                    for ref in fallback
                                ),
                            )
                        )
                    ref, _created = self._materialize_proposition_expr(
                        tx, expr, conditional_local_refs, forced_domain
                    )
                    return ref

                antecedent_ref = materialize_expr(
                    conditional.antecedent_expr, conditional.antecedent_refs
                )
                consequent_ref = materialize_expr(
                    conditional.consequent_expr, conditional.consequent_refs
                )
                conditional_domain = (
                    forced_domain
                    if forced_domain is not None
                    else DomainRouter(tx).route_external((antecedent_ref, consequent_ref))
                )
                function, created = tx.ensure_function(
                    conditional_domain, "IMPLIES", (antecedent_ref, consequent_ref)
                )
                conditional_ref = tx.ref(function.uid)
                conditionals.append(
                    IntegratedConditional(
                        ref=conditional_ref,
                        antecedent=antecedent_ref,
                        consequent=consequent_ref,
                        created=created,
                        member_refs=antecedent_members + consequent_members,
                    )
                )
                quoted_conditional = all(
                    conditional_assertions_by_id[item].quoted
                    for item in endpoint_ids
                )
                if not quoted_conditional:
                    seeds.append(
                        ActivationSeedRequest(
                            conditional_ref,
                            SeedReason.NEW_FACT if created else SeedReason.REACTIVATED_FACT,
                        )
                    )

            # Structural L truth is emitted only from ASSERTED, non-quoted content.
            # EMBEDDED/CONDITIONAL/QUOTED propositions may still be canonicalized as
            # scoped N for reference, but a relation mentioned inside a question or
            # command must never become the fact that later proves that same target.
            assertion_by_id = {item.local_id: item for item in ordered}

            # Intra-act structural relations (currently IS-A) use already resolved
            # semantic role bindings from the integrated N. Perception supplied only
            # relation type + endpoint roles; canonical UID resolution stays here.
            for relation in result.act_relations:
                candidate = assertion_by_id.get(relation.act_ref)
                if (
                    candidate is None
                    or candidate.quoted
                    or candidate.status is not AssertionStatus.ASSERTED
                    or relation.act_ref not in local_refs
                ):
                    continue
                proposition_ref = local_refs[relation.act_ref]
                if proposition_ref.kind is not RefKind.N:
                    continue
                node = tx.store.get_hypernode(proposition_ref.uid)
                source = node.actants.get(relation.source_role)
                target = node.actants.get(relation.target_role)
                if source is None or target is None:
                    raise IntegrationError(
                        f"Missing canonical act-relation endpoint in {relation.act_ref}"
                    )
                link, created = tx.ensure_link(
                    relation.canonical_relation_id,
                    source,
                    target,
                    self.config.is_a_link_weight,
                )
                relations.append(
                    IntegratedRelation(
                        relation_id=relation.canonical_relation_id,
                        source=source,
                        target=target,
                        ref=tx.ref(link.uid),
                        created=created,
                    )
                )

            # Directional inter-situation relations are likewise world truth only
            # when both endpoint situations are ordinary asserted facts.
            for relation in result.relations:
                source_candidate = assertion_by_id.get(relation.source_ref)
                target_candidate = assertion_by_id.get(relation.target_ref)
                if (
                    source_candidate is None
                    or target_candidate is None
                    or source_candidate.quoted
                    or target_candidate.quoted
                    or source_candidate.status is not AssertionStatus.ASSERTED
                    or target_candidate.status is not AssertionStatus.ASSERTED
                    or relation.source_ref not in local_refs
                    or relation.target_ref not in local_refs
                ):
                    continue
                source = local_refs[relation.source_ref]
                target = local_refs[relation.target_ref]
                relation_weight = (
                    self.config.cause_link_weight
                    if relation.canonical_relation_id == "CAUSE"
                    else self.config.follow_link_weight
                )
                link, created = tx.ensure_link(
                    relation.canonical_relation_id,
                    source,
                    target,
                    relation_weight,
                )
                relations.append(
                    IntegratedRelation(
                        relation_id=relation.canonical_relation_id,
                        source=source,
                        target=target,
                        ref=tx.ref(link.uid),
                        created=created,
                    )
                )

            mapper = ExperienceMapper(
                tx,
                event_weight=self.config.experience_hypernode_weight,
                follow_weight=self.config.follow_link_weight,
            )
            semantic_refs = (
                tuple(
                    item.ref
                    for item in assertions
                    if item.semantic_scope != "QUANTIFIED"
                    and item.local_id not in formula_leaf_ids
                )
                + tuple(item.ref for item in formulas)
                + tuple(item.ref for item in conditionals)
                + tuple(item.ref for item in existentials)
                + tuple(item.ref for item in universals)
            )
            if existing_experience_ref is None:
                experience = mapper.record_turn(
                    source_text=result.source_text,
                    speaker_ref=speaker_ref,
                    semantic_refs=semantic_refs,
                    context=context,
                    speech_act_kinds=self._speech_act_kinds(result),
                    source_ref=plan.candidate_ir.source_ref,
                    batch_kind=plan.candidate_ir.batch_kind.value,
                )
                experience_ref = experience.event_ref
                seeds.append(ActivationSeedRequest(experience.event_ref, SeedReason.EXPERIENCE))
            else:
                experience = mapper.attach_content(existing_experience_ref, semantic_refs)
                experience_ref = experience.event_ref

            # Conflict detection runs only after the H occurrence is attached.  A
            # compound g carries no ad-hoc asserted flag; its top-level assertion
            # status is derived from the user's experience occurrence.  The
            # ConflictEngine therefore sees the same canonical evidence that the
            # reasoner will later use and can create/reuse addressable k_CONFLICT
            # sets without choosing a winner.
            if forced_domain is None and assertions:
                conflict_engine = ConflictEngine(tx, self.schema_registry)
                conflict_records = conflict_engine.register_asserted_roots(
                    tuple(item.ref for item in assertions if item.semantic_scope is None)
                )
                for record in conflict_records:
                    conflicts.append(
                        IntegratedConflict(
                            ref=record.group_ref,
                            members=record.members,
                            kind=record.kind,
                            created=record.created,
                        )
                    )
                    seeds.append(
                        ActivationSeedRequest(record.group_ref, SeedReason.CONFLICT)
                    )

            # External language recognition has a second, post-semantic stage.
            # TextSensory can stimulate already-known surface candidates before
            # Perception, but an S created during this very turn does not exist yet
            # at that point (and homographs are intentionally unresolved). After
            # canonical integration we now know which predicate S actually
            # participated in the user's semantic acts, so stimulate those lexical
            # nodes strongly exactly once. Agent self-utterance integration is H-only
            # and must not feed this external sensory pathway.
            if forced_domain is None:
                resolved_symbols: dict[str, Ref] = {}
                visited: set[str] = set()

                def collect_predicate_symbols(ref: Ref) -> None:
                    if ref.uid in visited or not tx.store.has_uid(ref.uid):
                        return
                    visited.add(ref.uid)
                    kind = tx.store.kind_of(ref.uid)
                    if kind is RefKind.S:
                        resolved_symbols[ref.uid] = tx.ref(ref.uid)
                        return
                    if kind is RefKind.T:
                        template = tx.store.get_template(ref.uid)
                        resolved_symbols[template.predicate.uid] = template.predicate
                        return
                    if kind is RefKind.N:
                        node = tx.store.get_hypernode(ref.uid)
                        template = tx.store.get_template(node.template.uid)
                        resolved_symbols[template.predicate.uid] = template.predicate
                        return
                    if kind is RefKind.G:
                        element = tx.store.get_element_any_domain(ref.uid)
                        if isinstance(element, FunctionSymbol):
                            for operand in element.operands:
                                if isinstance(operand, Ref):
                                    collect_predicate_symbols(operand)
                        return
                    if kind is RefKind.K:
                        element = tx.store.get_element_any_domain(ref.uid)
                        if isinstance(element, Group):
                            for member in element.members:
                                collect_predicate_symbols(member)

                for item in assertions:
                    collect_predicate_symbols(item.ref)
                for item in conditionals:
                    collect_predicate_symbols(item.ref)
                for item in existentials:
                    collect_predicate_symbols(item.ref)
                for item in universals:
                    collect_predicate_symbols(item.ref)
                for semantic_act in (*resolved_queries, *resolved_commands):
                    selection = semantic_act.predicate.template_selection
                    if selection is not None and selection.existing_template_uid:
                        collect_predicate_symbols(tx.ref(selection.existing_template_uid))

                seeds.extend(
                    ActivationSeedRequest(ref, SeedReason.RESOLVED_SYMBOL)
                    for ref in sorted(resolved_symbols.values(), key=lambda item: item.uid)
                )

        assert experience_ref is not None
        if forced_domain is None:
            self._refresh_cross_turn_pronoun_anchors(result, assertions, context)
            self._refresh_cross_turn_existential_anchors(
                plan, result, assertions, existentials, context
            )
        context.last_experience_ref = experience_ref
        clarifications = self._clarification_requests(tuple(assertions))
        commit = IntegrationCommit(
            assertions=tuple(assertions),
            experience_ref=experience_ref,
            activation_seeds=tuple(seeds),
            refutations=tuple(refutations),
            unresolved_queries=tuple(item for item in resolved_queries if not item.quoted),
            unresolved_commands=tuple(item for item in resolved_commands if not item.quoted),
            clarification_required=bool(clarifications),
            clarifications=clarifications,
            relations=tuple(relations),
            conditionals=tuple(conditionals),
            formulas=tuple(formulas),
            existentials=tuple(existentials),
            universals=tuple(universals),
            conflicts=tuple(conflicts),
            quantified_queries=tuple(quantified_queries),
        )
        from ah.diagnostics.session_log import emit

        emit(
            "pipeline_canonical_commit",
            experience_uid=commit.experience_ref.uid,
            assertions=[
                {
                    "local_id": item.local_id,
                    "uid": item.ref.uid,
                    "kind": item.ref.kind.value,
                    "domain": item.domain.value,
                    "created": item.created,
                    "scope": item.semantic_scope,
                }
                for item in commit.assertions
            ],
            relations=[
                {
                    "relation_id": item.relation_id,
                    "uid": item.ref.uid,
                    "source_uid": item.source.uid,
                    "target_uid": item.target.uid,
                    "created": item.created,
                }
                for item in commit.relations
            ],
            conditionals=[item.ref.uid for item in commit.conditionals],
            quantified_queries=[
                {
                    "local_id": item.local_id,
                    "uid": item.ref.uid,
                    "members": [ref.uid for ref in item.member_refs],
                    "variable_ids": list(item.variable_ids),
                }
                for item in commit.quantified_queries
            ],
            formulas=[
                {
                    "local_id": item.local_id,
                    "uid": item.ref.uid,
                    "members": [ref.uid for ref in item.member_refs],
                    "created": item.created,
                }
                for item in commit.formulas
            ],
            existentials=[item.ref.uid for item in commit.existentials],
            universals=[item.ref.uid for item in commit.universals],
            conflicts=[item.ref.uid for item in commit.conflicts],
            activation_seeds=[
                {"uid": item.ref.uid, "reason": item.reason.value}
                for item in commit.activation_seeds
            ],
        )
        return commit

    def _discourse_signature(self, text: str | None) -> tuple[str, str | None] | None:
        """Return a stable number/gender signature for one source nominal.

        The signature is runtime evidence only.  It is used to carry a uniquely
        compatible antecedent into the next turn for nominative ``он/она/оно/они``.
        If morphology is ambiguous, no anchor is created.
        """
        import re

        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", text or "")
        for word in reversed(words):
            try:
                analyses = self._discourse_morphology.analyze_all(word)
            except AttributeError:
                single = self._discourse_morphology.analyze(word)
                analyses = () if single is None else (single,)
            nominal = [
                item for item in material_analyses(tuple(analyses))
                if item.pos in {"NOUN", "NPRO"} and item.number
            ]
            if not nominal:
                continue
            numbers = {item.number for item in nominal if item.number}
            if len(numbers) != 1:
                return None
            number = next(iter(numbers))
            if number == "plur":
                return ("plur", None)
            genders = {item.gender for item in nominal if item.gender}
            if len(genders) != 1:
                return None
            return ("sing", next(iter(genders)))
        return None

    def _predicate_discourse_signature(
        self, assertion: AssertionCandidate
    ) -> tuple[str, str | None] | None:
        """Return number/gender carried by a finite predicate occurrence.

        Russian noun forms can be lexically ambiguous (proper names and quantified
        NPs are common examples), while a finite verb in the same clause often
        exposes the number and, in the past singular, gender agreement directly.
        This is source grammar only; it never resolves an entity by semantics.
        """
        surface = (assertion.predicate.surface or "").strip()
        if not surface and assertion.predicate.evidence is not None:
            surface = assertion.predicate.evidence.text.strip()
        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", surface)
        if not words:
            return None
        analyses: list = []
        for word in words:
            try:
                values = self._discourse_morphology.analyze_all(word)
            except AttributeError:
                single = self._discourse_morphology.analyze(word)
                values = () if single is None else (single,)
            analyses.extend(
                item for item in material_analyses(tuple(values))
                if item.pos == "VERB" and item.number
            )
        if not analyses:
            return None
        numbers = {item.number for item in analyses if item.number}
        if len(numbers) != 1:
            return None
        number = next(iter(numbers))
        if number == "plur":
            return ("plur", None)
        if number != "sing":
            return None
        genders = {item.gender for item in analyses if item.gender}
        if len(genders) == 1:
            return ("sing", next(iter(genders)))
        return None

    def _subject_discourse_signature(
        self, assertion: AssertionCandidate, actant: ActantCandidate
    ) -> tuple[str, str | None] | None:
        # Predicate agreement is preferred when it is explicit because it describes
        # the grammatical SUBJECT of this exact clause. Fall back to the nominal
        # surface only when the predicate does not carry a unique signature.
        return self._predicate_discourse_signature(assertion) or self._discourse_signature(
            actant.mention or actant.normalized_hint
        )

    def _subject_is_proper_name(self, actant: ActantCandidate) -> bool:
        """Return whether source morphology selects a proper-name nominal reading.

        This is a discourse-salience feature only; it never changes canonical
        entity identity.  Pymorphy can expose surname/name homographs for ordinary
        nouns, so a weak proper-name reading is not enough.  Treat the source head
        as named only when the best proper reading is at least as strong as the best
        competing common-noun reading.
        """
        surface = (
            actant.nominal_relations[0].head_mention
            if actant.nominal_relations
            else (actant.mention or actant.normalized_hint or "")
        )
        words = re.findall(r"[A-Za-zА-Яа-яЁё-]+", surface)
        if not words:
            return False
        for word in reversed(words):
            try:
                values = self._discourse_morphology.analyze_all(word)
            except AttributeError:
                single = self._discourse_morphology.analyze(word)
                values = () if single is None else (single,)
            nominal = [
                item for item in material_analyses(tuple(values))
                if item.pos == "NOUN"
            ]
            if not nominal:
                continue
            proper = [
                item for item in nominal
                if {"Name", "Surn", "Patr"} & set(item.grammemes)
            ]
            if not proper:
                return False
            common = [item for item in nominal if item not in proper]
            best_proper = max(float(item.score) for item in proper)
            best_common = max((float(item.score) for item in common), default=-1.0)
            return best_proper >= best_common
        return False

    def _refresh_cross_turn_pronoun_anchors(
        self,
        result: PerceptionResult,
        assertions: tuple[IntegratedAssertion, ...] | list[IntegratedAssertion],
        context: InteractionContext,
    ) -> None:
        """Refresh third-person discourse anchors from source-grounded subjects.

        ``pronoun_refs`` is a salience cache, not canonical truth.  A unique
        source-grounded proper-name SUBJECT outranks incidental common-noun subjects
        of the same signature; otherwise source recency is used.  This preserves a
        stable narrative protagonist without making animacy a global preference.
        Several distinct named subjects or a tie at the winning recency remain
        unresolved and clear the cache rather than guessing.
        """
        candidates_by_signature: dict[
            tuple[str, str | None], list[tuple[int, Ref, bool]]
        ] = {}
        assertion_by_id = {item.local_id: item for item in result.assertions}

        for integrated in assertions:
            if integrated.ref.kind is not RefKind.N:
                continue
            candidate = assertion_by_id.get(integrated.local_id)
            if candidate is None or candidate.quoted:
                continue
            try:
                node = self.core.store.get_hypernode(integrated.ref.uid)
            except Exception:
                continue
            for actant in candidate.actants:
                if actant.role is not ActantRole.SUBJECT:
                    continue
                ref = node.actants.get(actant.role)
                if not isinstance(ref, Ref) or ref.kind is not RefKind.M:
                    continue
                entity = self.core.store.get_element_any_domain(ref.uid)
                if not isinstance(entity, SemanticEntity):
                    continue
                name_prop = entity.properties.get("name")
                canonical_name = (
                    str(name_prop.value).strip() if name_prop is not None else ""
                )
                # Never promote an unresolved pronoun-shaped M into the salience
                # cache. A resolved source pronoun points to an existing named M.
                if canonical_name.casefold() in _ENTITY_PRONOUNS:
                    continue
                signature = self._subject_discourse_signature(candidate, actant)
                if signature not in _NOMINATIVE_PRONOUN_BY_SIGNATURE:
                    continue
                position = (
                    actant.evidence.start
                    if actant.evidence is not None and actant.evidence.start is not None
                    else (
                        candidate.evidence.start
                        if candidate.evidence is not None and candidate.evidence.start is not None
                        else -1
                    )
                )
                candidates_by_signature.setdefault(signature, []).append(
                    (position, ref, self._subject_is_proper_name(actant))
                )

        for signature, candidates in candidates_by_signature.items():
            pronoun = _NOMINATIVE_PRONOUN_BY_SIGNATURE[signature]
            # A fresh canonical subject of this grammatical signature supersedes
            # an older runtime existential continuation anchor. If the current turn
            # is ambiguous, both caches are cleared below rather than guessed.
            context.existential_pronoun_anchors.pop(pronoun, None)

            # A unique explicitly named subject is a stronger discourse anchor than
            # later incidental common-noun subjects of the same grammatical gender.
            # This handles narrative continuity such as ``Марина ... Бумага ...
            # печь ... Она ...`` without globally preferring animate entities: when
            # there is no named referent, ordinary source recency still resolves
            # ``Лампа погасла. Точка появилась. Она ...`` to ``Точка``.  Multiple
            # distinct named subjects remain ambiguous and clear the cache.
            named_refs = {ref for _position, ref, is_named in candidates if is_named}
            if named_refs:
                if len(named_refs) == 1:
                    context.pronoun_refs[pronoun] = next(iter(named_refs))
                else:
                    context.pronoun_refs.pop(pronoun, None)
                continue

            latest_position = max(position for position, _ref, _named in candidates)
            latest_refs = {
                ref for position, ref, _named in candidates if position == latest_position
            }
            if len(latest_refs) == 1:
                context.pronoun_refs[pronoun] = next(iter(latest_refs))
            else:
                # Distinct entities tied at the latest source position are truly
                # unresolved; keeping an older anchor would be a hidden guess.
                context.pronoun_refs.pop(pronoun, None)

    def _refresh_cross_turn_existential_anchors(
        self,
        plan: MutationPlan,
        result: PerceptionResult,
        assertions: tuple[IntegratedAssertion, ...] | list[IntegratedAssertion],
        existentials: tuple[IntegratedExistential, ...] | list[IntegratedExistential],
        context: InteractionContext,
    ) -> None:
        """Publish one-variable existential subjects as runtime pronoun anchors.

        The canonical memory remains the quantified G/N structure.  The context
        stores only a reconstructible discourse handle so a following nominative
        pronoun can extend the same existential scope.  Multi-variable scopes are
        deliberately not exposed through this shortcut.
        """

        if not existentials or not plan.candidate_ir.existential_bindings:
            return

        candidates_by_id = {item.local_id: item for item in result.assertions}
        bindings = {item.entity_ref: item for item in plan.candidate_ir.existential_bindings}
        integrated_by_id = {item.local_id: item for item in assertions}

        # Determine which variable IDs are source-grounded SUBJECTs in this turn and
        # which nominative pronoun form their grammar licenses.
        pronouns_by_var: dict[int, set[str]] = {}
        for local_id, candidate in candidates_by_id.items():
            if local_id not in integrated_by_id:
                continue
            variants = candidate.alternatives or (candidate,)
            for variant in variants:
                for actant in variant.actants:
                    if actant.role is not ActantRole.SUBJECT or actant.entity_ref is None:
                        continue
                    binding = bindings.get(actant.entity_ref)
                    if binding is None or binding.negative:
                        continue
                    signature = self._subject_discourse_signature(candidate, actant)
                    pronoun = _NOMINATIVE_PRONOUN_BY_SIGNATURE.get(signature)
                    if pronoun is not None:
                        pronouns_by_var.setdefault(binding.variable_id, set()).add(pronoun)

        proposed: dict[str, list[ExistentialDiscourseAnchor]] = {}
        for existential in existentials:
            if len(existential.variable_ids) != 1:
                continue
            variable_id = existential.variable_ids[0]
            pronouns = pronouns_by_var.get(variable_id, set())
            if len(pronouns) != 1:
                continue
            pronoun = next(iter(pronouns))
            proposed.setdefault(pronoun, []).append(
                ExistentialDiscourseAnchor(
                    existential_ref=existential.ref,
                    member_refs=existential.member_refs,
                    variable_id=variable_id,
                    restriction_lemma=next(
                        (
                            binding.restriction_lemma
                            for binding in bindings.values()
                            if binding.variable_id == variable_id
                        ),
                        None,
                    ),
                )
            )

        for pronoun, anchors in proposed.items():
            # A latest existential subject must replace any stale canonical referent.
            # Multiple distinct existential scopes of the same signature in one turn
            # remain unresolved and clear both runtime caches.
            unique = {anchor.existential_ref.uid: anchor for anchor in anchors}
            context.pronoun_refs.pop(pronoun, None)
            if len(unique) == 1:
                context.existential_pronoun_anchors[pronoun] = next(iter(unique.values()))
            else:
                context.existential_pronoun_anchors.pop(pronoun, None)

    @staticmethod
    def _speech_act_kinds(result: PerceptionResult) -> tuple[str, ...]:
        """Return top-level pragmatic kinds for one H experience event.

        Embedded/quoted proposition content is deliberately excluded.  Its
        presence under a QUERY/COMMAND root records what was mentioned, not what
        the user asserted as a world fact.
        """
        kinds: list[str] = []
        if any(
            item.status is AssertionStatus.ASSERTED and not item.quoted
            for item in result.assertions
        ):
            kinds.append("ASSERTION")
        if any(not item.quoted for item in result.queries):
            kinds.append("QUERY")
        if any(not item.quoted for item in result.commands):
            kinds.append("COMMAND")
        return tuple(kinds)

    @staticmethod
    def _local_assertion_domain_overrides(
        core: AHCore,
        ordered: tuple[AssertionCandidate, ...] | list[AssertionCandidate],
        context: InteractionContext,
        *,
        forced_domain: Domain | None,
        speaker_ref: Ref,
        addressee_ref: Ref | None,
    ) -> dict[str, Domain]:
        """Propagate personalized provenance through local proposition content.

        Dependency ordering may integrate a nested candidate before its enclosing
        assertion.  Domain choice therefore cannot rely only on already-integrated
        candidate_refs.  Seed P from direct deictic provenance, then propagate that
        requirement through local candidate_ref containment before any N is built.
        LLM output is not involved and no canonical UID is exposed to Perception.
        """
        if forced_domain is not None:
            return {item.local_id: forced_domain for item in ordered}

        resolver = EntityResolver(core)
        by_id = {item.local_id: item for item in ordered}
        personalized: set[str] = set()
        for candidate in ordered:
            variants = (candidate, *candidate.alternatives)
            for variant in variants:
                for actant in variant.actants:
                    if actant.candidate_ref is not None or actant.composition is not None or actant.proposition is not None:
                        continue
                    resolved = resolver.deixis.resolve(
                        actant,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                    )
                    if (
                        resolved is not None
                        and core.store.domain_of(resolved.uid) is Domain.P
                    ):
                        personalized.add(candidate.local_id)
                        break
                if candidate.local_id in personalized:
                    break

        queue = list(personalized)
        while queue:
            parent_id = queue.pop()
            parent = by_id[parent_id]
            for variant in (parent, *parent.alternatives):
                for actant in variant.actants:
                    child_ids = (() if actant.candidate_ref is None else (actant.candidate_ref,))
                    if actant.proposition is not None:
                        child_ids = (*child_ids, *actant.proposition.leaf_refs())
                    for child_id in child_ids:
                        if child_id not in by_id or child_id in personalized:
                            continue
                        personalized.add(child_id)
                        queue.append(child_id)
        return {local_id: Domain.P for local_id in personalized}

    def clarification_request(self, ambiguous_ref: Ref) -> ClarificationRequest:
        """Describe one canonical ``k_AMBIGUOUS`` without exposing internal UIDs.

        This is a read-only deterministic projection used by the orchestrator to
        ask the user for missing evidence. The LLM may verbalize the returned
        options, but canonical choice remains outside the model.
        """
        if ambiguous_ref.kind is not RefKind.K or not self.core.store.has_uid(ambiguous_ref.uid):
            raise CandidateValidationError("Clarification target must be an existing K")
        element = self.core.store.get_element_any_domain(ambiguous_ref.uid)
        if not isinstance(element, Group):
            raise CandidateValidationError("Clarification target is not a K group")
        if element.meta.get("TYPE") == "AMBIGUOUS_REFERENCE":
            return self._build_clarification_request(ambiguous_ref, element)
        if element.meta.get("TYPE") == "STRUCTURAL_CLARIFICATION":
            return self._build_structural_clarification_request(ambiguous_ref, element)
        raise CandidateValidationError("Clarification target has unsupported TYPE")

    def register_structural_clarification(
        self,
        spec: StructuralClarificationSpec,
        experience_ref: Ref,
    ) -> ClarificationRequest:
        """Persist one unresolved structural ambiguity as H dialogue state.

        The option groups are not world facts and contain no guessed semantic N.
        They only keep the user's pending structural choice durable across turns.
        """
        if experience_ref.kind is not RefKind.N or self.core.store.domain_of(experience_ref.uid) is not Domain.H:
            raise CandidateValidationError("Structural clarification must anchor an H experience")
        with self.core.transaction() as tx:
            option_refs: list[Ref] = []
            for option in spec.options:
                group = tx.add_group(
                    Domain.H,
                    (),
                    meta={
                        "TYPE": "STRUCTURAL_CLARIFICATION_OPTION",
                        "label": option.label,
                        "resolution_key": option.key,
                        "gc_auto_created": True,
                    },
                )
                option_refs.append(tx.ref(group.uid))
            top = tx.add_group(
                Domain.H,
                tuple(option_refs),
                meta={
                    "TYPE": "STRUCTURAL_CLARIFICATION",
                    "ambiguity_type": spec.ambiguity_type,
                    "mention": spec.mention,
                    "source_text": spec.source_text,
                    "experience_uid": experience_ref.uid,
                    "gc_auto_created": True,
                },
            )
            ref = tx.ref(top.uid)
        return self.clarification_request(ref)

    def structural_clarification_selection(
        self,
        ambiguous_ref: Ref,
        selected_ref: Ref,
    ) -> tuple[str, str, Ref]:
        """Return (source_text, resolution_key, original_experience_ref)."""
        if ambiguous_ref.kind is not RefKind.K or selected_ref.kind is not RefKind.K:
            raise CandidateValidationError("Structural clarification refs must be K")
        group = self.core.store.get_element_any_domain(ambiguous_ref.uid)
        option = self.core.store.get_element_any_domain(selected_ref.uid)
        if not isinstance(group, Group) or group.meta.get("TYPE") != "STRUCTURAL_CLARIFICATION":
            raise CandidateValidationError("Clarification target is not structural")
        if selected_ref not in group.members:
            raise CandidateValidationError("Structural selection is not one of the pending options")
        if not isinstance(option, Group) or option.meta.get("TYPE") != "STRUCTURAL_CLARIFICATION_OPTION":
            raise CandidateValidationError("Structural selection option is invalid")
        source_text = str(group.meta.get("source_text") or "").strip()
        key = str(option.meta.get("resolution_key") or "").strip()
        experience_uid = str(group.meta.get("experience_uid") or "").strip()
        if not source_text or not key or not experience_uid or not self.core.store.has_uid(experience_uid):
            raise CandidateValidationError("Structural clarification state is incomplete")
        return source_text, key, self.core.ref(experience_uid)

    def finalize_structural_clarification(
        self, ambiguous_ref: Ref, selected_ref: Ref
    ) -> ClarificationResolutionCommit:
        with self.core.transaction() as tx:
            group = tx.store.get_element_any_domain(ambiguous_ref.uid)
            if not isinstance(group, Group) or group.meta.get("TYPE") != "STRUCTURAL_CLARIFICATION":
                raise CandidateValidationError("Clarification target is not structural")
            if selected_ref not in group.members:
                raise CandidateValidationError("Structural selection is not one of the pending options")
            domain = tx.store.domain_of(group.uid)
            assert domain is Domain.H
            tx.edit_element(
                Domain.H,
                replace(group, meta={**dict(group.meta), "resolved_to": selected_ref.uid}),
            )
        return ClarificationResolutionCommit(ambiguous_ref, selected_ref, (), ())

    def _build_structural_clarification_request(
        self, ref: Ref, group: Group
    ) -> ClarificationRequest:
        options: list[ClarificationOption] = []
        for index, member in enumerate(group.members, start=1):
            option = self.core.store.get_element_any_domain(member.uid)
            if not isinstance(option, Group) or option.meta.get("TYPE") != "STRUCTURAL_CLARIFICATION_OPTION":
                raise CandidateValidationError("Structural clarification contains an invalid option")
            label = str(option.meta.get("label") or "").strip()
            if not label:
                raise CandidateValidationError("Structural clarification option has no label")
            options.append(ClarificationOption(index, member, label))
        return ClarificationRequest(
            ambiguous_ref=ref,
            mention=str(group.meta.get("mention") or "неоднозначная конструкция"),
            options=tuple(options),
            uses=(),
            kind="STRUCTURAL",
            source_text=str(group.meta.get("source_text") or ""),
        )

    @staticmethod
    def _property_values_for_aliases(entity: SemanticEntity) -> tuple[str, ...]:
        values: list[str] = []
        for key in ("name", "aliases"):
            prop = entity.properties.get(key)
            if prop is None:
                continue
            raw = prop.value
            items = raw if isinstance(raw, (tuple, list, set, frozenset)) else (raw,)
            for item in items:
                text = str(item).strip()
                if text and text not in values:
                    values.append(text)
        return tuple(values)

    def merge_identity(
        self,
        left: Ref,
        right: Ref,
        *,
        reason: str,
    ) -> IdentityMergeResult:
        """Canonically merge two explicitly proven duplicate semantic identities.

        The method performs no identity inference.  The caller must already have
        established that ``left`` and ``right`` denote one entity.  The older
        canonical UID survives deterministically; every canonical incidence and
        proof support is rewired inside one AH transaction, and exact N collisions
        are recursively deduplicated.

        Conflicting ordinary properties are not silently resolved here.  Until a
        property-level conflict policy is registered, such a merge fails atomically
        instead of choosing a value by recency/frequency.
        """
        if not reason.strip():
            raise CandidateValidationError("Identity merge reason must be non-empty")
        if left.kind is not RefKind.M or right.kind is not RefKind.M:
            raise CandidateValidationError("Identity merge endpoints must be M")
        if left == right:
            return IdentityMergeResult(left, right, ())

        final_by_uid: dict[str, Ref] = {}
        with self.core.transaction() as tx:
            for ref in (left, right):
                if not tx.store.has_uid(ref.uid) or tx.store.kind_of(ref.uid) is not RefKind.M:
                    raise CandidateValidationError(f"Identity merge endpoint is not canonical: {ref.uid}")

            survivor, removed = sorted(
                (left, right),
                key=lambda ref: (tx.store.creation_sequence(ref.uid), ref.uid),
            )
            survivor_entity = tx.store.get_element_any_domain(survivor.uid)
            removed_entity = tx.store.get_element_any_domain(removed.uid)
            assert isinstance(survivor_entity, SemanticEntity)
            assert isinstance(removed_entity, SemanticEntity)

            merged_properties = dict(survivor_entity.properties)
            aliases = list(self._property_values_for_aliases(survivor_entity))
            for value in self._property_values_for_aliases(removed_entity):
                if value not in aliases:
                    aliases.append(value)

            for name, prop in removed_entity.properties.items():
                if name in {"name", "aliases"}:
                    continue
                existing = merged_properties.get(name)
                if existing is None:
                    merged_properties[name] = prop
                    continue
                if (existing.value, existing.type_name, existing.unit) != (
                    prop.value, prop.type_name, prop.unit
                ):
                    raise CandidateValidationError(
                        f"Identity merge property conflict for {name!r}: "
                        f"{existing.value!r} != {prop.value!r}"
                    )

            survivor_name = merged_properties.get("name")
            alias_values = tuple(
                value
                for value in aliases
                if survivor_name is None or str(survivor_name.value).strip() != value
            )
            if alias_values:
                merged_properties["aliases"] = Property("aliases", alias_values, "str[]")

            merged_meta = dict(survivor_entity.meta)
            for key, value in removed_entity.meta.items():
                if key not in merged_meta:
                    merged_meta[key] = value

            survivor_domain = tx.store.domain_of(survivor.uid)
            assert survivor_domain is not None
            tx.edit_element(
                survivor_domain,
                replace(
                    survivor_entity,
                    properties=merged_properties,
                    meta=merged_meta,
                ),
            )
            self._replace_reference_usages(
                tx, removed, survivor, delete_source=True, final_by_uid=final_by_uid
            )

        # Recursive N/L dedup rewiring is intentionally internal to the atomic
        # mutation.  The public merge result reports the identity replacement;
        # diagnostics can inspect the canonical graph for collapsed dependants.
        from ah.diagnostics.session_log import emit as emit_session_event

        emit_session_event(
            "identity_merge",
            survivor_uid=survivor.uid,
            removed_uid=removed.uid,
            reason=reason.strip(),
        )
        return IdentityMergeResult(
            survivor, removed, ((removed, survivor),), reason=reason.strip()
        )

    def resolve_clarification(
        self,
        ambiguous_ref: Ref,
        selected_ref: Ref,
    ) -> ClarificationResolutionCommit:
        """Replace every canonical use of one ambiguity K by an explicit member.

        The selection must already be grounded in the user's clarification answer.
        This method performs no linguistic inference and never asks an LLM.  The
        mutation is transactional; if replacement would violate canonical validity,
        the original graph remains untouched.
        """
        if ambiguous_ref.kind is not RefKind.K:
            raise CandidateValidationError("Clarification target must be K")
        final_by_uid: dict[str, Ref] = {}
        initial_affected: tuple[Ref, ...] = ()
        with self.core.transaction() as tx:
            if not tx.store.has_uid(ambiguous_ref.uid):
                raise CandidateValidationError("Clarification K no longer exists")
            group = tx.store.get_element_any_domain(ambiguous_ref.uid)
            if not isinstance(group, Group) or group.meta.get("TYPE") != "AMBIGUOUS_REFERENCE":
                raise CandidateValidationError("Clarification target is not k_AMBIGUOUS")
            if selected_ref not in group.members:
                raise CandidateValidationError("Clarification selection is not a member of k_AMBIGUOUS")
            if not tx.store.has_uid(selected_ref.uid) or tx.store.kind_of(selected_ref.uid) is not selected_ref.kind:
                raise CandidateValidationError("Clarification selection is not canonical")

            initial_affected = tuple(
                use.fact_ref for use in self._clarification_uses_for_ref(ambiguous_ref, core=tx)
            )
            self._replace_reference_usages(
                tx,
                ambiguous_ref,
                selected_ref,
                delete_source=False,
                final_by_uid=final_by_uid,
            )

        def final(ref: Ref) -> Ref:
            seen: set[str] = set()
            while ref.uid in final_by_uid and ref.uid not in seen:
                seen.add(ref.uid)
                ref = final_by_uid[ref.uid]
            return ref

        affected: list[Ref] = []
        for ref in initial_affected:
            resolved = final(ref)
            if resolved not in affected:
                affected.append(resolved)
        return ClarificationResolutionCommit(
            ambiguous_ref=ambiguous_ref,
            selected_ref=selected_ref,
            affected_facts=tuple(affected),
            activation_seeds=tuple(
                ActivationSeedRequest(ref, SeedReason.CORRECTION) for ref in affected
            ),
        )

    def _clarification_requests(
        self, assertions: tuple[IntegratedAssertion, ...]
    ) -> tuple[ClarificationRequest, ...]:
        by_uid: dict[str, ClarificationRequest] = {}
        visited: set[str] = set()

        def walk(ref: Ref) -> None:
            if ref.uid in visited or not self.core.store.has_uid(ref.uid):
                return
            visited.add(ref.uid)
            if ref.kind is RefKind.N:
                node = self.core.store.get_hypernode(ref.uid)
                for child in node.actants.values():
                    if isinstance(child, Ref):
                        walk(child)
                return
            if ref.kind is RefKind.G:
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, FunctionSymbol):
                    for child in element.operands:
                        if isinstance(child, Ref):
                            walk(child)
                return
            if ref.kind is RefKind.K:
                element = self.core.store.get_element_any_domain(ref.uid)
                if not isinstance(element, Group):
                    return
                if element.meta.get("TYPE") == "AMBIGUOUS_REFERENCE":
                    by_uid.setdefault(ref.uid, self._build_clarification_request(ref, element))
                    return
                for child in element.members:
                    walk(child)

        for assertion in assertions:
            walk(assertion.ref)
        return tuple(by_uid.values())

    def _build_clarification_request(self, ref: Ref, group: Group) -> ClarificationRequest:
        raw_labels = [self._clarification_member_label(member) for member in group.members]
        counts: dict[str, int] = {}
        for label in raw_labels:
            counts[label.casefold()] = counts.get(label.casefold(), 0) + 1
        labels: list[str] = []
        duplicate_index: dict[str, int] = {}
        for label in raw_labels:
            key = label.casefold()
            if counts[key] > 1:
                duplicate_index[key] = duplicate_index.get(key, 0) + 1
                labels.append(f"{label} (вариант {duplicate_index[key]})")
            else:
                labels.append(label)

        uses = list(self._clarification_uses_for_ref(ref))
        mention = str(group.meta.get("mention") or "неоднозначная ссылка").strip()
        return ClarificationRequest(
            ambiguous_ref=ref,
            mention=mention,
            options=tuple(
                ClarificationOption(index, member, labels[index - 1])
                for index, member in enumerate(group.members, start=1)
            ),
            uses=tuple(uses),
        )

    def _clarification_uses_for_ref(
        self,
        ambiguous_ref: Ref,
        *,
        core: AHCore | None = None,
    ) -> tuple[ClarificationUse, ...]:
        graph = core or self.core

        def contains(ref: Ref, visited: set[str]) -> bool:
            if ref == ambiguous_ref:
                return True
            if ref.uid in visited or not graph.store.has_uid(ref.uid):
                return False
            visited.add(ref.uid)
            if ref.kind is RefKind.G:
                element = graph.store.get_element_any_domain(ref.uid)
                return isinstance(element, FunctionSymbol) and any(
                    contains(child, visited)
                    for child in element.operands
                    if isinstance(child, Ref)
                )
            if ref.kind is RefKind.K:
                element = graph.store.get_element_any_domain(ref.uid)
                return isinstance(element, Group) and any(
                    contains(child, visited) for child in element.members
                )
            # An N referenced as an actant is a separate proposition. Its own
            # ambiguity is clarified at that N, not duplicated onto every parent
            # proposition/H wrapper that happens to reference it.
            if ref.kind is RefKind.N:
                return False
            return False

        uses: list[ClarificationUse] = []
        for domain in Domain:
            for element in graph.store.elements(domain):
                if not isinstance(element, Hypernode):
                    continue
                roles = tuple(
                    role
                    for role, value in element.actants.items()
                    if isinstance(value, Ref) and contains(value, set())
                )
                if roles:
                    uses.append(ClarificationUse(graph.ref(element.uid), roles))
        return tuple(uses)

    def _clarification_member_label(self, ref: Ref) -> str:
        element = self.core.store.get_element_any_domain(ref.uid)
        if isinstance(element, SemanticEntity):
            details = [
                f"{key}={prop.value}"
                for key, prop in sorted(element.properties.items())
                if key != "name"
                # Morphosyntactic identity guards belong to canonical matching,
                # not to the user-facing denotation.  Exposing them in a choice
                # label makes a clarification depend on parser internals.
                and not key.startswith("grammatical_")
                and isinstance(prop.value, (str, int, float, bool))
            ]
            name = element.properties.get("name")
            if name is not None and str(name.value).strip():
                base = str(name.value).strip()
                return f"{base} ({'; '.join(details)})" if details else base
            if details:
                return "; ".join(details)
            return "объект"
        if isinstance(element, Hypernode):
            return "ситуация"
        if isinstance(element, Group):
            return "группа"
        if isinstance(element, FunctionSymbol):
            return element.function_id
        return ref.kind.value

    @staticmethod
    def _merged_occurrence_meta(existing: Hypernode, duplicate: Hypernode) -> dict[str, object]:
        meta = dict(existing.meta)
        meta["occurrence_count"] = int(existing.meta.get("occurrence_count", 1)) + int(
            duplicate.meta.get("occurrence_count", 1)
        )
        return meta

    def _replace_reference_usages(
        self,
        core: AHCore,
        source: Ref,
        target: Ref,
        *,
        delete_source: bool,
        final_by_uid: dict[str, Ref],
    ) -> None:
        """Rewrite canonical references and recursively collapse N dedup collisions."""
        queue: list[tuple[Ref, Ref, bool]] = [(source, target, delete_source)]
        processed: set[tuple[str, str]] = set()
        while queue:
            old, new, remove_old = queue.pop(0)
            if old == new or (old.uid, new.uid) in processed:
                continue
            processed.add((old.uid, new.uid))
            final_by_uid[old.uid] = new

            for domain in Domain:
                for element in tuple(core.store.elements(domain)):
                    if element.uid == old.uid:
                        continue
                    if isinstance(element, Hypernode):
                        changed = False
                        actants = dict(element.actants)
                        for role, value in tuple(actants.items()):
                            if value == old:
                                actants[role] = new
                                changed = True
                        if not changed:
                            continue
                        updated = replace(element, actants=actants)
                        template = core.store.get_template(updated.template.uid)
                        signature = hypernode_signature(updated, template)
                        existing = core.store.find_hypernode_by_signature(domain, signature)
                        if existing is not None and existing.uid != element.uid:
                            merged = replace(
                                existing,
                                weight=max(existing.weight, element.weight),
                                meta=self._merged_occurrence_meta(existing, element),
                            )
                            core.edit_element(domain, merged)
                            queue.append((core.ref(element.uid), core.ref(existing.uid), True))
                        else:
                            core.edit_element(domain, updated)
                    elif isinstance(element, FunctionSymbol):
                        if old not in element.operands:
                            continue
                        operands = tuple(new if value == old else value for value in element.operands)
                        core.edit_element(domain, replace(element, operands=operands))
                    elif isinstance(element, Group):
                        if old not in element.members:
                            continue
                        members: list[Ref] = []
                        for value in element.members:
                            value = new if value == old else value
                            if value not in members:
                                members.append(value)
                        if (
                            element.meta.get("TYPE") == "AMBIGUOUS_REFERENCE"
                            and len(members) == 1
                        ):
                            # The ambiguity disappeared because two supposedly
                            # different candidates were canonically the same value.
                            # Collapse the K itself so old pending clarifications do
                            # not survive as one-option zombie questions.
                            queue.append((core.ref(element.uid), members[0], True))
                        else:
                            core.edit_element(domain, replace(element, members=tuple(members)))

            for link in tuple(core.store.links()):
                if link.source != old and link.target != old:
                    continue
                new_source = new if link.source == old else link.source
                new_target = new if link.target == old else link.target
                replacement, created = core.ensure_link(
                    link.relation_id, new_source, new_target, link.weight
                )
                if not created and replacement.weight < link.weight:
                    core.edit_link(replace(replacement, weight=link.weight))
                core.supports.rewire_ref(core.ref(link.uid), core.ref(replacement.uid))
                core.store._remove_uid(link.uid)

            if remove_old and core.store.has_uid(old.uid):
                core.supports.rewire_ref(old, new)
                core.store._remove_uid(old.uid)

    def _ensure_class_pattern(
        self,
        core: AHCore,
        lemma: str,
        variable: BoundVar,
        domain: Domain,
    ) -> Ref:
        """Materialize CLASS($var) as a QUANTIFIED unary pattern, not a factual N."""

        lookup = str(lemma or "").strip()
        if not lookup:
            raise CandidateValidationError("Universal restriction class is empty")
        predicate = PredicateCandidate(
            lookup,
            lookup,
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        )
        template = TemplateResolver(core, template_domain=domain).resolve(
            predicate, (ActantRole.SUBJECT,)
        ).template
        node, _created = core.add_or_enrich_hypernode(
            domain,
            core.ref(template.uid),
            {ActantRole.SUBJECT: variable},
            weight=self.config.initial_hypernode_weight,
            meta={"semantic_scope": "QUANTIFIED"},
            count_occurrence=False,
        )
        return core.ref(node.uid)

    @staticmethod
    def _entity_anchors(result: PerceptionResult) -> dict[str, ActantCandidate]:
        """Choose one source-grounded anchor for every turn-local ``entity_ref``.

        Dependency ordering may integrate an embedded frame before the matrix frame
        that introduced the named participant.  ``entity_ref`` is nevertheless a
        turn-local identity commitment, so first integration must resolve from the
        best source mention for that id rather than from whichever frame happens to
        be visited first.  Named nominals outrank third-person pronouns; source order
        breaks ties deterministically.
        """
        grouped: dict[str, list[ActantCandidate]] = {}
        for assertion in result.assertions:
            for variant in (assertion, *assertion.alternatives):
                for actant in variant.actants:
                    if actant.entity_ref is None or actant.candidate_ref is not None or actant.composition is not None or actant.proposition is not None:
                        continue
                    grouped.setdefault(actant.entity_ref, []).append(actant)

        def score(item: ActantCandidate) -> tuple[int, int, str]:
            text = (item.normalized_hint or item.mention or "").strip()
            folded = text.casefold()
            named = int(bool(text) and folded not in _ENTITY_PRONOUNS)
            start = item.evidence.start if item.evidence is not None and item.evidence.start is not None else 10**12
            return (-named, start, folded)

        return {entity_ref: sorted(items, key=score)[0] for entity_ref, items in grouped.items()}

    def _integrate_disjunctive_assertion(
        self,
        core: AHCore,
        candidate: AssertionCandidate,
        context: InteractionContext,
        local_refs: dict[str, Ref],
        entity_local_refs: dict[str, Ref],
        forced_domain: Domain | None,
        *,
        entity_anchors: dict[str, ActantCandidate],
        speaker_ref: Ref,
        addressee_ref: Ref | None,
        count_occurrence: bool,
    ) -> IntegratedAssertion | None:
        """Lift an OR-valued actant into OR over complete proposition N nodes.

        ``X is green or red`` is not one fact whose STATE is an OR of raw values;
        it is a disjunction between two complete predicate realizations.  This
        generic lifting applies to exactly one OR-composed role and leaves AND
        composition untouched (AND entities such as ``bread and milk`` can remain
        a composed actant).
        """
        or_actants = [
            actant for actant in candidate.actants
            if actant.composition is not None and actant.composition.operator.value == "OR"
        ]
        if len(or_actants) != 1 or candidate.negated:
            return None
        target = or_actants[0]
        members: list[IntegratedAssertion] = []
        for member in target.composition.members:
            replacement = ActantCandidate(
                role=target.role,
                mention=member.mention,
                normalized_hint=member.normalized_hint,
                semantic_hint=member.semantic_hint,
                evidence=member.evidence,
            )
            variant_actants = tuple(
                replacement if actant is target else actant
                for actant in candidate.actants
            )
            variant = AssertionCandidate(
                local_id=candidate.local_id,
                predicate=candidate.predicate,
                actants=variant_actants,
                evidence=candidate.evidence,
                alternatives=(),
                negated=False,
                status=candidate.status,
            )
            integrated = self._integrate_assertion(
                core, variant, context, local_refs, entity_local_refs, forced_domain,
                entity_anchors=entity_anchors,
                speaker_ref=speaker_ref, addressee_ref=addressee_ref,
                count_occurrence=False,
                semantic_scope="DISJUNCTIVE",
                _allow_or_lift=False,
            )
            members.append(integrated)
        if not members:
            return None
        domains = {item.domain for item in members}
        if len(domains) != 1:
            raise CandidateValidationError("OR proposition members resolved to different domains")
        domain = members[0].domain
        function, created = core.ensure_function(
            domain, "OR", tuple(item.ref for item in members)
        )
        return IntegratedAssertion(
            local_id=candidate.local_id,
            ref=core.ref(function.uid),
            domain=domain,
            created=created or any(item.created for item in members),
            ambiguous=any(item.ambiguous for item in members),
        )

    @staticmethod
    def _literal_properties(plan: NewEntityPlan | EquivalentLiteralPlan) -> dict[str, Property]:
        return {
            "name": Property("name", plan.literal_value or getattr(plan, "name", ""), "str"),
            "literal_kind": Property("literal_kind", plan.literal_kind or "NUMBER", "str"),
            "literal_value": Property("literal_value", plan.literal_value or getattr(plan, "name", ""), "str"),
        }

    def _materialize_equivalent_literal(
        self, core: AHCore, plan: EquivalentLiteralPlan
    ) -> Ref:
        """Collapse persisted duplicate literal m nodes into one canonical identity.

        Literals are values, not discourse referents. Two NUMBER(5) nodes cannot
        represent a user-visible ambiguity. Prefer an existing C node; otherwise
        create the canonical literal in C, then rewrite every old incidence to it.
        """
        live = [ref for ref in plan.candidates if core.store.has_uid(ref.uid)]
        c_refs = [ref for ref in live if core.store.domain_of(ref.uid) is Domain.C]
        target = min(c_refs, key=lambda ref: ref.uid) if c_refs else None
        if target is None:
            entity = core.add_entity(
                Domain.C,
                properties=self._literal_properties(plan),
                meta={
                    "semantic_literal": True,
                    "literal_kind": plan.literal_kind,
                    "literal_value": plan.literal_value,
                    "gc_auto_created": True,
                },
            )
            target = core.ref(entity.uid)
        else:
            element = core.store.get_element_any_domain(target.uid)
            if isinstance(element, SemanticEntity):
                properties = dict(element.properties)
                properties.update(self._literal_properties(plan))
                meta = dict(element.meta)
                meta.update({
                    "semantic_literal": True,
                    "literal_kind": plan.literal_kind,
                    "literal_value": plan.literal_value,
                })
                core.edit_element(Domain.C, replace(element, properties=properties, meta=meta))

        final_by_uid: dict[str, Ref] = {}
        for source in live:
            if source.uid == target.uid or not core.store.has_uid(source.uid):
                continue
            self._replace_reference_usages(
                core, source, target, delete_source=True, final_by_uid=final_by_uid
            )
        return target

    def _materialize_entity_plan(
        self,
        core: AHCore,
        plan: Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan,
        default_domain: Domain,
    ) -> tuple[Ref, bool]:
        if isinstance(plan, Ref):
            return plan, False
        if isinstance(plan, EquivalentLiteralPlan):
            return self._materialize_equivalent_literal(core, plan), False
        if isinstance(plan, NewEntityPlan):
            domain = Domain.C if plan.literal_kind is not None else default_domain
            properties = (
                self._literal_properties(plan)
                if plan.literal_kind is not None
                else {"name": Property("name", plan.name, "str")}
            )
            if plan.literal_kind is None and plan.grammatical_number in {"sing", "plur"}:
                properties["grammatical_number"] = Property(
                    "grammatical_number", plan.grammatical_number, "str"
                )
            meta = {"gc_auto_created": True}
            if plan.literal_kind is None and plan.grammatical_number in {"sing", "plur"}:
                meta["grammatical_number"] = plan.grammatical_number
            if plan.literal_kind is not None:
                meta.update({
                    "semantic_literal": True,
                    "literal_kind": plan.literal_kind,
                    "literal_value": plan.literal_value,
                })
            entity = core.add_entity(domain, properties=properties, meta=meta)
            return core.ref(entity.uid), False
        group = core.add_group(
            default_domain,
            plan.candidates,
            meta={
                "TYPE": "AMBIGUOUS_REFERENCE",
                "mention": plan.mention,
                "gc_auto_created": True,
            },
        )
        return core.ref(group.uid), True

    @staticmethod
    def _nominal_relation_key(mention: str | None, normalized: str | None) -> str:
        value = (normalized or mention or "").strip().casefold().replace("ё", "е")
        return value

    def _materialize_nominal_relations(
        self,
        core: AHCore,
        source_actants: tuple[ActantCandidate, ...],
        canonical_actants: dict[ActantRole, Ref | BoundVar],
        context: InteractionContext,
        *,
        domain: Domain,
        speaker_ref: Ref,
        addressee_ref: Ref | None,
        entity_local_refs: dict[str, Ref],
        semantic_scope: str | None,
    ) -> tuple[IntegratedRelation, ...]:
        """Materialize source-grounded NP-internal structure as canonical L.

        Only ordinary asserted content creates these links.  Embedded, quoted and
        conditional proposition content remains scoped and therefore must not leak
        a possessive/genitive relation into the asserted world graph.

        Direction is always ``HEAD --RELATION--> DEPENDENT``.  ``POSSESSOR`` is
        semantically stronger and is emitted only from explicit possessive
        morphology. ``GENITIVE_DEP`` intentionally preserves the weaker grammatical
        relation rather than guessing whether a genitive means ownership, part-of,
        content, source, material, etc. ``NOMINAL_MODIFIER`` is weaker still: it
        records an attributive source modifier without guessing a MATERIAL, STATE,
        historical event, or other specialized semantic relation.
        """
        if semantic_scope is not None:
            return ()

        resolver = EntityResolver(core)
        integrated: list[IntegratedRelation] = []
        for actant in source_actants:
            if not actant.nominal_relations:
                continue
            main_ref = canonical_actants.get(actant.role)
            if not isinstance(main_ref, Ref):
                # Nominal world relations cannot use a scoped logical variable as
                # a canonical L endpoint.  Rich existential NP-internal semantics
                # remains a later formula-level extension rather than fabricating M.
                continue

            # Internal chains reuse identities already materialized earlier in the
            # same NP: дверь дома брата -> дверь->дом, then дом->брат.
            refs_by_key: dict[str, Ref] = {}
            for relation in actant.nominal_relations:
                if not refs_by_key:
                    for key in (
                        self._nominal_relation_key(relation.head_mention, relation.head_normalized_hint),
                        self._nominal_relation_key(actant.mention, actant.normalized_hint),
                    ):
                        if key:
                            refs_by_key[key] = main_ref

                head_key = self._nominal_relation_key(
                    relation.head_mention, relation.head_normalized_hint
                )
                source_ref = refs_by_key.get(head_key)
                if source_ref is None:
                    head_candidate = ActantCandidate(
                        role=actant.role,
                        mention=relation.head_mention,
                        normalized_hint=relation.head_normalized_hint,
                        evidence=relation.evidence,
                    )
                    head_resolution = resolver.resolve(
                        head_candidate,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                        preferred_domain=domain,
                    )
                    head_plan = (
                        head_resolution.ref
                        if isinstance(head_resolution, ExistingEntity)
                        else head_resolution
                    )
                    source_ref, _ = self._materialize_entity_plan(core, head_plan, domain)
                    if head_key:
                        refs_by_key[head_key] = source_ref

                dependent_ref = (
                    entity_local_refs.get(relation.dependent_entity_ref)
                    if relation.dependent_entity_ref is not None
                    else None
                )
                if dependent_ref is None:
                    dependent_candidate = ActantCandidate(
                        role=ActantRole.OBJECT,
                        mention=relation.dependent_mention,
                        normalized_hint=relation.dependent_normalized_hint,
                        entity_ref=relation.dependent_entity_ref,
                        evidence=relation.evidence,
                    )
                    dependent_resolution = resolver.resolve(
                        dependent_candidate,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                        preferred_domain=domain,
                    )
                    dependent_plan = (
                        dependent_resolution.ref
                        if isinstance(dependent_resolution, ExistingEntity)
                        else dependent_resolution
                    )
                    dependent_ref, _ = self._materialize_entity_plan(
                        core, dependent_plan, domain
                    )
                    if relation.dependent_entity_ref is not None:
                        prior = entity_local_refs.get(relation.dependent_entity_ref)
                        if prior is not None and prior != dependent_ref:
                            raise CandidateValidationError(
                                f"entity_ref {relation.dependent_entity_ref!r} resolved inconsistently "
                                "inside nominal relation"
                            )
                        entity_local_refs[relation.dependent_entity_ref] = dependent_ref

                link, created = core.ensure_link(
                    relation.kind.value,
                    source_ref,
                    dependent_ref,
                    self.config.nominal_relation_link_weight,
                )
                integrated.append(
                    IntegratedRelation(
                        relation_id=relation.kind.value,
                        source=source_ref,
                        target=dependent_ref,
                        ref=core.ref(link.uid),
                        created=created,
                    )
                )
                dep_key = self._nominal_relation_key(
                    relation.dependent_mention, relation.dependent_normalized_hint
                )
                if dep_key:
                    refs_by_key[dep_key] = dependent_ref
        return tuple(integrated)

    def _integrate_assertion(
        self,
        core: AHCore,
        candidate: AssertionCandidate,
        context: InteractionContext,
        local_refs: dict[str, Ref],
        entity_local_refs: dict[str, Ref],
        forced_domain: Domain | None,
        *,
        entity_anchors: dict[str, ActantCandidate],
        speaker_ref: Ref,
        addressee_ref: Ref | None,
        count_occurrence: bool = True,
        semantic_scope: str | None = None,
        _allow_or_lift: bool = True,
        existential_vars: dict[str, BoundVar] | None = None,
    ) -> IntegratedAssertion:
        existential_vars = existential_vars or {}
        if _allow_or_lift and semantic_scope is None:
            lifted = self._integrate_disjunctive_assertion(
                core, candidate, context, local_refs, entity_local_refs, forced_domain,
                entity_anchors=entity_anchors,
                speaker_ref=speaker_ref, addressee_ref=addressee_ref,
                count_occurrence=count_occurrence,
            )
            if lifted is not None:
                return lifted

        effective_actants = candidate.actants
        alternative_role_options: dict[ActantRole, tuple[ActantCandidate, ...]] = {}
        if candidate.alternatives:
            role_maps = [
                {actant.role: actant for actant in alternative.actants}
                for alternative in candidate.alternatives
            ]
            effective_actants = candidate.alternatives[0].actants

            def option_key(actant: ActantCandidate) -> tuple[object, ...]:
                if actant.entity_ref is not None:
                    return ("entity_ref", actant.entity_ref)
                if actant.candidate_ref is not None:
                    return ("candidate_ref", actant.candidate_ref)
                if actant.composition is not None:
                    return ("composition", repr(actant.composition))
                if actant.proposition is not None:
                    return ("proposition", repr(actant.proposition))
                return ("mention", (actant.lookup_text or "").casefold())

            for role in role_maps[0]:
                options = tuple(mapping[role] for mapping in role_maps)
                keys = {option_key(item) for item in options}
                if len(keys) > 1:
                    alternative_role_options[role] = options
            if len(alternative_role_options) > 1:
                raise CandidateValidationError(
                    f"Correlated runtime alternatives across several roles are not yet canonicalizable: "
                    f"{candidate.local_id}"
                )

        roles = tuple(actant.role for actant in effective_actants)
        template_domain = forced_domain if forced_domain is not None else Domain.C
        template = TemplateResolver(core, template_domain=template_domain).resolve(
            candidate.predicate, roles
        ).template
        entity_resolver = EntityResolver(core)

        # Resolve semantic-domain provenance before ordinary name lookup.  Deixis,
        # already integrated candidate_refs, and turn-local entity_refs are strong
        # identity evidence; a bare matching name is only a retrieval hint and must
        # not pull an assertion across C/P boundaries.  Once this provisional domain
        # is known, lexical entity lookup is restricted to that domain.
        provenance_refs: list[Ref] = []
        for actant in effective_actants:
            if actant.entity_ref in existential_vars:
                continue
            if actant.candidate_ref is not None:
                ref = local_refs.get(actant.candidate_ref)
                if ref is not None:
                    provenance_refs.append(ref)
                continue
            if actant.proposition is not None:
                for local_id in actant.proposition.leaf_refs():
                    ref = local_refs.get(local_id)
                    if ref is not None:
                        provenance_refs.append(ref)
                continue
            if actant.entity_ref is not None and actant.entity_ref in entity_local_refs:
                provenance_refs.append(entity_local_refs[actant.entity_ref])
                continue
            if actant.composition is not None:
                continue
            resolution_candidate = (
                entity_anchors.get(actant.entity_ref, actant)
                if actant.entity_ref is not None
                else actant
            )
            deictic = entity_resolver.deixis.resolve(
                resolution_candidate,
                context,
                first_person_ref=speaker_ref,
                second_person_ref=addressee_ref,
            )
            if deictic is not None:
                provenance_refs.append(deictic)
        domain_locked = forced_domain is not None or bool(provenance_refs)
        provisional_domain = forced_domain or DomainRouter(core).route_external(
            tuple(provenance_refs)
        )
        lexical_lookup_domain = provisional_domain if domain_locked else None

        staged: dict[
            ActantRole,
            Ref | BoundVar | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan | _CompositionPlan | _ReferenceAlternativesPlan,
        ] = {}
        staged_corefs: dict[ActantRole, str] = {}
        existing_refs: list[Ref] = []
        for actant in effective_actants:
            if actant.entity_ref in existential_vars:
                staged[actant.role] = existential_vars[actant.entity_ref]
                continue
            if actant.role is ActantRole.TIME and actant.temporal is not None:
                if not actant.temporal.resolved or actant.temporal.value is None:
                    raise CandidateValidationError(
                        f"Unresolved temporal actant reached Integration: {candidate.local_id}"
                    )
                time_ref, _time_created = ensure_time_entity(core, actant.temporal.value)
                staged[actant.role] = time_ref
                existing_refs.append(time_ref)
                continue

            if actant.role in alternative_role_options:
                option_members: list[
                    tuple[str | None, Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan]
                ] = []
                for option in alternative_role_options[actant.role]:
                    if option.candidate_ref is not None or option.composition is not None:
                        raise CandidateValidationError(
                            f"Runtime alternatives may vary only canonical entity reference in {candidate.local_id}"
                        )
                    if option.entity_ref is not None and option.entity_ref in entity_local_refs:
                        plan: Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan = entity_local_refs[option.entity_ref]
                    else:
                        resolution_candidate = (
                            entity_anchors.get(option.entity_ref, option)
                            if option.entity_ref is not None
                            else option
                        )
                        resolution = entity_resolver.resolve(
                            resolution_candidate,
                            context,
                            first_person_ref=speaker_ref,
                            second_person_ref=addressee_ref,
                            preferred_domain=lexical_lookup_domain,
                        )
                        plan = resolution.ref if isinstance(resolution, ExistingEntity) else resolution
                    if isinstance(plan, Ref):
                        existing_refs.append(plan)
                    option_members.append((option.entity_ref, plan))
                base_for_role = next(
                    (item for item in candidate.actants if item.role == actant.role),
                    None,
                )
                staged[actant.role] = _ReferenceAlternativesPlan(
                    mention=(
                        (base_for_role.mention or base_for_role.normalized_hint)
                        if base_for_role is not None
                        else (actant.mention or actant.normalized_hint or candidate.predicate.surface)
                    ),
                    members=tuple(option_members),
                )
                continue

            if actant.proposition is not None:
                def resolve_expr(expr: PropositionExprCandidate) -> Ref:
                    if expr.operator is PropositionOperator.REF:
                        assert expr.ref is not None
                        try:
                            return local_refs[expr.ref]
                        except KeyError as exc:
                            raise CandidateValidationError(
                                f"proposition ref not integrated yet: {expr.ref}"
                            ) from exc
                    members = tuple(resolve_expr(member) for member in expr.members)
                    domain = forced_domain if forced_domain is not None else DomainRouter(core).route_external(members)
                    function_id = (
                        "NOT"
                        if expr.operator in {PropositionOperator.NOT, PropositionOperator.FALSE}
                        else expr.operator.value
                    )
                    function, _ = core.ensure_function(domain, function_id, members)
                    return core.ref(function.uid)
                ref = resolve_expr(actant.proposition)
                staged[actant.role] = ref
                existing_refs.append(ref)
                continue

            if actant.candidate_ref is not None:
                try:
                    ref = local_refs[actant.candidate_ref]
                except KeyError as exc:
                    raise CandidateValidationError(
                        f"candidate_ref not integrated yet: {actant.candidate_ref}"
                    ) from exc
                staged[actant.role] = ref
                existing_refs.append(ref)
                continue

            if actant.entity_ref is not None and actant.entity_ref in entity_local_refs:
                ref = entity_local_refs[actant.entity_ref]
                staged[actant.role] = ref
                existing_refs.append(ref)
                continue

            if actant.entity_ref is not None:
                staged_corefs[actant.role] = actant.entity_ref

            if actant.composition is not None:
                member_plans: list[Ref | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan] = []
                for member in actant.composition.members:
                    member_candidate = ActantCandidate(
                        role=actant.role,
                        mention=member.mention,
                        normalized_hint=member.normalized_hint,
                        semantic_hint=member.semantic_hint,
                        evidence=member.evidence,
                    )
                    member_resolution = entity_resolver.resolve(
                        member_candidate,
                        context,
                        first_person_ref=speaker_ref,
                        second_person_ref=addressee_ref,
                        preferred_domain=lexical_lookup_domain,
                    )
                    if isinstance(member_resolution, ExistingEntity):
                        member_plans.append(member_resolution.ref)
                        existing_refs.append(member_resolution.ref)
                    else:
                        member_plans.append(member_resolution)
                staged[actant.role] = _CompositionPlan(
                    actant.composition.operator.value, tuple(member_plans)
                )
                continue

            resolution_candidate = (
                entity_anchors.get(actant.entity_ref, actant)
                if actant.entity_ref is not None
                else actant
            )
            resolution = entity_resolver.resolve(
                resolution_candidate,
                context,
                first_person_ref=speaker_ref,
                second_person_ref=addressee_ref,
                preferred_domain=lexical_lookup_domain,
            )
            if isinstance(resolution, ExistingEntity):
                staged[actant.role] = resolution.ref
                existing_refs.append(resolution.ref)
            else:
                staged[actant.role] = resolution

        domain = (
            provisional_domain
            if domain_locked
            else DomainRouter(core).route_external(tuple(existing_refs))
        )
        actants: dict[ActantRole, Ref | BoundVar] = {}
        ambiguous = False

        for role, item in staged.items():
            coref_id = staged_corefs.get(role)
            # A turn-local entity_ref is an identity commitment, not merely a
            # similarity hint. Several roles inside the *same* assertion may be
            # bound to the same previously unseen participant (for example
            # reflexive/coreferential structures). Staging happens before any new
            # entity is committed, so each occurrence can legitimately hold an
            # equivalent NewEntityPlan. Once the first occurrence materializes,
            # every later occurrence must reuse that canonical ref instead of
            # creating a second M and then reporting a false inconsistency.
            if coref_id is not None and coref_id in entity_local_refs:
                prior = entity_local_refs[coref_id]
                if isinstance(item, Ref) and item != prior:
                    raise CandidateValidationError(
                        f"entity_ref {coref_id!r} resolved inconsistently inside one perception result"
                    )
                actants[role] = prior
                continue

            if isinstance(item, BoundVar):
                actants[role] = item
            elif isinstance(item, (Ref, NewEntityPlan, EquivalentLiteralPlan, AmbiguousEntityPlan)):
                ref, item_ambiguous = self._materialize_entity_plan(core, item, domain)
                actants[role] = ref
                ambiguous = ambiguous or item_ambiguous
            elif isinstance(item, _ReferenceAlternativesPlan):
                member_refs: list[Ref] = []
                for member_coref_id, member in item.members:
                    prior = entity_local_refs.get(member_coref_id) if member_coref_id is not None else None
                    if prior is not None:
                        if isinstance(member, Ref) and member != prior:
                            raise CandidateValidationError(
                                f"entity_ref {member_coref_id!r} resolved inconsistently inside one perception result"
                            )
                        ref = prior
                    elif isinstance(member, Ref):
                        ref = member
                    elif isinstance(member, (NewEntityPlan, EquivalentLiteralPlan, AmbiguousEntityPlan)):
                        ref, member_ambiguous = self._materialize_entity_plan(core, member, domain)
                        ambiguous = ambiguous or member_ambiguous
                    else:
                        raise AssertionError(f"Unhandled alternative member: {member!r}")
                    if member_coref_id is not None:
                        prior = entity_local_refs.get(member_coref_id)
                        if prior is not None and prior != ref:
                            raise CandidateValidationError(
                                f"entity_ref {member_coref_id!r} resolved inconsistently inside one perception result"
                            )
                        entity_local_refs[member_coref_id] = ref
                    if ref not in member_refs:
                        member_refs.append(ref)
                if not member_refs:
                    raise CandidateValidationError(
                        f"Runtime alternatives produced no canonical referents in {candidate.local_id}"
                    )
                if len(member_refs) == 1:
                    actants[role] = member_refs[0]
                else:
                    group = core.add_group(
                        domain,
                        tuple(member_refs),
                        meta={
                            "TYPE": "AMBIGUOUS_REFERENCE",
                            "mention": item.mention,
                            "gc_auto_created": True,
                        },
                    )
                    actants[role] = core.ref(group.uid)
                    ambiguous = True
            elif isinstance(item, _CompositionPlan):
                member_refs: list[Ref] = []
                for member in item.members:
                    if isinstance(member, Ref):
                        member_refs.append(member)
                    elif isinstance(member, (NewEntityPlan, EquivalentLiteralPlan, AmbiguousEntityPlan)):
                        ref, member_ambiguous = self._materialize_entity_plan(core, member, domain)
                        member_refs.append(ref)
                        ambiguous = ambiguous or member_ambiguous
                    else:
                        raise AssertionError(f"Unhandled composition member: {member!r}")
                function, _created = core.ensure_function(domain, item.operator, tuple(member_refs))
                actants[role] = core.ref(function.uid)
            else:
                raise AssertionError(f"Unhandled staged actant: {item!r}")

            if coref_id is not None:
                resolved = actants[role]
                prior = entity_local_refs.get(coref_id)
                if prior is not None and prior != resolved:
                    raise CandidateValidationError(
                        f"entity_ref {coref_id!r} resolved inconsistently inside one perception result"
                    )
                entity_local_refs[coref_id] = resolved

        nominal_relations = self._materialize_nominal_relations(
            core,
            effective_actants,
            actants,
            context,
            domain=domain,
            speaker_ref=speaker_ref,
            addressee_ref=addressee_ref,
            entity_local_refs=entity_local_refs,
            semantic_scope=(semantic_scope or ("NEGATED" if candidate.negated else None)),
        )

        scoped_meta: dict[str, object] = {}
        if semantic_scope:
            scoped_meta["semantic_scope"] = semantic_scope
        if candidate.temporal_mode is not None:
            scoped_meta["temporal_mode"] = candidate.temporal_mode.value
        node, created = core.add_or_enrich_hypernode(
            domain,
            core.ref(template.uid),
            actants,
            weight=self.config.initial_hypernode_weight,
            meta=(scoped_meta or None),
            count_occurrence=count_occurrence,
        )
        return IntegratedAssertion(
            local_id=candidate.local_id,
            ref=core.ref(node.uid),
            domain=domain,
            created=created,
            ambiguous=ambiguous,
            semantic_scope=semantic_scope,
            nominal_relations=nominal_relations,
        )
