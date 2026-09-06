from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re

from ah.agent import InteractionContext
from ah.core import AHCore
from ah.model import ActantRole, Domain, Ref, RefKind, SemanticEntity
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
    literal_kind: str | None = None
    literal_value: str | None = None
    grammatical_number: str | None = None


@dataclass(frozen=True, slots=True)
class EquivalentLiteralPlan:
    candidates: tuple[Ref, ...]
    literal_kind: str
    literal_value: str


@dataclass(frozen=True, slots=True)
class AmbiguousEntityPlan:
    candidates: tuple[Ref, ...]
    mention: str


EntityResolution = ExistingEntity | NewEntityPlan | EquivalentLiteralPlan | AmbiguousEntityPlan


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



    _DECIMAL_LITERAL_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)$")

    @classmethod
    def _numeric_literal_value(cls, text: str | None) -> str | None:
        """Return a canonical decimal value for a bare numeric literal.

        Numeric syntax is deterministic source structure, not semantic inference.
        We deliberately accept only a bare decimal token here: units, dates,
        identifiers and names remain ordinary entity resolution.
        """
        if text is None:
            return None
        raw = text.strip().replace(" ", "")
        if not raw or cls._DECIMAL_LITERAL_RE.fullmatch(raw) is None:
            return None
        normalized = raw.replace(",", ".")
        try:
            value = Decimal(normalized)
        except InvalidOperation:
            return None
        if not value.is_finite():
            return None
        if value == 0:
            return "0"
        rendered = format(value.normalize(), "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered

    @classmethod
    def _entity_matches_numeric_literal(cls, entity, value: str) -> bool:
        explicit_kind = entity.meta.get("literal_kind")
        explicit_value = entity.meta.get("literal_value")
        if explicit_kind == "NUMBER":
            return str(explicit_value) == value

        # Backward compatibility for already persisted memories: before literal
        # identity existed, a number was stored as a bare name-only m node. Do
        # not reinterpret richer objects merely because somebody named one "5".
        if set(entity.properties) != {"name"}:
            return False
        name = entity.properties.get("name")
        return name is not None and cls._numeric_literal_value(str(name.value)) == value

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
            if not any(
                isinstance(ref, Ref) and ref.uid == descriptor.uid
                for ref in node.actants.values()
            ):
                continue
            support = self.core.ref(node.uid)
            for role, ref in node.actants.items():
                if not isinstance(ref, Ref):
                    continue
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

    @staticmethod
    def _filter_by_grammatical_number(entities, number: str | None):
        """Keep lexical identity separate from source grammatical cardinality.

        Lemma lookup intentionally maps both ``матрос`` and ``матросы`` to the
        same lexical name.  A known singular/plural source feature is therefore a
        second deterministic identity constraint.  Entities created before this
        feature (no metadata) are not silently treated as either cardinality;
        ambiguity/duplication is safer than merging distinct discourse referents.
        """
        # Be defensive at the integration boundary too.  Fresh perception now
        # emits plain strings, but an already-running process or imported object
        # may still carry a pymorphy grammeme scalar from an older build.
        normalized_number = str(number) if number is not None else None
        if normalized_number not in {"sing", "plur"}:
            return list(entities)

        result = []
        for entity in entities:
            raw_entity_number = entity.meta.get("grammatical_number")
            entity_number = (
                str(raw_entity_number) if raw_entity_number is not None else None
            )
            if entity_number == normalized_number:
                result.append(entity)
        return result

    def resolve(
        self,
        candidate: ActantCandidate,
        context: InteractionContext,
        *,
        first_person_ref: Ref | None = None,
        second_person_ref: Ref | None = None,
        preferred_domain: Domain | None = None,
        attention_refs: tuple[Ref, ...] = (),
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

        literal_value = self._numeric_literal_value(candidate.lookup_text)
        if literal_value is not None:
            literal_matches: list[Ref] = []
            for domain in Domain:
                for entity in self.core.store.find_entities_by_name(candidate.lookup_text or literal_value, domain):
                    if self._entity_matches_numeric_literal(entity, literal_value):
                        ref = self.core.ref(entity.uid)
                        if all(existing.uid != ref.uid for existing in literal_matches):
                            literal_matches.append(ref)
            # Normalized persisted values can differ lexically (e.g. 5.0 vs 5).
            # Scan only semantic entities when exact-name indexing found nothing.
            if not literal_matches:
                for domain in Domain:
                    for element in self.core.store.elements(domain):
                        if isinstance(element, SemanticEntity) and self._entity_matches_numeric_literal(element, literal_value):
                            ref = self.core.ref(element.uid)
                            if all(existing.uid != ref.uid for existing in literal_matches):
                                literal_matches.append(ref)
            if len(literal_matches) == 1:
                return ExistingEntity(literal_matches[0])
            if len(literal_matches) > 1:
                return EquivalentLiteralPlan(tuple(literal_matches), "NUMBER", literal_value)
            return NewEntityPlan(
                literal_value, candidate.semantic_hint, literal_kind="NUMBER", literal_value=literal_value
            )

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
                active = {ref.uid for ref in attention_refs}
                active_matches = [entity for entity in descriptor_matches if entity.uid in active]
                if len(active_matches) == 1:
                    descriptor_ref = self.core.ref(active_matches[0].uid)
                    relational = self._resolve_relational_reference(
                        owner, descriptor_ref, candidate.mention or text,
                        preferred_domain=preferred_domain,
                    )
                    if relational is not None:
                        return relational
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
            entities = self._filter_by_grammatical_number(
                entities, candidate.grammatical_number
            )
            if len(entities) == 1:
                return ExistingEntity(self.core.ref(entities[0].uid))
            if len(entities) > 1:
                active = {ref.uid for ref in attention_refs}
                active_matches = [entity for entity in entities if entity.uid in active]
                if len(active_matches) == 1:
                    return ExistingEntity(self.core.ref(active_matches[0].uid))
                return AmbiguousEntityPlan(
                    tuple(self.core.ref(entity.uid) for entity in entities),
                    lookup,
                )

        canonical_name = lookup_forms[0] if lookup_forms else text
        return NewEntityPlan(
            canonical_name,
            candidate.semantic_hint,
            grammatical_number=candidate.grammatical_number,
        )
