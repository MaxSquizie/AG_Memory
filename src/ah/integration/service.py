from __future__ import annotations

from dataclasses import dataclass

from ah.config import IntegrationSettings

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Property, Ref
from ah.perception import AssertionCandidate, PerceptionResult

from .candidate_validator import CandidateValidator
from .contracts import (
    ActivationSeedRequest,
    IntegratedAssertion,
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


@dataclass(frozen=True, slots=True)
class IntegrationConfig:
    initial_hypernode_weight: float
    experience_hypernode_weight: float
    follow_link_weight: float

    def __post_init__(self) -> None:
        for name, value in (
            ("initial_hypernode_weight", self.initial_hypernode_weight),
            ("experience_hypernode_weight", self.experience_hypernode_weight),
            ("follow_link_weight", self.follow_link_weight),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")

    @classmethod
    def from_settings(cls, settings: IntegrationSettings) -> "IntegrationConfig":
        return cls(
            initial_hypernode_weight=settings.initial_hypernode_weight,
            experience_hypernode_weight=settings.experience_hypernode_weight,
            follow_link_weight=settings.follow_link_weight,
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
        local_refs: dict[str, Ref] = {}
        experience_ref: Ref | None = None

        with self.core.transaction() as tx:
            for candidate in ordered:
                integrated = self._integrate_assertion(
                    tx,
                    candidate,
                    context,
                    local_refs,
                    forced_domain,
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
        )

    def _integrate_assertion(
        self,
        core: AHCore,
        candidate: AssertionCandidate,
        context: InteractionContext,
        local_refs: dict[str, Ref],
        forced_domain: Domain | None,
        *,
        speaker_ref: Ref,
        addressee_ref: Ref | None,
        count_occurrence: bool = True,
    ) -> IntegratedAssertion:
        roles = tuple(actant.role for actant in candidate.actants)
        template_domain = forced_domain if forced_domain is not None else Domain.C
        template = TemplateResolver(core, template_domain=template_domain).resolve(
            candidate.predicate, roles
        ).template
        entity_resolver = EntityResolver(core)

        staged: dict[ActantRole, Ref | NewEntityPlan | AmbiguousEntityPlan] = {}
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

            resolution = entity_resolver.resolve(
                actant,
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
            else:
                raise AssertionError(f"Unhandled staged actant: {item!r}")

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
