from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from ah.agent import InteractionContext
from ah.model import ActantRole, Domain, Property, RefKind, SemanticEntity
from ah.perception import PerceptionResult
from ah.perception.naming_semantics import NamingAssertionCandidate
from ah.perception.query_semantics import EventSetQueryCandidate
from ah.temporal import TemporalAnchorContext, TemporalNormalizer, exact_datetime_from_ref

from .contracts import IntegrationCommit
from .entity_resolver import EntityResolver, ExistingEntity
from .errors import CandidateValidationError
from .service import IntegrationService as _BaseIntegrationService


class NamingAwareIntegrationService(_BaseIntegrationService):
    """Consume naming/open-event semantics and close turn-anchored temporal values.

    Three source structures deliberately need a narrow adapter before ordinary
    canonical Integration:

    * ``NamingAssertionCandidate`` assigns a conventional name/alias to an already
      resolved entity. It must enrich that M identity and must not manufacture a
      world proposition from the nominal shell used by the source language.
    * ``EventSetQueryCandidate`` asks for matching factual events with an open
      predicate. The interrogative shell is runtime query structure, so asking the
      question must not create/expand a canonical predicate template.
    * a source actant already classified as ``TIME`` is normalized against the
      authoritative turn/source timestamp here, for assertions, queries and
      commands alike. Perception may establish the temporal *role* without owning
      the wall-clock anchor; Integration is the first layer that has that anchor.

    Ordinary assertions/queries continue through the unchanged IntegrationService.
    The original H utterance is retained and its pragmatic kinds are restored after
    the detached runtime structures are consumed.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._temporal_normalizer = TemporalNormalizer()

    @staticmethod
    def _detached_ids(
        naming: tuple[NamingAssertionCandidate, ...],
        event_queries: tuple[EventSetQueryCandidate, ...],
    ) -> set[str]:
        return {
            item.local_id
            for item in (*naming, *event_queries)
            if item.local_id is not None
        }

    @staticmethod
    def _assert_detachable(
        result: PerceptionResult,
        detached_ids: set[str],
    ) -> None:
        """Fail closed if a detached semantic act participates in another structure."""
        if not detached_ids:
            return
        for dependency in result.act_dependencies:
            if dependency.parent_ref in detached_ids or dependency.child_ref in detached_ids:
                raise CandidateValidationError(
                    "Detached naming/event query participates in an act dependency; "
                    "composed semantics require an explicit typed integration path"
                )
        for relation in result.relations:
            if relation.source_ref in detached_ids or relation.target_ref in detached_ids:
                raise CandidateValidationError(
                    "Detached naming/event query participates in a situation relation"
                )
        for root in result.proposition_roots:
            if detached_ids.intersection(root.expression.leaf_refs()):
                raise CandidateValidationError(
                    "Detached naming assertion participates in a proposition formula"
                )

    def _temporal_anchors(
        self,
        context: InteractionContext,
        source_timestamp: datetime | None,
    ) -> TemporalAnchorContext:
        experience_timestamp = (
            exact_datetime_from_ref(self.core, context.now_ref)
            if context.now_ref is not None
            else None
        )
        return TemporalAnchorContext(
            source_timestamp=source_timestamp,
            experience_timestamp=experience_timestamp,
        )

    def _normalize_time_actant(self, actant, anchors: TemporalAnchorContext):
        """Attach a TemporalCandidate only to a source-grounded plain TIME actant.

        The role itself is already a Perception decision. This method merely turns
        its lexical temporal value (for example ``вчера``) into the same canonical
        temporal representation used by storage. Structured proposition/entity
        references and actants that already own a temporal candidate are untouched.
        """
        if (
            actant.role is not ActantRole.TIME
            or actant.temporal is not None
            or actant.candidate_ref is not None
            or actant.entity_ref is not None
            or actant.composition is not None
            or actant.proposition is not None
        ):
            return actant
        text = actant.lookup_text
        if not text:
            return actant
        temporal = self._temporal_normalizer.normalize(text, anchors)
        return actant if temporal is None else replace(actant, temporal=temporal)

    def _normalize_assertion_temporals(self, assertion, anchors: TemporalAnchorContext):
        actants = tuple(self._normalize_time_actant(item, anchors) for item in assertion.actants)
        alternatives = tuple(
            self._normalize_assertion_temporals(item, anchors)
            for item in assertion.alternatives
        )
        if actants == assertion.actants and alternatives == assertion.alternatives:
            return assertion
        return replace(assertion, actants=actants, alternatives=alternatives)

    def _normalize_temporals(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        source_timestamp: datetime | None,
    ) -> PerceptionResult:
        """Resolve explicit TIME actants from one authoritative turn anchor.

        This is intentionally shared by facts and questions. Without this boundary,
        an assertion could store a plain entity named ``вчера`` while a later query
        used a canonical date-valued temporal entity, making two semantically
        identical time constraints impossible to match.
        """
        anchors = self._temporal_anchors(context, source_timestamp)
        assertions = tuple(
            self._normalize_assertion_temporals(item, anchors)
            for item in result.assertions
        )
        queries = tuple(
            replace(
                query,
                actants=tuple(
                    self._normalize_time_actant(item, anchors)
                    for item in query.actants
                ),
            )
            for query in result.queries
        )
        commands = tuple(
            replace(
                command,
                actants=tuple(
                    self._normalize_time_actant(item, anchors)
                    for item in command.actants
                ),
            )
            for command in result.commands
        )
        if (
            assertions == result.assertions
            and queries == result.queries
            and commands == result.commands
        ):
            return result
        return replace(
            result,
            assertions=assertions,
            queries=queries,
            commands=commands,
        )

    def template_requests(self, result: PerceptionResult):
        """Do not request canonical T schemas for identity/event-query source shells."""
        filtered = replace(
            result,
            assertions=tuple(
                item
                for item in result.assertions
                if not isinstance(item, NamingAssertionCandidate)
            ),
            queries=tuple(
                item
                for item in result.queries
                if not isinstance(item, EventSetQueryCandidate)
            ),
        )
        return super().template_requests(filtered)

    @staticmethod
    def _alias_values(entity: SemanticEntity) -> list[str]:
        prop = entity.properties.get("aliases")
        if prop is None:
            return []
        raw = prop.value
        values = raw if isinstance(raw, (tuple, list, set, frozenset)) else (raw,)
        out: list[str] = []
        seen: set[str] = set()
        for item in values:
            value = str(item).strip()
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                out.append(value)
        return out

    def _apply_naming_assertions(
        self,
        core,
        naming: tuple[NamingAssertionCandidate, ...],
        context: InteractionContext,
    ) -> None:
        resolver = EntityResolver(core)
        for assertion in naming:
            owner = assertion.owner
            assert owner is not None
            resolved = resolver.resolve(
                owner,
                context,
                first_person_ref=context.user_ref,
                second_person_ref=context.self_ref,
                preferred_domain=Domain.P,
            )
            if not isinstance(resolved, ExistingEntity):
                raise CandidateValidationError(
                    f"Naming owner is not a uniquely existing entity: {assertion.local_id}"
                )
            if resolved.ref.kind is not RefKind.M:
                raise CandidateValidationError("Naming owner must resolve to canonical M")
            entity = core.store.get_element_any_domain(resolved.ref.uid)
            if not isinstance(entity, SemanticEntity):
                raise CandidateValidationError("Naming owner does not reference SemanticEntity")

            alias = assertion.name_value.strip()
            alias_key = alias.casefold()
            primary = entity.properties.get("name")
            aliases = self._alias_values(entity)
            properties = dict(entity.properties)
            changed = False

            if not (
                primary is not None
                and str(primary.value).strip().casefold() == alias_key
            ) and alias_key not in {item.casefold() for item in aliases}:
                aliases.append(alias)
                existing_prop = entity.properties.get("aliases")
                properties["aliases"] = Property(
                    "aliases",
                    tuple(aliases),
                    existing_prop.type_name if existing_prop is not None else "str[]",
                    existing_prop.unit if existing_prop is not None else None,
                )
                changed = True

            # USER/SELF are individual deictic identities. Once a source explicitly
            # names such an identity, record that singular identity guard so the
            # ordinary name resolver cannot later discard the alias merely because
            # the proper-name mention carries grammatical_number=sing.
            meta = dict(entity.meta)
            if (
                str(meta.get("identity_role") or "").upper() in {"USER", "SELF"}
                and meta.get("grammatical_number") is None
            ):
                meta["grammatical_number"] = "sing"
                changed = True

            if not changed:
                continue
            domain = core.store.domain_of(entity.uid)
            if domain is None:
                raise CandidateValidationError("Naming owner has no semantic domain")
            core.edit_element(
                domain,
                replace(entity, properties=properties, meta=meta),
            )

    def _restore_experience_kinds(
        self,
        core,
        commit: IntegrationCommit,
        original: PerceptionResult,
    ) -> None:
        kinds = self._speech_act_kinds(original)
        experience = core.store.get_hypernode(commit.experience_ref.uid)
        raw_current = experience.meta.get("speech_act_kinds", ())
        current_items = (raw_current,) if isinstance(raw_current, str) else raw_current
        current = tuple(
            str(item).strip().upper()
            for item in current_items
            if str(item).strip()
        )
        if current == kinds:
            return
        domain = core.store.domain_of(experience.uid)
        if domain is not Domain.H:
            raise CandidateValidationError("External experience must belong to H")
        core.edit_element(
            Domain.H,
            replace(
                experience,
                meta={**dict(experience.meta), "speech_act_kinds": kinds},
            ),
        )

    def integrate_external(
        self,
        result: PerceptionResult,
        context: InteractionContext,
        *,
        source_timestamp: datetime | None = None,
    ) -> IntegrationCommit:
        normalized = self._normalize_temporals(result, context, source_timestamp)
        naming = tuple(
            item
            for item in normalized.assertions
            if isinstance(item, NamingAssertionCandidate)
        )
        event_queries = tuple(
            item
            for item in normalized.queries
            if isinstance(item, EventSetQueryCandidate)
        )
        detached_ids = self._detached_ids(naming, event_queries)
        self._assert_detachable(normalized, detached_ids)

        ordinary = replace(
            normalized,
            assertions=tuple(
                item
                for item in normalized.assertions
                if not isinstance(item, NamingAssertionCandidate)
            ),
            queries=tuple(
                item
                for item in normalized.queries
                if not isinstance(item, EventSetQueryCandidate)
            ),
        )
        commit = super().integrate_external(
            ordinary,
            context,
            source_timestamp=source_timestamp,
        )

        # Identity metadata and H pragmatic bookkeeping are one deterministic
        # post-commit transaction. If this phase fails, the source utterance still
        # remains durably recorded in H, matching the architecture's failure policy;
        # no false nominal world proposition has been committed.
        with self.core.transaction() as tx:
            self._apply_naming_assertions(tx, naming, context)
            self._restore_experience_kinds(tx, commit, normalized)

        if event_queries:
            commit = replace(
                commit,
                unresolved_queries=commit.unresolved_queries + event_queries,
            )
        return commit