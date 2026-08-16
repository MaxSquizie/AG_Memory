from __future__ import annotations

from dataclasses import dataclass, replace

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Property, Ref
from ah.perception import PredicateCandidate, TemplateCandidate

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

    def attach_content(
        self,
        event_ref: Ref,
        semantic_refs: tuple[Ref, ...],
    ) -> ExperienceResult:
        """Attach delayed semantic content to an already-recorded H turn.

        Structural clarification records the original external utterance in H before
        its semantics are known.  After the user selects one reading, Integration
        fills that same event's OBJECT instead of creating a duplicate experience.
        """
        if event_ref.kind.value != "N" or not self.core.store.has_uid(event_ref.uid):
            raise IntegrationError("Existing experience must be a canonical H N")
        if self.core.store.domain_of(event_ref.uid) is not Domain.H:
            raise IntegrationError("Existing experience must be in H")
        event = self.core.store.get_hypernode(event_ref.uid)
        if not bool(event.meta.get("event_instance", False)):
            raise IntegrationError("Existing H N is not an experience event")

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

        if content_ref is not None:
            existing = event.actants.get(ActantRole.OBJECT)
            if existing is not None and existing != content_ref:
                raise IntegrationError("Existing experience already has different semantic content")
            if existing is None:
                self.core.edit_element(
                    Domain.H,
                    replace(event, actants={**dict(event.actants), ActantRole.OBJECT: content_ref}),
                )
        return ExperienceResult(event_ref, None)

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
            PredicateCandidate(
                self.predicate_form,
                self.predicate_form,
                template_candidate=TemplateCandidate(tuple(roles)),
            ),
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
