from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ah.core import AHCore
from ah.model import ActantRole, Domain, FunctionSymbol, Group, Hypernode, Ref, RefKind


class _SchemaRegistry(Protocol):
    def get(self, canonical_id: str): ...


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    """Addressable canonical conflict set plus its currently opposed expressions."""

    group_ref: Ref
    members: tuple[Ref, ...]
    kind: str
    created: bool = False


class ConflictEngine:
    """Detect and maintain explicit unresolved conflict sets.

    The engine is deliberately conservative.  In the current slice it recognizes
    only formal polarity conflicts ``P`` versus an independently asserted
    ``NOT(P)``.  It never chooses a winner from recency, activation, weight or
    repetition.  The addressable conflict is represented by ordinary canonical
    ``k`` with ``Mt.TYPE=CONFLICT``; operational admissibility remains runtime
    logic and therefore does not turn ``k`` into a hidden logical operator.

    A conflict group may remain in canonical history after a later explicit
    refutation/correction. ``is_unresolved`` is computed from the *current*
    admissibility of its members, so a resolved historical group no longer blocks
    proof without requiring destructive history rewriting.
    """

    TYPE = "CONFLICT"
    KIND_POLARITY = "POLARITY"
    KIND_FUNCTIONAL = "FUNCTIONAL"
    KIND_MUTUAL_EXCLUSION = "MUTUAL_EXCLUSION"

    def __init__(self, core: AHCore, schema_registry: _SchemaRegistry | None = None) -> None:
        self.core = core
        self.schema_registry = schema_registry

    # ---------- canonical/assertion helpers ----------
    def _leaf_scopes(self, ref: Ref, seen: set[str] | None = None) -> set[str]:
        seen = set() if seen is None else seen
        if ref.uid in seen or not self.core.store.has_uid(ref.uid):
            return set()
        seen.add(ref.uid)
        if ref.kind is RefKind.N:
            node = self.core.store.get_hypernode(ref.uid)
            scope = str(node.meta.get("semantic_scope") or "").upper()
            return {scope} if scope else set()
        if ref.kind is not RefKind.G:
            return set()
        obj = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(obj, FunctionSymbol):
            return set()
        out: set[str] = set()
        for operand in obj.operands:
            if isinstance(operand, Ref):
                out.update(self._leaf_scopes(operand, seen))
        return out

    def _has_external_occurrence(self, ref: Ref) -> bool:
        """Whether a C/P expression was top-level content of a user experience."""
        if self.core.store.domain_of(ref.uid) not in {Domain.C, Domain.P}:
            return False

        candidates = [ref]
        for group in self.core.store.groups_containing(ref.uid):
            if self.core.store.domain_of(group.uid) is not Domain.H:
                continue
            if str(group.meta.get("type") or "").upper() != "UTTERANCE_CONTENT":
                continue
            candidates.append(self.core.ref(group.uid))

        for candidate in candidates:
            for node in self.core.store.hypernodes_for_actant(candidate.uid):
                if self.core.store.domain_of(node.uid) is not Domain.H:
                    continue
                if not bool(node.meta.get("event_instance", False)):
                    continue
                if node.actants.get(ActantRole.OBJECT) == candidate:
                    return True
        return False

    def _function_parents(self, ref: Ref, canonical_id: str) -> tuple[tuple[Ref, FunctionSymbol], ...]:
        out: list[tuple[Ref, FunctionSymbol]] = []
        for obj in self.core.store.function_parents(ref.uid):
            try:
                actual = self.core.function_registry.canonical_id(obj.function_id)
            except KeyError:
                continue
            if actual != canonical_id:
                continue
            out.append((self.core.ref(obj.uid), obj))
        out.sort(key=lambda item: item[0].uid)
        return tuple(out)

    def _false_parent(self, ref: Ref) -> Ref | None:
        for parent_ref, obj in self._function_parents(ref, "FALSE"):
            if len(obj.operands) == 1 and obj.operands[0] == ref:
                return parent_ref
        return None

    def _is_asserted_expression(self, ref: Ref) -> bool:
        if not self.core.store.has_uid(ref.uid):
            return False
        if self._false_parent(ref) is not None:
            return False
        if ref.kind is RefKind.N:
            node = self.core.store.get_hypernode(ref.uid)
            if node.meta.get("semantic_scope"):
                return False
            return int(node.meta.get("occurrence_count", 0)) > 0 or bool(
                self.core.resolve_supports(ref)
            )
        if ref.kind is RefKind.G:
            obj = self.core.store.get_element_any_domain(ref.uid)
            if not isinstance(obj, FunctionSymbol):
                return False
            try:
                canonical = self.core.function_registry.canonical_id(obj.function_id)
            except KeyError:
                return False
            if canonical == "FALSE":
                return False
            if not self._has_external_occurrence(ref):
                return False
            scopes = self._leaf_scopes(ref)
            return not bool(scopes & {"EMBEDDED", "QUOTED"})
        return False

    def _not_operand(self, ref: Ref) -> Ref | None:
        if ref.kind is not RefKind.G or not self.core.store.has_uid(ref.uid):
            return None
        obj = self.core.store.get_element_any_domain(ref.uid)
        if not isinstance(obj, FunctionSymbol):
            return None
        try:
            canonical = self.core.function_registry.canonical_id(obj.function_id)
        except KeyError:
            return None
        if canonical != "NOT" or len(obj.operands) != 1:
            return None
        operand = obj.operands[0]
        return operand if isinstance(operand, Ref) else None

    def _asserted_not_parents(self, ref: Ref) -> tuple[Ref, ...]:
        out: list[Ref] = []
        for parent_ref, obj in self._function_parents(ref, "NOT"):
            if len(obj.operands) != 1 or obj.operands[0] != ref:
                continue
            if self._is_asserted_expression(parent_ref):
                out.append(parent_ref)
        return tuple(out)

    @staticmethod
    def _member_key(ref: Ref) -> tuple[str, str]:
        return (ref.kind.value, ref.uid)

    def _conflict_groups_containing(self, ref: Ref) -> tuple[Group, ...]:
        groups: list[Group] = []
        for group in self.core.store.groups_containing(ref.uid):
            if str(group.meta.get("TYPE") or group.meta.get("type") or "").upper() != self.TYPE:
                continue
            groups.append(group)
        return tuple(sorted(groups, key=lambda item: item.uid))

    def _ensure_group(
        self,
        refs: tuple[Ref, ...],
        *,
        kind: str,
        meta: dict[str, object] | None = None,
    ) -> ConflictRecord:
        wanted = set(refs)
        if len(wanted) < 2:
            raise ValueError("Conflict group requires at least two distinct members")
        domains = {self.core.store.domain_of(ref.uid) for ref in wanted}
        if len(domains) != 1 or None in domains:
            raise ValueError("Conflict members must belong to one semantic domain")
        domain = next(iter(domains))
        assert domain is not None

        # Reuse or monotonically widen one semantically identical conflict set.
        # This lets three competing functional values live in one addressable K
        # instead of creating pairwise conflict noise.
        compatible_groups: list[Group] = []
        for ref in wanted:
            for group in self._conflict_groups_containing(ref):
                if str(group.meta.get("conflict_kind") or self.KIND_POLARITY).upper() != kind:
                    continue
                if meta and any(group.meta.get(key) != value for key, value in meta.items()):
                    continue
                if group not in compatible_groups:
                    compatible_groups.append(group)
        if compatible_groups:
            group = sorted(compatible_groups, key=lambda item: item.uid)[0]
            merged = tuple(sorted(set(group.members) | wanted, key=self._member_key))
            if merged != group.members:
                from dataclasses import replace
                group = self.core.edit_element(
                    domain, replace(group, members=merged)
                )
            return ConflictRecord(self.core.ref(group.uid), group.members, kind, False)

        members = tuple(sorted(wanted, key=self._member_key))
        group = self.core.add_group(
            domain,
            members,
            meta={
                "TYPE": self.TYPE,
                "conflict_kind": kind,
                "gc_auto_created": True,
                **dict(meta or {}),
            },
        )
        return ConflictRecord(self.core.ref(group.uid), group.members, kind, True)

    def _ensure_polarity_group(self, positive: Ref, negative: Ref) -> ConflictRecord:
        return self._ensure_group((positive, negative), kind=self.KIND_POLARITY)

    def _functional_conflicts_for(self, ref: Ref) -> tuple[Ref, ...]:
        """Return asserted positive N that violate an explicit functional T slot.

        FUNCTIONAL is conservative-by-default: no registry, no functional flag or
        no explicit output role means no conflict.  All non-output roles (including
        TIME/context roles) must be filled identically on both propositions; a
        missing/different context therefore prevents a false conflict.
        """

        if self.schema_registry is None or ref.kind is not RefKind.N:
            return ()
        if not self._is_asserted_expression(ref):
            return ()
        node = self.core.store.get_hypernode(ref.uid)
        schema = self.schema_registry.get(node.template.uid)
        if not bool(getattr(schema, "functional", False)):
            return ()
        value_role = getattr(schema, "functional_role", None)
        if value_role is None or value_role not in node.actants:
            return ()
        value = node.actants[value_role]

        out: list[Ref] = []
        for other in self.core.store.find_hypernodes_by_template(node.template.uid):
            if other.uid == node.uid:
                continue
            other_ref = self.core.ref(other.uid)
            if self.core.store.domain_of(other.uid) is not self.core.store.domain_of(node.uid):
                continue
            if not self._is_asserted_expression(other_ref):
                continue
            if value_role not in other.actants or other.actants[value_role] == value:
                continue
            left_key = {role: operand for role, operand in node.actants.items() if role is not value_role}
            right_key = {role: operand for role, operand in other.actants.items() if role is not value_role}
            if left_key != right_key:
                continue
            out.append(other_ref)
        return tuple(sorted(out, key=self._member_key))

    def _schema_exclusion_conflicts_for(self, ref: Ref) -> tuple[Ref, ...]:
        """Return asserted positive N excluded by an explicit schema declaration.

        Mutual exclusion is never guessed from predicate names.  It is operational
        only when the registry explicitly declares the other template and a
        non-empty tuple of key roles.  Every key role must be present and equal in
        both propositions; all other differences are allowed because the schema
        declaration itself defines the incompatible states.
        """
        if self.schema_registry is None or ref.kind is not RefKind.N:
            return ()
        if not self._is_asserted_expression(ref):
            return ()
        node = self.core.store.get_hypernode(ref.uid)
        out: list[Ref] = []
        own_schema = self.schema_registry.get(node.template.uid)
        partner_ids = set(getattr(own_schema, "mutually_exclusive_with", ()))
        for other_schema in getattr(self.schema_registry, "items", lambda: ())():
            if node.template.uid.upper() in getattr(other_schema, "mutually_exclusive_with", ()):
                partner_ids.add(other_schema.canonical_id)

        for partner_id in sorted(partner_ids):
            key_roles = getattr(
                self.schema_registry,
                "mutual_exclusion_key",
                lambda _left, _right: None,
            )(node.template.uid, partner_id)
            if not key_roles:
                continue
            for other in self.core.store.find_hypernodes_by_template(partner_id):
                if other.uid == node.uid:
                    continue
                other_ref = self.core.ref(other.uid)
                if self.core.store.domain_of(other.uid) is not self.core.store.domain_of(node.uid):
                    continue
                if not self._is_asserted_expression(other_ref):
                    continue
                if any(role not in node.actants or role not in other.actants for role in key_roles):
                    continue
                if any(node.actants[role] != other.actants[role] for role in key_roles):
                    continue
                out.append(other_ref)
        return tuple(sorted(set(out), key=self._member_key))

    # ---------- public API ----------
    def register_asserted_roots(self, refs: tuple[Ref, ...]) -> tuple[ConflictRecord, ...]:
        """Create/reuse conflict sets touched by newly asserted top-level roots.

        Call after the H occurrence for the turn has been attached, because
        compound ``g`` assertion status is intentionally derived from that
        occurrence rather than from adding forbidden Pr/Mt to ``g``.
        """
        out: dict[str, ConflictRecord] = {}
        for ref in refs:
            if not self.core.store.has_uid(ref.uid):
                continue
            negative_operand = self._not_operand(ref)
            if negative_operand is not None:
                if (
                    self._is_asserted_expression(ref)
                    and self._is_asserted_expression(negative_operand)
                    and self.core.store.domain_of(ref.uid)
                    is self.core.store.domain_of(negative_operand.uid)
                ):
                    record = self._ensure_polarity_group(negative_operand, ref)
                    out[record.group_ref.uid] = record
                continue

            if not self._is_asserted_expression(ref):
                continue
            for negative in self._asserted_not_parents(ref):
                if self.core.store.domain_of(ref.uid) is not self.core.store.domain_of(negative.uid):
                    continue
                record = self._ensure_polarity_group(ref, negative)
                out[record.group_ref.uid] = record

            competitors = self._functional_conflicts_for(ref)
            if competitors:
                node = self.core.store.get_hypernode(ref.uid)
                schema = self.schema_registry.get(node.template.uid) if self.schema_registry is not None else None
                value_role = getattr(schema, "functional_role", None)
                record = self._ensure_group(
                    (ref, *competitors),
                    kind=self.KIND_FUNCTIONAL,
                    meta={
                        "functional_template": node.template.uid,
                        "functional_role": value_role.value if value_role is not None else None,
                    },
                )
                out[record.group_ref.uid] = record

            exclusions = self._schema_exclusion_conflicts_for(ref)
            if exclusions:
                node = self.core.store.get_hypernode(ref.uid)
                by_template: dict[str, list[Ref]] = {}
                for other_ref in exclusions:
                    other = self.core.store.get_hypernode(other_ref.uid)
                    by_template.setdefault(other.template.uid, []).append(other_ref)
                for partner_template, partner_refs in sorted(by_template.items()):
                    pair = tuple(sorted((node.template.uid, partner_template)))
                    record = self._ensure_group(
                        (ref, *partner_refs),
                        kind=self.KIND_MUTUAL_EXCLUSION,
                        meta={
                            "exclusion_templates": pair,
                        },
                    )
                    out[record.group_ref.uid] = record
        return tuple(out[uid] for uid in sorted(out))

    def is_unresolved_group(self, group: Group | Ref) -> bool:
        if isinstance(group, Ref):
            if group.kind is not RefKind.K or not self.core.store.has_uid(group.uid):
                return False
            obj = self.core.store.get_element_any_domain(group.uid)
            if not isinstance(obj, Group):
                return False
            group_obj = obj
        else:
            group_obj = group
        if str(group_obj.meta.get("TYPE") or group_obj.meta.get("type") or "").upper() != self.TYPE:
            return False
        if len(group_obj.members) < 2:
            return False

        members = tuple(group_obj.members)
        kind = str(group_obj.meta.get("conflict_kind") or self.KIND_POLARITY).upper()
        if kind in {self.KIND_FUNCTIONAL, self.KIND_MUTUAL_EXCLUSION}:
            live = tuple(member for member in members if self._is_asserted_expression(member))
            return len(live) >= 2

        for negative in members:
            operand = self._not_operand(negative)
            if operand is None or operand not in members:
                continue
            if self._is_asserted_expression(negative) and self._is_asserted_expression(operand):
                return True
        return False

    def unresolved_for(self, ref: Ref) -> tuple[ConflictRecord, ...]:
        out: list[ConflictRecord] = []
        for group in self._conflict_groups_containing(ref):
            if not self.is_unresolved_group(group):
                continue
            out.append(
                ConflictRecord(
                    self.core.ref(group.uid),
                    group.members,
                    str(group.meta.get("conflict_kind") or self.KIND_POLARITY),
                    False,
                )
            )
        return tuple(out)

    def is_conflicted(self, ref: Ref) -> bool:
        return bool(self.unresolved_for(ref))
