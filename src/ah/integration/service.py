from __future__ import annotations

from dataclasses import dataclass, replace

from ah.config import IntegrationSettings

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.core.signatures import hypernode_signature
from ah.model import ActantRole, Domain, FunctionSymbol, Group, Hypernode, Property, Ref, RefKind, SemanticEntity
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    StructuralClarificationSpec,
)

from .candidate_validator import CandidateValidator
from .contracts import (
    ActivationSeedRequest,
    ClarificationOption,
    ClarificationRequest,
    ClarificationResolutionCommit,
    ClarificationUse,
    IntegratedAssertion,
    IntegratedConditional,
    IntegratedRelation,
    IntegrationCommit,
    RefutationRequest,
    SeedReason,
    TemplateRequest,
)
from .correction import SemanticCorrectionService
from .domain_router import DomainRouter
from .entity_resolver import (
    AmbiguousEntityPlan,
    EntityResolver,
    ExistingEntity,
    NewEntityPlan,
)
from .errors import CandidateValidationError, IntegrationError
from .experience_mapper import ExperienceMapper
from .template_resolver import TemplateResolver


_ENTITY_PRONOUNS = {
    "я", "мы", "ты", "вы", "он", "она", "оно", "они",
    "меня", "мне", "мной", "нас", "нам", "нами",
    "тебя", "тебе", "тобой", "вас", "вам", "вами",
    "его", "ему", "им", "неё", "нее", "ей", "ею", "её",
    "их", "им", "ими",
}


@dataclass(frozen=True, slots=True)
class _CompositionPlan:
    operator: str
    members: tuple[Ref | NewEntityPlan | AmbiguousEntityPlan, ...]


@dataclass(frozen=True, slots=True)
class _ReferenceAlternativesPlan:
    """Canonicalization plan for one role with several runtime entity readings."""

    mention: str
    members: tuple[
        tuple[str | None, Ref | NewEntityPlan | AmbiguousEntityPlan], ...
    ]


@dataclass(frozen=True, slots=True)
class IntegrationConfig:
    initial_hypernode_weight: float
    experience_hypernode_weight: float
    follow_link_weight: float
    cause_link_weight: float = 0.2

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_hypernode_weight", self.initial_hypernode_weight),
            ("experience_hypernode_weight", self.experience_hypernode_weight),
            ("follow_link_weight", self.follow_link_weight),
            ("cause_link_weight", self.cause_link_weight),
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
        )


class IntegrationService:
    def __init__(self, core: AHCore, config: IntegrationConfig) -> None:
        self.core = core
        self.config = config
        self.validator = CandidateValidator()

    def template_requests(self, result: PerceptionResult) -> tuple[TemplateRequest, ...]:
        """Return only predicates that need a Perception-layer T proposal.

        This is a deterministic read-only preflight. It never creates S/T and it
        never asks an LLM. For each unknown predicate it also preserves a minimal
        *noncanonical* textual view of already observed role bindings. Perception
        receives only the explicit schema of the current semantic act; it does not
        need to predict absent future valency. Canonical refs/UIDs are deliberately
        not exposed through this request.
        """
        grouped: dict[str, dict[str, object]] = {}

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
            key = predicate.lookup_form.casefold()
            entry = grouped.get(key)
            if entry is None:
                entry = {
                    "predicate": predicate,
                    "roles": [],
                    "has_candidate": predicate.template_candidate is not None,
                    "source_context": (source_context or result.source_text),
                    "bindings": [],
                }
                grouped[key] = entry
            else:
                entry["has_candidate"] = bool(entry["has_candidate"]) or predicate.template_candidate is not None
                if source_context and entry["source_context"] == result.source_text:
                    entry["source_context"] = source_context

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
            extra = (query.requested_role,) if query.requested_role is not None else ()
            add(query.predicate, query.actants, extra_roles=extra, source_context=result.source_text)
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
            symbol = self.core.store.find_symbol_by_form(predicate.lookup_form)
            if symbol is None and predicate.surface.strip():
                symbol = self.core.store.find_symbol_by_form(predicate.surface.strip())
            if symbol is not None and self.core.store.find_templates_by_predicate(symbol.uid):
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

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
    ) -> IntegrationCommit:
        if context.user_ref is None:
            raise IntegrationError("External integration requires context.user_ref")
        return self._integrate(result, context, forced_domain=None, speaker_ref=context.user_ref)

    def integrate_external_resolution(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        existing_experience_ref: Ref,
    ) -> IntegrationCommit:
        """Integrate delayed semantics into the original external H experience."""
        if context.user_ref is None:
            raise IntegrationError("External integration requires context.user_ref")
        return self._integrate(
            result,
            context,
            forced_domain=None,
            speaker_ref=context.user_ref,
            existing_experience_ref=existing_experience_ref,
        )

    def integrate_to_h(
        self,
        result: PerceptionResult,
        context: InteractionContext,
    ) -> IntegrationCommit:
        if context.self_ref is None:
            raise IntegrationError("H-only agent integration requires context.self_ref")
        return self._integrate(result, context, forced_domain=Domain.H, speaker_ref=context.self_ref)

    def _integrate(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        forced_domain: Domain | None,
        speaker_ref: Ref,
        existing_experience_ref: Ref | None = None,
    ) -> IntegrationCommit:
        self.validator.validate(result)
        ordered = self.validator.dependency_order(result)

        assertions: list[IntegratedAssertion] = []
        seeds: list[ActivationSeedRequest] = []
        refutations: list[RefutationRequest] = []
        relations: list[IntegratedRelation] = []
        conditionals: list[IntegratedConditional] = []
        local_refs: dict[str, Ref] = {}
        entity_local_refs: dict[str, Ref] = {}
        entity_anchors = self._entity_anchors(result)
        experience_ref: Ref | None = None

        with self.core.transaction() as tx:
            # Predicate/T resolution precedes actant/entity resolution for every
            # semantic act, not only assertions. Query/Command candidates do not
            # create N facts here, but an unknown predicate can still register the
            # validated representational T required by downstream query/behavioral
            # handling.
            for query in result.queries:
                query_roles = [actant.role for actant in query.actants]
                if query.requested_role is not None and query.requested_role not in query_roles:
                    query_roles.append(query.requested_role)
                TemplateResolver(tx, template_domain=Domain.C).resolve(
                    query.predicate, tuple(query_roles)
                )
            for command in result.commands:
                TemplateResolver(tx, template_domain=Domain.C).resolve(
                    command.predicate, tuple(actant.role for actant in command.actants)
                )

            for candidate in ordered:
                # Conditional branches are propositions under a semantic operator,
                # not ordinary world assertions. Skip the asserted-fact path here;
                # they are canonicalized below as scoped N operands of g_IF.
                if candidate.status is not AssertionStatus.ASSERTED:
                    continue
                integrated = self._integrate_assertion(
                    tx,
                    candidate,
                    context,
                    local_refs,
                    entity_local_refs,
                    forced_domain,
                    entity_anchors=entity_anchors,
                    speaker_ref=speaker_ref,
                    addressee_ref=(context.self_ref if speaker_ref == context.user_ref else context.user_ref),
                    count_occurrence=not candidate.negated,
                )

                if candidate.negated:
                    correction = SemanticCorrectionService(tx).refute(integrated.ref)
                    final = IntegratedAssertion(
                        local_id=integrated.local_id,
                        ref=correction.false_ref,
                        domain=integrated.domain,
                        created=correction.false_created,
                        ambiguous=integrated.ambiguous,
                    )
                    assertions.append(final)
                    local_refs[candidate.local_id] = final.ref
                    seeds.extend(correction.activation_seeds)
                    refutations.extend(correction.refutations)
                else:
                    assertions.append(integrated)
                    local_refs[candidate.local_id] = integrated.ref
                    seeds.append(
                        ActivationSeedRequest(
                            integrated.ref,
                            SeedReason.NEW_FACT if integrated.created else SeedReason.REACTIVATED_FACT,
                        )
                    )

            # Conditional branches are canonical proposition content but are not
            # ordinary asserted world facts.  Integrate them as scoped N/G operands,
            # then bind the antecedent and consequent through deterministic IF.
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
                    integrated = self._integrate_assertion(
                        tx,
                        candidate,
                        context,
                        {**local_refs, **conditional_local_refs},
                        entity_local_refs,
                        forced_domain,
                        entity_anchors=entity_anchors,
                        speaker_ref=speaker_ref,
                        addressee_ref=(context.self_ref if speaker_ref == context.user_ref else context.user_ref),
                        count_occurrence=False,
                        semantic_scope="CONDITIONAL",
                    )
                    proposition_ref = integrated.ref
                    if candidate.negated:
                        false_g, _false_created = tx.ensure_function(
                            integrated.domain, "FALSE", (proposition_ref,)
                        )
                        proposition_ref = tx.ref(false_g.uid)
                    conditional_local_refs[local_id] = proposition_ref

                antecedent_members = tuple(conditional_local_refs[item] for item in conditional.antecedent_refs)
                consequent_members = tuple(conditional_local_refs[item] for item in conditional.consequent_refs)

                def compose_and(members: tuple[Ref, ...]) -> Ref:
                    if len(members) == 1:
                        return members[0]
                    domain = DomainRouter(tx).route_external(members) if forced_domain is None else forced_domain
                    conjunction, _ = tx.ensure_function(domain, "AND", members)
                    return tx.ref(conjunction.uid)

                antecedent_ref = compose_and(antecedent_members)
                consequent_ref = compose_and(consequent_members)
                conditional_domain = (
                    forced_domain
                    if forced_domain is not None
                    else DomainRouter(tx).route_external((antecedent_ref, consequent_ref))
                )
                function, created = tx.ensure_function(
                    conditional_domain, "IF", (antecedent_ref, consequent_ref)
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
                seeds.append(
                    ActivationSeedRequest(
                        conditional_ref,
                        SeedReason.NEW_FACT if created else SeedReason.REACTIVATED_FACT,
                    )
                )

            # Directional situation relations are materialized only after all local
            # assertion references exist. L is a relation/channel, not an excitation
            # node, so relation creation does not add activation seeds.
            for relation in result.relations:
                # Relations wholly or partly inside a non-asserted conditional
                # branch must not leak into canonical world knowledge either.
                if relation.source_ref not in local_refs or relation.target_ref not in local_refs:
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
            semantic_refs = tuple(item.ref for item in assertions) + tuple(item.ref for item in conditionals)
            if existing_experience_ref is None:
                experience = mapper.record_turn(
                    source_text=result.source_text,
                    speaker_ref=speaker_ref,
                    semantic_refs=semantic_refs,
                    context=context,
                )
                experience_ref = experience.event_ref
                seeds.append(ActivationSeedRequest(experience.event_ref, SeedReason.EXPERIENCE))
            else:
                experience = mapper.attach_content(existing_experience_ref, semantic_refs)
                experience_ref = experience.event_ref

        assert experience_ref is not None
        context.last_experience_ref = experience_ref
        clarifications = self._clarification_requests(tuple(assertions))
        return IntegrationCommit(
            assertions=tuple(assertions),
            experience_ref=experience_ref,
            activation_seeds=tuple(seeds),
            refutations=tuple(refutations),
            unresolved_queries=result.queries,
            unresolved_commands=result.commands,
            clarification_required=bool(clarifications),
            clarifications=clarifications,
            relations=tuple(relations),
            conditionals=tuple(conditionals),
        )

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
                    walk(child)
                return
            if ref.kind is RefKind.G:
                element = self.core.store.get_element_any_domain(ref.uid)
                if isinstance(element, FunctionSymbol):
                    for child in element.operands:
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
                    contains(child, visited) for child in element.operands
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
                    if contains(value, set())
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
                if key != "name" and isinstance(prop.value, (str, int, float, bool))
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
                core.store._remove_uid(link.uid)

            if remove_old and core.store.has_uid(old.uid):
                core.store._remove_uid(old.uid)

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
                    if actant.entity_ref is None or actant.candidate_ref is not None or actant.composition is not None:
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
                count_occurrence=count_occurrence,
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
    ) -> IntegratedAssertion:
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
            if actant.candidate_ref is not None:
                ref = local_refs.get(actant.candidate_ref)
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
            Ref | NewEntityPlan | AmbiguousEntityPlan | _CompositionPlan | _ReferenceAlternativesPlan,
        ] = {}
        staged_corefs: dict[ActantRole, str] = {}
        existing_refs: list[Ref] = []
        for actant in effective_actants:
            if actant.role in alternative_role_options:
                option_members: list[
                    tuple[str | None, Ref | NewEntityPlan | AmbiguousEntityPlan]
                ] = []
                for option in alternative_role_options[actant.role]:
                    if option.candidate_ref is not None or option.composition is not None:
                        raise CandidateValidationError(
                            f"Runtime alternatives may vary only canonical entity reference in {candidate.local_id}"
                        )
                    if option.entity_ref is not None and option.entity_ref in entity_local_refs:
                        plan: Ref | NewEntityPlan | AmbiguousEntityPlan = entity_local_refs[option.entity_ref]
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
                member_plans: list[Ref | NewEntityPlan | AmbiguousEntityPlan] = []
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
        actants: dict[ActantRole, Ref] = {}
        ambiguous = False

        for role, item in staged.items():
            if isinstance(item, Ref):
                actants[role] = item
            elif isinstance(item, NewEntityPlan):
                entity = core.add_entity(
                    domain,
                    properties={"name": Property("name", item.name, "str")},
                    meta={"gc_auto_created": True},
                )
                actants[role] = core.ref(entity.uid)
            elif isinstance(item, AmbiguousEntityPlan):
                group = core.add_group(
                    domain,
                    item.candidates,
                    meta={
                        "TYPE": "AMBIGUOUS_REFERENCE",
                        "mention": item.mention,
                        "gc_auto_created": True,
                    },
                )
                actants[role] = core.ref(group.uid)
                ambiguous = True
            elif isinstance(item, _ReferenceAlternativesPlan):
                member_refs: list[Ref] = []
                for coref_id, member in item.members:
                    if isinstance(member, Ref):
                        ref = member
                    elif isinstance(member, NewEntityPlan):
                        entity = core.add_entity(
                            domain,
                            properties={"name": Property("name", member.name, "str")},
                            meta={"gc_auto_created": True},
                        )
                        ref = core.ref(entity.uid)
                    elif isinstance(member, AmbiguousEntityPlan):
                        group = core.add_group(
                            domain,
                            member.candidates,
                            meta={
                                "TYPE": "AMBIGUOUS_REFERENCE",
                                "mention": member.mention,
                                "gc_auto_created": True,
                            },
                        )
                        ref = core.ref(group.uid)
                    else:
                        raise AssertionError(f"Unhandled alternative member: {member!r}")
                    if coref_id is not None:
                        prior = entity_local_refs.get(coref_id)
                        if prior is not None and prior != ref:
                            raise CandidateValidationError(
                                f"entity_ref {coref_id!r} resolved inconsistently inside one perception result"
                            )
                        entity_local_refs[coref_id] = ref
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
                    elif isinstance(member, NewEntityPlan):
                        entity = core.add_entity(
                            domain,
                            properties={"name": Property("name", member.name, "str")},
                            meta={"gc_auto_created": True},
                        )
                        member_refs.append(core.ref(entity.uid))
                    elif isinstance(member, AmbiguousEntityPlan):
                        group = core.add_group(
                            domain,
                            member.candidates,
                            meta={
                                "TYPE": "AMBIGUOUS_REFERENCE",
                                "mention": member.mention,
                                "gc_auto_created": True,
                            },
                        )
                        member_refs.append(core.ref(group.uid))
                        ambiguous = True
                    else:
                        raise AssertionError(f"Unhandled composition member: {member!r}")
                function, _created = core.ensure_function(domain, item.operator, tuple(member_refs))
                actants[role] = core.ref(function.uid)
            else:
                raise AssertionError(f"Unhandled staged actant: {item!r}")

            coref_id = staged_corefs.get(role)
            if coref_id is not None:
                resolved = actants[role]
                prior = entity_local_refs.get(coref_id)
                if prior is not None and prior != resolved:
                    raise CandidateValidationError(
                        f"entity_ref {coref_id!r} resolved inconsistently inside one perception result"
                    )
                entity_local_refs[coref_id] = resolved

        scoped_meta = {"semantic_scope": semantic_scope} if semantic_scope else None
        node, created = core.add_hypernode(
            domain,
            core.ref(template.uid),
            actants,
            weight=self.config.initial_hypernode_weight,
            meta=scoped_meta,
            count_occurrence=count_occurrence,
        )
        return IntegratedAssertion(
            local_id=candidate.local_id,
            ref=core.ref(node.uid),
            domain=domain,
            created=created,
            ambiguous=ambiguous,
        )
