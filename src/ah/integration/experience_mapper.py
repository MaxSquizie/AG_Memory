from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Property, Ref
from ah.perception import PredicateCandidate

from .errors import IntegrationError
from .template_resolver import TemplateResolver


@dataclass(frozen=True, slots=True)
class ExperienceResult:
    event_ref: Ref
    follow_ref: Ref | None


class ExperienceMapper:
    """Represent one dialogue turn as an ordinary semantic event N in H."""

    def __init__(
        self,
        core: AHCore,
        *,
        event_weight: float,
        follow_weight: float,
        predicate_form: str = "высказать",
    ) -> None:
        self.core = core
        self.event_weight = event_weight
        self.follow_weight = follow_weight
        self.predicate_form = predicate_form

    def record_turn(
        self,
        *,
        source_text: str,
        speaker_ref: Ref,
        semantic_refs: tuple[Ref, ...],
        context: InteractionContext,
    ) -> ExperienceResult:
        if not self.core.store.has_uid(speaker_ref.uid):
            raise IntegrationError(f"Unknown speaker ref: {speaker_ref.uid}")

        content_ref: Ref | None = None
        if len(semantic_refs) == 1:
            content_ref = semantic_refs[0]
        elif len(semantic_refs) > 1:
            group = self.core.add_group(
                Domain.H,
                semantic_refs,
                meta={"type": "UTTERANCE_CONTENT", "gc_auto_created": True},
            )
            content_ref = self.core.ref(group.uid)

        roles = [ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME]
        template = TemplateResolver(self.core).resolve(
            PredicateCandidate(self.predicate_form, self.predicate_form),
            tuple(roles),
        ).template

        actants = {ActantRole.SUBJECT: speaker_ref}
        if content_ref is not None:
            actants[ActantRole.OBJECT] = content_ref
        if context.now_ref is not None:
            actants[ActantRole.TIME] = context.now_ref

        event, _ = self.core.add_hypernode(
            Domain.H,
            self.core.ref(template.uid),
            actants,
            weight=self.event_weight,
            properties={"text": Property("text", source_text, "str")},
            meta={"event_instance": True},
            deduplicate=False,
        )
        event_ref = self.core.ref(event.uid)

        follow_ref: Ref | None = None
        if context.last_experience_ref is not None:
            link = self.core.add_link(
                "FOLLOW",
                context.last_experience_ref,
                event_ref,
                weight=self.follow_weight,
            )
            follow_ref = self.core.ref(link.uid)

        return ExperienceResult(event_ref, follow_ref)
