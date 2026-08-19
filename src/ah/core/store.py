from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
import json

from ah.model import (
    AbstractSymbol,
    CanonicalElement,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    Ref,
    RefKind,
    RuntimeState,
    SemanticEntity,
    Template,
)


@dataclass
class _StoreState:
    # Canonical records.
    symbols: dict[str, AbstractSymbol] = field(default_factory=dict)
    domains: dict[Domain, dict[str, CanonicalElement]] = field(
        default_factory=lambda: {d: {} for d in Domain}
    )
    links: dict[str, Link] = field(default_factory=dict)

    # Runtime state exists only for excitable S/C/P/H elements. L has no x.
    runtime: dict[str, RuntimeState] = field(default_factory=dict)

    # Diagnostic insertion chronology. This is not semantic AH content and never
    # participates in identity/inference. It exists so operator tooling can show
    # the complete graph in true add order across S/C/P/H/L without smuggling
    # timestamps into canonical S/T/L records that do not own Mt.
    creation_sequence: dict[str, int] = field(default_factory=dict)
    next_creation_sequence: int = 1

    # Derived indexes. None of these are a second source of truth.
    uid_kind: dict[str, RefKind] = field(default_factory=dict)
    uid_domain: dict[str, Domain] = field(default_factory=dict)
    # One observed wordform may belong to several lexical S nodes.  This is
    # required for genuine homography (e.g. one surface form shared by distinct
    # paradigms).  The index is therefore retrieval-only and never an identity
    # constraint.
    forms_index: dict[str, set[str]] = field(default_factory=dict)
    template_by_predicate: dict[str, list[str]] = field(default_factory=dict)
    hypernodes_by_template: dict[str, list[str]] = field(default_factory=dict)
    entity_name_index: dict[str, list[str]] = field(default_factory=dict)
    property_name_index: dict[str, list[str]] = field(default_factory=dict)
    property_value_index: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    outgoing_links: dict[str, list[str]] = field(default_factory=dict)
    incoming_links: dict[str, list[str]] = field(default_factory=dict)
    relation_outgoing: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    relation_incoming: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    n_signature: dict[Domain, dict[tuple, str]] = field(
        default_factory=lambda: {d: {} for d in Domain}
    )
    n_actants: dict[str, tuple[str, ...]] = field(default_factory=dict)
    actant_hypernodes: dict[str, list[str]] = field(default_factory=dict)
    group_memberships: dict[str, list[str]] = field(default_factory=dict)
    function_parents: dict[str, list[str]] = field(default_factory=dict)


class AHStore:
    """In-memory canonical AH store plus rebuildable runtime indexes.

    Canonical records are S, C/P/H elements and L. Indexes are strictly derived
    from those records and may be discarded/rebuilt at any time. Public callers
    never write an index directly.
    """

    def __init__(self) -> None:
        self._state = _StoreState()
        self._lock = RLock()

    def clone(self) -> "AHStore":
        other = AHStore()
        with self._lock:
            other._state = deepcopy(self._state)
        return other

    def replace_from(self, other: "AHStore") -> None:
        with self._lock, other._lock:
            self._state = deepcopy(other._state)

    # ---------- canonical reads ----------
    def has_uid(self, uid: str) -> bool:
        return uid in self._state.uid_kind

    def kind_of(self, uid: str) -> RefKind:
        return self._state.uid_kind[uid]

    def domain_of(self, uid: str) -> Domain | None:
        return self._state.uid_domain.get(uid)

    def get_symbol(self, uid: str) -> AbstractSymbol:
        return self._state.symbols[uid]

    def get_element(self, domain: Domain, uid: str) -> CanonicalElement:
        return self._state.domains[domain][uid]

    def get_element_any_domain(self, uid: str) -> CanonicalElement:
        domain = self._state.uid_domain[uid]
        return self._state.domains[domain][uid]

    def get_template(self, uid: str) -> Template:
        element = self.get_element_any_domain(uid)
        if not isinstance(element, Template):
            raise TypeError(f"{uid} is not a Template")
        return element

    def get_hypernode(self, uid: str) -> Hypernode:
        element = self.get_element_any_domain(uid)
        if not isinstance(element, Hypernode):
            raise TypeError(f"{uid} is not a Hypernode")
        return element

    def get_link(self, uid: str) -> Link:
        return self._state.links[uid]

    def elements(self, domain: Domain) -> tuple[CanonicalElement, ...]:
        return tuple(self._state.domains[domain].values())

    def links(self) -> tuple[Link, ...]:
        return tuple(self._state.links.values())

    def runtime_state(self, uid: str) -> RuntimeState:
        return self._state.runtime[uid]

    def all_uids(self) -> tuple[str, ...]:
        return tuple(self._state.uid_kind.keys())

    def creation_sequence(self, uid: str) -> int:
        """Return stable diagnostic insertion order for one canonical UID."""
        try:
            return int(self._state.creation_sequence[uid])
        except KeyError as exc:
            raise KeyError(f"No creation sequence for {uid}") from exc

    def creation_items(self) -> tuple[tuple[str, int], ...]:
        return tuple(self._state.creation_sequence.items())

    def runtime_items(self) -> tuple[tuple[str, RuntimeState], ...]:
        return tuple(self._state.runtime.items())

    def all_elements(self) -> tuple[CanonicalElement, ...]:
        out: list[CanonicalElement] = []
        for domain in Domain:
            out.extend(self._state.domains[domain].values())
        return tuple(out)

    # ---------- indexed reads ----------
    def find_symbols_by_form(self, form: str) -> tuple[AbstractSymbol, ...]:
        """Return every canonical S whose ``R_text`` contains ``form``.

        A wordform is not an identity key: homographs may legitimately appear in
        several paradigms.  Callers that need one lexical identity must resolve
        that ambiguity using additional perception context instead of relying on
        insertion order.
        """
        uids = self._state.forms_index.get(form.casefold(), set())
        return tuple(self._state.symbols[uid] for uid in sorted(uids))

    def find_symbol_by_form(self, form: str) -> AbstractSymbol | None:
        """Return the unique S for ``form`` or fail closed on homography.

        This compatibility helper is intentionally strict so legacy callers cannot
        silently collapse ``wordform -> set[S]`` back into ``wordform -> S``.
        New ambiguity-aware code should use :meth:`find_symbols_by_form`.
        """
        matches = self.find_symbols_by_form(form)
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous wordform {form!r} belongs to multiple S nodes: "
                + ", ".join(symbol.uid for symbol in matches)
            )
        return matches[0] if matches else None

    def find_templates_by_predicate(self, predicate_uid: str) -> tuple[Template, ...]:
        uids = self._state.template_by_predicate.get(predicate_uid, [])
        return tuple(self.get_template(uid) for uid in uids)

    def find_hypernodes_by_template(self, template_uid: str) -> tuple[Hypernode, ...]:
        """Return canonical N realizations of one T across C/P/H.

        This is a derived retrieval index used by ignition lexical spreading; it
        never changes canonical ownership or semantic identity.
        """
        uids = self._state.hypernodes_by_template.get(template_uid, [])
        return tuple(self.get_hypernode(uid) for uid in uids)

    def find_entities_by_name(
        self,
        name: str,
        domain: Domain | None = None,
    ) -> tuple[SemanticEntity, ...]:
        """Return name/alias candidates, optionally restricted to one semantic domain.

        The name index is deliberately a retrieval index, not an identity key. Multiple
        entities may legitimately share a name (including inside one domain); callers
        must resolve or expose that ambiguity explicitly.
        """
        uids = self._state.entity_name_index.get(name.strip().casefold(), [])
        result: list[SemanticEntity] = []
        for uid in uids:
            if domain is not None and self._state.uid_domain.get(uid) is not domain:
                continue
            element = self.get_element_any_domain(uid)
            if isinstance(element, SemanticEntity):
                result.append(element)
        return tuple(result)

    def find_elements_with_property(self, name: str, value: object | None = None) -> tuple[Ref, ...]:
        if value is None:
            uids = self._state.property_name_index.get(name, [])
        else:
            uids = self._state.property_value_index.get((name, self._property_value_key(value)), [])
        return tuple(Ref(uid, self._state.uid_kind[uid]) for uid in uids)

    def outgoing_links(self, uid: str, relation_id: str | None = None) -> tuple[Link, ...]:
        if relation_id is None:
            ids = self._state.outgoing_links.get(uid, [])
        else:
            ids = self._state.relation_outgoing.get(relation_id.upper(), {}).get(uid, [])
        return tuple(self._state.links[lid] for lid in ids)

    def incoming_links(self, uid: str, relation_id: str | None = None) -> tuple[Link, ...]:
        if relation_id is None:
            ids = self._state.incoming_links.get(uid, [])
        else:
            ids = self._state.relation_incoming.get(relation_id.upper(), {}).get(uid, [])
        return tuple(self._state.links[lid] for lid in ids)

    def find_link(self, relation_id: str, source_uid: str, target_uid: str) -> Link | None:
        relation = relation_id.upper()
        for link in self.outgoing_links(source_uid, relation):
            if link.target.uid == target_uid:
                return link
        return None

    def find_hypernode_by_signature(self, domain: Domain, signature: tuple) -> Hypernode | None:
        uid = self._state.n_signature[domain].get(signature)
        return self.get_hypernode(uid) if uid else None

    def function_parents(self, operand_uid: str) -> tuple[FunctionSymbol, ...]:
        """Return canonical g nodes that directly use ``operand_uid``.

        This is a derived reverse operand index used by semantic recall/correction
        diagnostics; it never changes canonical function direction.
        """
        uids = self._state.function_parents.get(operand_uid, [])
        out: list[FunctionSymbol] = []
        for uid in uids:
            element = self.get_element_any_domain(uid)
            if isinstance(element, FunctionSymbol):
                out.append(element)
        return tuple(out)

    def hypernode_actants(self, uid: str) -> tuple[Ref, ...]:
        node = self.get_hypernode(uid)
        return tuple(node.actants.values())

    def hypernodes_for_actant(self, uid: str) -> tuple[Hypernode, ...]:
        return tuple(self.get_hypernode(n_uid) for n_uid in self._state.actant_hypernodes.get(uid, []))

    def groups_containing(self, uid: str) -> tuple[Group, ...]:
        out: list[Group] = []
        for k_uid in self._state.group_memberships.get(uid, []):
            element = self.get_element_any_domain(k_uid)
            if isinstance(element, Group):
                out.append(element)
        return tuple(out)

    # ---------- runtime mutation used by Ignition ----------
    def _replace_runtime_states(self, states: dict[str, RuntimeState]) -> None:
        missing = set(self._state.runtime) - set(states)
        extra = set(states) - set(self._state.runtime)
        if missing or extra:
            raise ValueError(f"Runtime replacement UID mismatch: missing={missing}, extra={extra}")
        self._state.runtime = states

    def _update_runtime_states(self, states: dict[str, RuntimeState]) -> None:
        """Replace only the runtime states touched by one sparse Ignition tick.

        Canonical/runtime membership is unchanged; this is equivalent to a full
        synchronous replacement for UIDs whose state changed, while cold untouched
        UIDs keep their existing RuntimeState object.
        """
        unknown = set(states) - set(self._state.runtime)
        if unknown:
            raise ValueError(f"Runtime update contains unknown UIDs: {unknown}")
        self._state.runtime.update(states)

    def _replace_link(self, link: Link) -> None:
        if link.uid not in self._state.links:
            raise KeyError(link.uid)
        self._state.links[link.uid] = link
        # Endpoint/relation are treated as immutable identity in current MVP. If that
        # changes, this operation must rebuild adjacency indexes.

    def _replace_hypernode(self, domain: Domain, node: Hypernode) -> None:
        current = self._state.domains[domain].get(node.uid)
        if not isinstance(current, Hypernode):
            raise KeyError(node.uid)
        self._state.domains[domain][node.uid] = node

    def _replace_symbol(self, symbol: AbstractSymbol) -> None:
        if symbol.uid not in self._state.symbols:
            raise KeyError(symbol.uid)
        self._state.symbols[symbol.uid] = symbol
        self.rebuild_indexes()

    def _replace_element(self, domain: Domain, element: CanonicalElement, kind: RefKind) -> None:
        current = self._state.domains[domain].get(element.uid)
        if current is None:
            raise KeyError(element.uid)
        if self._state.uid_kind.get(element.uid) is not kind:
            raise TypeError(f"Element kind cannot change for {element.uid}")
        self._state.domains[domain][element.uid] = element
        self.rebuild_indexes()

    def _remove_uid(self, uid: str) -> None:
        """Canonical deletion primitive used by GC/high-level services.

        Referential safety is the caller's responsibility. All derived indexes are
        rebuilt afterwards so this operation cannot leave stale query state.
        """
        kind = self._state.uid_kind.get(uid)
        if kind is None:
            raise KeyError(uid)
        if kind is RefKind.S:
            self._state.symbols.pop(uid, None)
        elif kind is RefKind.L:
            self._state.links.pop(uid, None)
        else:
            domain = self._state.uid_domain.get(uid)
            if domain is None:
                raise KeyError(uid)
            self._state.domains[domain].pop(uid, None)
        self._state.runtime.pop(uid, None)
        self._state.creation_sequence.pop(uid, None)
        self.rebuild_indexes()

    # ---------- canonical insertions ----------
    def _assert_uid_free(self, uid: str) -> None:
        if uid in self._state.uid_kind:
            raise ValueError(f"UID already exists: {uid}")

    def _register_runtime(self, uid: str) -> None:
        self._state.runtime[uid] = RuntimeState()

    def _register_creation(self, uid: str) -> None:
        if uid in self._state.creation_sequence:
            return
        sequence = max(1, int(self._state.next_creation_sequence))
        self._state.creation_sequence[uid] = sequence
        self._state.next_creation_sequence = sequence + 1

    def _restore_creation_sequence(
        self, mapping: dict[str, int], *, next_sequence: int | None = None
    ) -> None:
        """Restore optional persisted diagnostic chronology.

        Invalid/missing UIDs are ignored. Missing canonical UIDs receive new tail
        positions deterministically, so older persistence files remain readable.
        """
        cleaned: dict[str, int] = {}
        used: set[int] = set()
        for uid, raw in sorted(mapping.items(), key=lambda item: (int(item[1]), item[0])):
            if not self.has_uid(uid):
                continue
            value = int(raw)
            if value <= 0 or value in used:
                continue
            cleaned[uid] = value
            used.add(value)
        self._state.creation_sequence = cleaned
        baseline = max(used, default=0) + 1
        self._state.next_creation_sequence = max(
            baseline, int(next_sequence) if next_sequence is not None else baseline
        )
        for uid in self.all_uids():
            self._register_creation(uid)

    def _rebuild_legacy_creation_sequence(self) -> None:
        """Best-effort chronology for pre-v0.31 persistence without metadata.

        Existing old files cannot reveal exact insertion order for S/T/M because
        canonical JSON was UID-sorted. We therefore use canonical N.created_tick
        when available, otherwise first_excitation_tick, and keep deterministic
        tail ordering for never-excited nodes. From the first v0.31 save onward the
        exact insertion sequence is persisted.
        """
        ranked: list[tuple[int, int, str]] = []
        for uid in self.all_uids():
            kind = self.kind_of(uid)
            tick: int | None = None
            if kind is RefKind.N:
                node = self.get_hypernode(uid)
                raw = node.meta.get("created_tick")
                if raw is not None:
                    try:
                        tick = int(raw)
                    except (TypeError, ValueError):
                        tick = None
            if tick is None and kind is not RefKind.L:
                first = self.runtime_state(uid).first_excitation_tick
                tick = None if first is None else int(first)
            ranked.append((1 if tick is None else 0, tick if tick is not None else 10**18, uid))
        ranked.sort()
        self._state.creation_sequence = {uid: index for index, (*_, uid) in enumerate(ranked, 1)}
        self._state.next_creation_sequence = len(ranked) + 1

    def _insert_symbol(self, symbol: AbstractSymbol) -> None:
        self._assert_uid_free(symbol.uid)
        self._state.symbols[symbol.uid] = symbol
        self._state.uid_kind[symbol.uid] = RefKind.S
        self._register_runtime(symbol.uid)
        self._register_creation(symbol.uid)
        self._index_symbol(symbol)

    def _insert_element(self, domain: Domain, element: CanonicalElement, kind: RefKind) -> None:
        self._assert_uid_free(element.uid)
        self._state.domains[domain][element.uid] = element
        self._state.uid_kind[element.uid] = kind
        self._state.uid_domain[element.uid] = domain
        self._register_runtime(element.uid)
        self._register_creation(element.uid)
        self._index_element(domain, element)

    def _insert_link(self, link: Link) -> None:
        self._assert_uid_free(link.uid)
        self._state.links[link.uid] = link
        self._state.uid_kind[link.uid] = RefKind.L
        self._register_creation(link.uid)
        # L belongs to AH.L and has no excitation state of its own.
        self._index_link(link)

    # ---------- index maintenance ----------
    @staticmethod
    def _property_value_key(value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return repr(value)

    def _index_symbol(self, symbol: AbstractSymbol) -> None:
        for form in symbol.forms:
            key = form.casefold()
            self._state.forms_index.setdefault(key, set()).add(symbol.uid)

    def _index_properties(self, uid: str, properties) -> None:
        for name, prop in properties.items():
            by_name = self._state.property_name_index.setdefault(name, [])
            if uid not in by_name:
                by_name.append(uid)
            key = (name, self._property_value_key(prop.value))
            by_value = self._state.property_value_index.setdefault(key, [])
            if uid not in by_value:
                by_value.append(uid)

    def _index_entity_names(self, entity: SemanticEntity) -> None:
        values: list[str] = []
        name_prop = entity.properties.get("name")
        if name_prop is not None and isinstance(name_prop.value, str):
            values.append(name_prop.value)
        aliases_prop = entity.properties.get("aliases")
        if aliases_prop is not None:
            raw = aliases_prop.value
            if isinstance(raw, str):
                values.append(raw)
            elif isinstance(raw, (list, tuple, set, frozenset)):
                values.extend(str(v) for v in raw)
        for value in values:
            key = value.strip().casefold()
            if not key:
                continue
            bucket = self._state.entity_name_index.setdefault(key, [])
            if entity.uid not in bucket:
                bucket.append(entity.uid)

    def _index_element(self, domain: Domain, element: CanonicalElement) -> None:
        if isinstance(element, Template):
            self._state.template_by_predicate.setdefault(element.predicate.uid, []).append(element.uid)
        if isinstance(element, SemanticEntity):
            self._index_entity_names(element)
            self._index_properties(element.uid, element.properties)
        elif isinstance(element, FunctionSymbol):
            for operand in element.operands:
                self._state.function_parents.setdefault(operand.uid, []).append(element.uid)
        elif isinstance(element, Group):
            self._index_properties(element.uid, element.properties)
            for member in element.members:
                self._state.group_memberships.setdefault(member.uid, []).append(element.uid)
        elif isinstance(element, Hypernode):
            self._state.hypernodes_by_template.setdefault(element.template.uid, []).append(element.uid)
            self._index_properties(element.uid, element.properties)
            self._state.n_actants[element.uid] = tuple(ref.uid for ref in element.actants.values())
            for ref in element.actants.values():
                self._state.actant_hypernodes.setdefault(ref.uid, []).append(element.uid)
            if not bool(element.meta.get("dedup_exempt", False)):
                from .signatures import hypernode_signature
                template = self.get_template(element.template.uid)
                signature = hypernode_signature(element, template)
                existing = self._state.n_signature[domain].get(signature)
                if existing is None:
                    self._state.n_signature[domain][signature] = element.uid

    def _index_link(self, link: Link) -> None:
        self._state.outgoing_links.setdefault(link.source.uid, []).append(link.uid)
        self._state.incoming_links.setdefault(link.target.uid, []).append(link.uid)
        relation = link.relation_id.upper()
        self._state.relation_outgoing.setdefault(relation, {}).setdefault(link.source.uid, []).append(link.uid)
        self._state.relation_incoming.setdefault(relation, {}).setdefault(link.target.uid, []).append(link.uid)

    def _register_n_signature(self, domain: Domain, signature: tuple, uid: str) -> None:
        existing = self._state.n_signature[domain].get(signature)
        if existing is not None and existing != uid:
            raise ValueError(f"Duplicate N signature in domain {domain.value}: {signature}")
        self._state.n_signature[domain][signature] = uid

    def rebuild_indexes(self) -> None:
        """Rebuild every derived index from canonical records.

        Runtime excitation is preserved for still-existing excitable UIDs; missing
        runtime entries are initialized to zero. L never receives RuntimeState.
        """
        old_runtime = self._state.runtime
        self._state.uid_kind = {}
        self._state.uid_domain = {}
        self._state.forms_index = {}
        self._state.template_by_predicate = {}
        self._state.hypernodes_by_template = {}
        self._state.entity_name_index = {}
        self._state.property_name_index = {}
        self._state.property_value_index = {}
        self._state.outgoing_links = {}
        self._state.incoming_links = {}
        self._state.relation_outgoing = {}
        self._state.relation_incoming = {}
        self._state.n_signature = {d: {} for d in Domain}
        self._state.n_actants = {}
        self._state.actant_hypernodes = {}
        self._state.group_memberships = {}
        self._state.function_parents = {}

        new_runtime: dict[str, RuntimeState] = {}
        for symbol in self._state.symbols.values():
            if symbol.uid in self._state.uid_kind:
                raise ValueError(f"Duplicate UID during index rebuild: {symbol.uid}")
            self._state.uid_kind[symbol.uid] = RefKind.S
            new_runtime[symbol.uid] = old_runtime.get(symbol.uid, RuntimeState())
            self._index_symbol(symbol)

        type_to_kind = {
            SemanticEntity: RefKind.M,
            FunctionSymbol: RefKind.G,
            Group: RefKind.K,
            Template: RefKind.T,
            Hypernode: RefKind.N,
        }
        # First register all elements/UIDs, then derive indexes that may dereference T.
        for domain in Domain:
            for element in self._state.domains[domain].values():
                if element.uid in self._state.uid_kind:
                    raise ValueError(f"Duplicate UID during index rebuild: {element.uid}")
                kind = type_to_kind[type(element)]
                self._state.uid_kind[element.uid] = kind
                self._state.uid_domain[element.uid] = domain
                new_runtime[element.uid] = old_runtime.get(element.uid, RuntimeState())

        for domain in Domain:
            for element in self._state.domains[domain].values():
                self._index_element(domain, element)

        for link in self._state.links.values():
            if link.uid in self._state.uid_kind:
                raise ValueError(f"Duplicate UID during index rebuild: {link.uid}")
            self._state.uid_kind[link.uid] = RefKind.L
            self._index_link(link)

        self._state.runtime = new_runtime
        # Creation chronology is diagnostic metadata rather than a derived index,
        # therefore index rebuilds preserve it and only append missing UIDs.
        existing = set(self._state.uid_kind)
        self._state.creation_sequence = {
            uid: seq for uid, seq in self._state.creation_sequence.items() if uid in existing
        }
        if self._state.creation_sequence:
            self._state.next_creation_sequence = max(
                int(self._state.next_creation_sequence),
                max(self._state.creation_sequence.values()) + 1,
            )
        else:
            self._state.next_creation_sequence = max(1, int(self._state.next_creation_sequence))
        for uid in self._state.uid_kind:
            self._register_creation(uid)

    # ---------- reference inspection / GC support ----------
    def structural_referrers(self, uid: str) -> tuple[Ref, ...]:
        """Return non-L canonical structures that contain a direct ref to ``uid``.

        Every canonical direct-reference shape already owns a rebuildable reverse
        index. GC therefore must not scan all C/P/H records merely to decide whether
        one expired N is still referenced. Canonical truth remains in the records;
        these indexes are only the deterministic retrieval path and are rebuilt by
        :meth:`rebuild_indexes`.
        """
        referrer_uids: set[str] = set()
        referrer_uids.update(self._state.template_by_predicate.get(uid, ()))
        referrer_uids.update(self._state.hypernodes_by_template.get(uid, ()))
        referrer_uids.update(self._state.actant_hypernodes.get(uid, ()))
        referrer_uids.update(self._state.function_parents.get(uid, ()))
        referrer_uids.update(self._state.group_memberships.get(uid, ()))
        return tuple(
            Ref(ref_uid, self._state.uid_kind[ref_uid])
            for ref_uid in sorted(referrer_uids)
            if ref_uid in self._state.uid_kind and self._state.uid_kind[ref_uid] is not RefKind.L
        )

    def has_any_link(self, uid: str) -> bool:
        return bool(self._state.outgoing_links.get(uid) or self._state.incoming_links.get(uid))

    def _delete_uids(self, uids: set[str]) -> set[str]:
        """Delete canonical UIDs and links incident to deleted endpoints, then rebuild indexes."""
        if not uids:
            return set()
        removed = set(uids)
        # Links incident to a deleted endpoint cannot survive referentially.
        for link in tuple(self._state.links.values()):
            if link.uid in uids or link.source.uid in uids or link.target.uid in uids:
                removed.add(link.uid)
                self._state.links.pop(link.uid, None)

        for uid in tuple(uids):
            self._state.symbols.pop(uid, None)
            domain = self._state.uid_domain.get(uid)
            if domain is not None:
                self._state.domains[domain].pop(uid, None)
            self._state.runtime.pop(uid, None)
            self._state.creation_sequence.pop(uid, None)

        self.rebuild_indexes()
        return removed


class AHTransaction:
    """Copy-on-write transaction prioritizing atomic semantics over throughput."""

    def __init__(self, parent: AHStore) -> None:
        self.parent = parent
        self.store = parent.clone()
        self._committed = False

    def commit(self) -> None:
        if self._committed:
            raise RuntimeError("Transaction already committed")
        self.parent.replace_from(self.store)
        self._committed = True
