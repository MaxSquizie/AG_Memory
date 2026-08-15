from __future__ import annotations

from dataclasses import dataclass

from ah.config import IntegrationSettings

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Property, Ref
from ah.perception import ActantCandidate, AssertionCandidate, AssertionStatus, PerceptionResult

from .candidate_validator import CandidateValidator
from .contracts import (
    ActivationSeedRequest,
    IntegratedAssertion,
    IntegratedRelation,
    IntegrationCommit,
    RefutationRequest,
    SeedReason,
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

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
    ) -> IntegrationCommit:
        if context.user_ref is None:
            raise IntegrationError("External integration requires context.user_ref")
        return self._integrate(result, context, forced_domain=None, speaker_ref=context.user_ref)

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
    ) -> IntegrationCommit:
        self.validator.validate(result)
        ordered = self.validator.dependency_order(result)

        assertions: list[IntegratedAssertion] = []
        seeds: list[ActivationSeedRequest] = []
        refutations: list[RefutationRequest] = []
        relations: list[IntegratedRelation] = []
        local_refs: dict[str, Ref] = {}
        entity_local_refs: dict[str, Ref] = {}
        entity_anchors = self._entity_anchors(result)
        experience_ref: Ref | None = None

        with self.core.transaction() as tx:
            for candidate in ordered:
                # Conditional branches are propositions under a conditional
                # operator, not ordinary world assertions. Preserve them in the
                # PerceptionResult/H experience, but never commit them as C/P/H
                # facts until conditional inference is implemented explicitly.
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

            experience = ExperienceMapper(
                tx,
                event_weight=self.config.experience_hypernode_weight,
                follow_weight=self.config.follow_link_weight,
            ).record_turn(
                source_text=result.source_text,
                speaker_ref=speaker_ref,
                semantic_refs=tuple(item.ref for item in assertions),
                context=context,
            )
            experience_ref = experience.event_ref
            seeds.append(ActivationSeedRequest(experience.event_ref, SeedReason.EXPERIENCE))

        assert experience_ref is not None
        context.last_experience_ref = experience_ref
        return IntegrationCommit(
            assertions=tuple(assertions),
            experience_ref=experience_ref,
            activation_seeds=tuple(seeds),
            refutations=tuple(refutations),
            unresolved_queries=result.queries,
            unresolved_commands=result.commands,
            clarification_required=any(item.ambiguous for item in assertions),
            relations=tuple(relations),
        )

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
            for actant in assertion.actants:
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
        _allow_or_lift: bool = True,
    ) -> IntegratedAssertion:
        if _allow_or_lift:
            lifted = self._integrate_disjunctive_assertion(
                core, candidate, context, local_refs, entity_local_refs, forced_domain,
                entity_anchors=entity_anchors,
                speaker_ref=speaker_ref, addressee_ref=addressee_ref,
                count_occurrence=count_occurrence,
            )
            if lifted is not None:
                return lifted

        roles = tuple(actant.role for actant in candidate.actants)
        template_domain = forced_domain if forced_domain is not None else Domain.C
        template = TemplateResolver(core, template_domain=template_domain).resolve(
            candidate.predicate, roles
        ).template
        entity_resolver = EntityResolver(core)

        staged: dict[ActantRole, Ref | NewEntityPlan | AmbiguousEntityPlan | _CompositionPlan] = {}
        staged_corefs: dict[ActantRole, str] = {}
        existing_refs: list[Ref] = []
        for actant in candidate.actants:
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
            )
            if isinstance(resolution, ExistingEntity):
                staged[actant.role] = resolution.ref
                existing_refs.append(resolution.ref)
            else:
                staged[actant.role] = resolution

        domain = forced_domain or DomainRouter(core).route_external(tuple(existing_refs))
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

        node, created = core.add_hypernode(
            domain,
            core.ref(template.uid),
            actants,
            weight=self.config.initial_hypernode_weight,
            count_occurrence=count_occurrence,
        )
        return IntegratedAssertion(
            local_id=candidate.local_id,
            ref=core.ref(node.uid),
            domain=domain,
            created=created,
            ambiguous=ambiguous,
        )
