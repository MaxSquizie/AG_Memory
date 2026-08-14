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

    # Derived indexes. None of these are a second source of truth.
    uid_kind: dict[str, RefKind] = field(default_factory=dict)
    uid_domain: dict[str, Domain] = field(default_factory=dict)
    forms_index: dict[str, str] = field(default_factory=dict)
    template_by_predicate: dict[str, list[str]] = field(default_factory=dict)
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

    def runtime_items(self) -> tuple[tuple[str, RuntimeState], ...]:
        return tuple(self._state.runtime.items())

    def all_elements(self) -> tuple[CanonicalElement, ...]:
        out: list[CanonicalElement] = []
        for domain in Domain:
            out.extend(self._state.domains[domain].values())
        return tuple(out)

    # ---------- indexed reads ----------
    def find_symbol_by_form(self, form: str) -> AbstractSymbol | None:
        uid = self._state.forms_index.get(form.casefold())
        return self._state.symbols.get(uid) if uid else None

    def find_templates_by_predicate(self, predicate_uid: str) -> tuple[Template, ...]:
        uids = self._state.template_by_predicate.get(predicate_uid, [])
        return tuple(self.get_template(uid) for uid in uids)

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
        self._assert_symbol_forms_available(symbol, replacing_uid=symbol.uid)
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
        self.rebuild_indexes()

    # ---------- canonical insertions ----------
    def _assert_uid_free(self, uid: str) -> None:
        if uid in self._state.uid_kind:
            raise ValueError(f"UID already exists: {uid}")

    def _register_runtime(self, uid: str) -> None:
        self._state.runtime[uid] = RuntimeState()

    def _insert_symbol(self, symbol: AbstractSymbol) -> None:
        self._assert_uid_free(symbol.uid)
        # Validate every wordform before touching canonical storage. Historically this
        # check lived only in _index_symbol(), which could raise after the record had
        # already been inserted and therefore leave an invalid S behind.
        self._assert_symbol_forms_available(symbol)
        self._state.symbols[symbol.uid] = symbol
        self._state.uid_kind[symbol.uid] = RefKind.S
        self._register_runtime(symbol.uid)
        self._index_symbol(symbol)

    def _insert_element(self, domain: Domain, element: CanonicalElement, kind: RefKind) -> None:
        self._assert_uid_free(element.uid)
        self._state.domains[domain][element.uid] = element
        self._state.uid_kind[element.uid] = kind
        self._state.uid_domain[element.uid] = domain
        self._register_runtime(element.uid)
        self._index_element(domain, element)

    def _insert_link(self, link: Link) -> None:
        self._assert_uid_free(link.uid)
        self._state.links[link.uid] = link
        self._state.uid_kind[link.uid] = RefKind.L
        # L belongs to AH.L and has no excitation state of its own.
        self._index_link(link)

    # ---------- index maintenance ----------
    @staticmethod
    def _property_value_key(value: object) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except Exception:
            return repr(value)

    def _assert_symbol_forms_available(
        self,
        symbol: AbstractSymbol,
        *,
        replacing_uid: str | None = None,
    ) -> None:
        for form in symbol.forms:
            existing = self._state.forms_index.get(form.casefold())
            if existing is not None and existing != (replacing_uid or symbol.uid):
                raise ValueError(f"Wordform already belongs to another S: {form!r}")

    def _index_symbol(self, symbol: AbstractSymbol) -> None:
        for form in symbol.forms:
            key = form.casefold()
            existing = self._state.forms_index.get(key)
            if existing is not None and existing != symbol.uid:
                raise ValueError(f"Wordform already belongs to another S: {form!r}")
            self._state.forms_index[key] = symbol.uid

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
        elif isinstance(element, Group):
            self._index_properties(element.uid, element.properties)
            for member in element.members:
                self._state.group_memberships.setdefault(member.uid, []).append(element.uid)
        elif isinstance(element, Hypernode):
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

        new_runtime: dict[str, RuntimeState] = {}
        for symbol in self._state.symbols.values():
            if symbol.uid in self._state.uid_kind:
                raise ValueError(f"Duplicate UID during index rebuild: {symbol.uid}")
            self._state.uid_kind[symbol.uid] = RefKind.S
            new_runtime[symbol.uid] = deepcopy(old_runtime.get(symbol.uid, RuntimeState()))
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
                new_runtime[element.uid] = deepcopy(old_runtime.get(element.uid, RuntimeState()))

        for domain in Domain:
            for element in self._state.domains[domain].values():
                self._index_element(domain, element)

        for link in self._state.links.values():
            if link.uid in self._state.uid_kind:
                raise ValueError(f"Duplicate UID during index rebuild: {link.uid}")
            self._state.uid_kind[link.uid] = RefKind.L
            self._index_link(link)

        self._state.runtime = new_runtime

    # ---------- reference inspection / GC support ----------
    def structural_referrers(self, uid: str) -> tuple[Ref, ...]:
        """Return non-L canonical structures that contain a direct ref to uid."""
        out: list[Ref] = []
        for domain in Domain:
            for element in self._state.domains[domain].values():
                hit = False
                if isinstance(element, Template):
                    hit = element.predicate.uid == uid
                elif isinstance(element, Hypernode):
                    hit = element.template.uid == uid or any(ref.uid == uid for ref in element.actants.values())
                elif isinstance(element, FunctionSymbol):
                    hit = any(ref.uid == uid for ref in element.operands)
                elif isinstance(element, Group):
                    hit = any(ref.uid == uid for ref in element.members)
                if hit:
                    out.append(Ref(element.uid, self._state.uid_kind[element.uid]))
        return tuple(out)

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
