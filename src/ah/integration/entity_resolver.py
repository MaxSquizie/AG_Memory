from __future__ import annotations

from dataclasses import dataclass

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Ref, RefKind
from ah.perception import ActantCandidate
from ah.perception.morphology import build_morphology, stable_normal_form

from .deixis_resolver import DeixisResolver


@dataclass(frozen=True, slots=True)
class ExistingEntity:
    ref: Ref
    # Runtime-only evidence used by query recall/diagnostics. Canonical identity
    # remains ``ref``; supporting facts are not merged into the entity.
    support_refs: tuple[Ref, ...] = ()


@dataclass(frozen=True, slots=True)
class NewEntityPlan:
    name: str
    semantic_hint: str | None = None


@dataclass(frozen=True, slots=True)
class AmbiguousEntityPlan:
    candidates: tuple[Ref, ...]
    mention: str


EntityResolution = ExistingEntity | NewEntityPlan | AmbiguousEntityPlan


class EntityResolver:
    _FIRST_POSSESSIVE = {
        "мой", "моя", "моё", "мое", "мои", "моего", "моей", "моему",
        "моим", "моими", "моих", "мою",
    }
    _SECOND_POSSESSIVE = {
        "твой", "твоя", "твоё", "твое", "твои", "твоего", "твоей", "твоему",
        "твоим", "твоими", "твоих", "твою",
    }
    _RELATIONAL_CIRCUMSTANCE_ROLES = {
        ActantRole.TIME, ActantRole.DURATION, ActantRole.LOCATION, ActantRole.SOURCE,
        ActantRole.CAUSE, ActantRole.PURPOSE, ActantRole.TOOL, ActantRole.MATERIAL,
        ActantRole.AMOUNT, ActantRole.HOW_TO, ActantRole.STATE,
    }

    def __init__(self, core: AHCore, deixis: DeixisResolver | None = None) -> None:
        self.core = core
        self.deixis = deixis or DeixisResolver()
        # Deterministic morphology is used only to recover the nominal head of a
        # possessive description such as ``моего друга``. It never decides identity.
        self.morphology = build_morphology("auto")

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        import re
        return tuple(re.findall(r"[A-Za-zА-Яа-яЁё-]+", text.casefold()))

    def _possessive_owner(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None,
        second_person_ref: Ref | None,
    ) -> Ref | None:
        tokens = self._tokens(candidate.mention or "")
        if not tokens:
            return None
        first = first_person_ref if first_person_ref is not None else context.user_ref
        second = second_person_ref if second_person_ref is not None else context.self_ref
        if any(token in self._FIRST_POSSESSIVE for token in tokens):
            return first
        if any(token in self._SECOND_POSSESSIVE for token in tokens):
            return second
        return None

    def _descriptor_lookup_forms(self, candidate: ActantCandidate) -> tuple[str, ...]:
        forms: list[str] = []
        normalized = (candidate.normalized_hint or "").strip()
        if normalized:
            forms.append(normalized)

        tokens = self._tokens(candidate.mention or "")
        lexical = [
            token for token in tokens
            if token not in self._FIRST_POSSESSIVE and token not in self._SECOND_POSSESSIVE
        ]
        if lexical:
            head = lexical[-1]
            analyses = self.morphology.analyze_all(head)
            normal = stable_normal_form(analyses, poses={"NOUN", "NPRO"})
            if normal and normal not in forms:
                forms.append(normal)
            if head not in forms:
                forms.append(head)
        return tuple(forms)

    def _resolve_relational_reference(
        self,
        owner: Ref,
        descriptor: Ref,
        mention: str,
        *,
        preferred_domain: Domain | None,
    ) -> ExistingEntity | AmbiguousEntityPlan | None:
        """Resolve descriptions like ``мой друг`` through already canonical facts.

        The canonical graph is not rewritten: for
        ``N_ЕСТЬ(SUBJECT=USER, OBJECT=ДРУГ, AUXILLIARY=МИША)`` the descriptor
        ``ДРУГ`` and referent ``МИША`` remain distinct m nodes.  Resolution merely
        follows the shared fact at runtime and returns the third participant.
        """
        candidates: dict[str, tuple[Ref, list[Ref]]] = {}
        for node in self.core.store.hypernodes_for_actant(owner.uid):
            if preferred_domain is not None and self.core.store.domain_of(node.uid) is not preferred_domain:
                continue
            if not any(ref.uid == descriptor.uid for ref in node.actants.values()):
                continue
            support = self.core.ref(node.uid)
            for role, ref in node.actants.items():
                if ref.uid in {owner.uid, descriptor.uid}:
                    continue
                if role in self._RELATIONAL_CIRCUMSTANCE_ROLES or ref.kind is not RefKind.M:
                    continue
                existing = candidates.get(ref.uid)
                if existing is None:
                    candidates[ref.uid] = (ref, [support])
                elif support not in existing[1]:
                    existing[1].append(support)

        if len(candidates) == 1:
            ref, supports = next(iter(candidates.values()))
            return ExistingEntity(ref, tuple(supports))
        if len(candidates) > 1:
            return AmbiguousEntityPlan(
                tuple(item[0] for item in candidates.values()),
                mention,
            )
        return None

    def resolve(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None = None,
        second_person_ref: Ref | None = None,
        preferred_domain: Domain | None = None,
    ) -> EntityResolution:
        deictic = self.deixis.resolve(
            candidate,
            context,
            first_person_ref=first_person_ref,
            second_person_ref=second_person_ref,
        )
        if deictic is not None:
            return ExistingEntity(deictic)

        text = candidate.lookup_text
        if not text:
            raise ValueError("EntityResolver requires text for non-candidate_ref actants")

        # `normalized_hint` is an indexing aid, not a new canonical identity field.
        # Prefer it for deterministic lookup/creation so inflectional variants of
        # the same nominal do not become separate m nodes merely because their
        # surface case differs. Evidence/mention still preserves the source text.
        lookup_forms: list[str] = []
        for value in (candidate.normalized_hint, candidate.mention):
            if value and value.strip() and value.strip() not in lookup_forms:
                lookup_forms.append(value.strip())

        owner = self._possessive_owner(
            candidate, context,
            first_person_ref=first_person_ref,
            second_person_ref=second_person_ref,
        )
        descriptor_forms = self._descriptor_lookup_forms(candidate) if owner is not None else ()

        # A possessive nominal description is a relational reference, not an
        # instruction to merge descriptor and referent identities. Resolve the
        # descriptor first, then traverse already canonical N incidence together
        # with the deictic owner (e.g. USER + ДРУГ -> N_ЕСТЬ -> МИША).
        if owner is not None:
            descriptor_matches = []
            for lookup in descriptor_forms:
                for entity in self.core.store.find_entities_by_name(lookup, preferred_domain):
                    if all(existing.uid != entity.uid for existing in descriptor_matches):
                        descriptor_matches.append(entity)
            if len(descriptor_matches) == 1:
                descriptor_ref = self.core.ref(descriptor_matches[0].uid)
                relational = self._resolve_relational_reference(
                    owner, descriptor_ref, candidate.mention or text,
                    preferred_domain=preferred_domain,
                )
                if relational is not None:
                    return relational
            elif len(descriptor_matches) > 1:
                return AmbiguousEntityPlan(
                    tuple(self.core.ref(entity.uid) for entity in descriptor_matches),
                    candidate.mention or text,
                )

        for lookup in lookup_forms:
            # Name/alias is a retrieval index, never a cross-domain identity key.
            # Once Integration has provenance evidence for the current assertion,
            # lexical resolution stays inside that semantic domain. This prevents
            # a prior generic C entity with the same surface name from hijacking a
            # newly introduced personalized P entity. Stronger identity evidence
            # (deixis, candidate_ref, turn-local entity_ref) is resolved before this
            # lookup and may still route the assertion to P.
            entities = self.core.store.find_entities_by_name(lookup, preferred_domain)
            if len(entities) == 1:
                return ExistingEntity(self.core.ref(entities[0].uid))
            if len(entities) > 1:
                return AmbiguousEntityPlan(
                    tuple(self.core.ref(entity.uid) for entity in entities),
                    lookup,
                )

        canonical_name = lookup_forms[0] if lookup_forms else text
        return NewEntityPlan(canonical_name, candidate.semantic_hint)
