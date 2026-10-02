from __future__ import annotations

import re

from ah.integration.identity_graph import is_identity_name_entity
from ah.model import FunctionSymbol, Group, Ref, RefKind, SemanticEntity
from ah.perception.morphology import build_morphology, material_analyses

from .coordinator_session import AssociationCoordinator as _SessionAssociationCoordinator


class AssociationCoordinator(_SessionAssociationCoordinator):
    """Association search resilient to legacy cross-domain common-noun duplicates.

    Bare common nouns are intended to reuse one canonical semantic entity across
    proposition domains.  Older persisted memories (and memories written before the
    common-nominal anchor existed) can nevertheless contain several M nodes for the
    same bare noun.  Ordinary open-event retrieval can still find those facts by
    their other role constraints, while an association seeded from the canonical M
    cannot reach the duplicate endpoint at all.

    This layer does *not* merge canonical nodes.  It exposes exact-name,
    morphology-confirmed common-noun peers as runtime-only representation bridges.
    Proper names, identity-name helper nodes and rich/literal identities are not
    bridged.  The same equivalence is used for endpoint containment and scoped role
    constraints, so LOCATION and other typed scopes behave consistently with the
    search frontier.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._association_identity_morphology = None

    def _morphology(self):
        value = self._association_identity_morphology
        if value is None:
            value = build_morphology("auto")
            self._association_identity_morphology = value
        return value

    @staticmethod
    def _name_tokens(value: str) -> tuple[str, ...]:
        return tuple(re.findall(r"[A-Za-zА-Яа-яЁё-]+", value.casefold()))

    def _bare_common_nominal_name(self, ref: Ref) -> str | None:
        if ref.kind is not RefKind.M:
            return None
        try:
            entity = self.core.store.get_element_any_domain(ref.uid)
        except Exception:
            return None
        if not isinstance(entity, SemanticEntity):
            return None
        if is_identity_name_entity(entity):
            return None
        if entity.meta.get("identity_role") or entity.meta.get("literal_kind"):
            return None

        name = entity.properties.get("name")
        if name is None or not isinstance(name.value, str) or not name.value.strip():
            return None
        tokens = self._name_tokens(name.value)
        if len(tokens) != 1:
            return None
        head = tokens[0]

        try:
            analyses = material_analyses(tuple(self._morphology().analyze_all(head)))
        except Exception:
            try:
                one = self._morphology().analyze(head)
            except Exception:
                one = None
            analyses = () if one is None else (one,)

        nouns = tuple(item for item in analyses if item.pos == "NOUN")
        if not nouns:
            return None
        proper = tuple(
            item
            for item in nouns
            if {"Name", "Surn", "Patr"} & set(item.grammemes)
        )
        common = tuple(item for item in nouns if item not in proper)
        if not common:
            return None
        if proper:
            best_common = max(float(item.score) for item in common)
            best_proper = max(float(item.score) for item in proper)
            if best_common <= best_proper:
                return None
        return head.replace("ё", "е")

    def _common_nominal_equivalent(self, left: Ref, right: Ref) -> bool:
        if left == right:
            return True
        left_name = self._bare_common_nominal_name(left)
        if left_name is None:
            return False
        right_name = self._bare_common_nominal_name(right)
        return right_name is not None and left_name == right_name

    def _representation_peers(self, ref: Ref) -> tuple[Ref, ...]:
        name = self._bare_common_nominal_name(ref)
        if name is None:
            return ()
        peers: dict[str, Ref] = {}
        try:
            entities = self.core.store.find_entities_by_name(name, None)
        except Exception:
            entities = ()
        for entity in entities:
            try:
                candidate = self.core.ref(entity.uid)
            except Exception:
                continue
            if candidate.uid == ref.uid:
                continue
            if not self._common_nominal_equivalent(ref, candidate):
                continue
            peers[candidate.uid] = candidate
        return tuple(peers[uid] for uid in sorted(peers))

    def _operand_contains(self, operand, target: Ref, seen: set[str] | None = None) -> bool:
        if not isinstance(operand, Ref):
            return False
        if operand == target or self._common_nominal_equivalent(operand, target):
            return True
        seen = set() if seen is None else seen
        if operand.uid in seen:
            return False
        seen.add(operand.uid)
        obj = self._element(operand)
        if isinstance(obj, Group):
            return any(self._operand_contains(member, target, seen) for member in obj.members)
        if isinstance(obj, FunctionSymbol):
            return any(
                self._operand_contains(member, target, seen)
                for member in obj.operands
                if isinstance(member, Ref)
            )
        return False

    def _constraint_value_matches(self, actual: Ref, requested: Ref) -> bool:
        if super()._constraint_value_matches(actual, requested):
            return True
        return self._common_nominal_equivalent(actual, requested)

    def _query_neighbors(self, ref, policy):
        rows = list(super()._query_neighbors(ref, policy))
        seen = {item[0].uid for item in rows}
        for peer in self._representation_peers(ref):
            if peer.uid in seen or not self._allowed(peer, policy):
                continue
            rows.append((peer, "COMMON_NOMINAL_REPRESENTATION", None))
            seen.add(peer.uid)
        rows.sort(key=lambda item: (item[0].uid, item[1], item[2] or ""))
        return tuple(rows)
