from __future__ import annotations

from dataclasses import replace

from ah.model import (
    AbstractSymbol,
    ActantRole,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    Property,
    Ref,
    RefKind,
    SemanticEntity,
    Template,
)

from .signatures import hypernode_signature
from .store import AHStore, AHTransaction
from .uid import UidGenerator, UuidUidGenerator
from .validation import ValidationError, validate_hypernode, validate_ref_exists


_KIND_BY_TYPE = {
    SemanticEntity: RefKind.M,
    FunctionSymbol: RefKind.G,
    Group: RefKind.K,
    Template: RefKind.T,
    Hypernode: RefKind.N,
}


class AHCore:
    """Only public write boundary for canonical AH structures in the first code slice."""

    def __init__(self, store: AHStore | None = None, uid_generator: UidGenerator | None = None) -> None:
        self.store = store or AHStore()
        self.uid = uid_generator or UuidUidGenerator()

    def transaction(self) -> "AHCoreTransaction":
        return AHCoreTransaction(self)

    # ----- S -----
    def add_abstract_symbol(self, forms: set[str] | frozenset[str], uid: str | None = None) -> AbstractSymbol:
        symbol = AbstractSymbol(uid or self.uid.new(RefKind.S), frozenset(forms))
        self.store._insert_symbol(symbol)
        return symbol

    def ensure_abstract_symbol(self, form: str) -> AbstractSymbol:
        found = self.store.find_symbol_by_form(form)
        return found if found is not None else self.add_abstract_symbol({form})

    def add_symbol_form(self, symbol_uid: str, form: str) -> AbstractSymbol:
        value = form.strip()
        if not value:
            raise ValueError("Symbol form must be non-empty")
        symbol = self.store.get_symbol(symbol_uid)
        existing = self.store.find_symbol_by_form(value)
        if existing is not None and existing.uid != symbol_uid:
            raise ValueError(f"Wordform already belongs to another S: {value!r}")
        if value in symbol.forms:
            return symbol
        updated = replace(symbol, forms=frozenset((*symbol.forms, value)))
        self.store._replace_symbol(updated)
        return updated

    # ----- C/P/H elements -----
    def add_entity(
        self,
        domain: Domain,
        properties: dict[str, Property] | None = None,
        meta: dict[str, object] | None = None,
        uid: str | None = None,
    ) -> SemanticEntity:
        entity = SemanticEntity(uid or self.uid.new(RefKind.M), properties or {}, meta or {})
        self.store._insert_element(domain, entity, RefKind.M)
        return entity

    def add_function(
        self,
        domain: Domain,
        function_id: str,
        operands: tuple[Ref, ...],
        uid: str | None = None,
    ) -> FunctionSymbol:
        for ref in operands:
            validate_ref_exists(self.store, ref)
        g = FunctionSymbol(uid or self.uid.new(RefKind.G), function_id, operands)
        self.store._insert_element(domain, g, RefKind.G)
        return g

    def add_group(
        self,
        domain: Domain,
        members: tuple[Ref, ...],
        properties: dict[str, Property] | None = None,
        meta: dict[str, object] | None = None,
        uid: str | None = None,
    ) -> Group:
        for ref in members:
            validate_ref_exists(self.store, ref)
        k = Group(uid or self.uid.new(RefKind.K), members, properties or {}, meta or {})
        self.store._insert_element(domain, k, RefKind.K)
        return k

    def add_template(
        self,
        domain: Domain,
        predicate: Ref,
        roles: tuple[ActantRole, ...],
        uid: str | None = None,
    ) -> Template:
        validate_ref_exists(self.store, predicate)
        t = Template(uid or self.uid.new(RefKind.T), predicate, roles)
        self.store._insert_element(domain, t, RefKind.T)
        return t

    def add_hypernode(
        self,
        domain: Domain,
        template: Ref,
        actants: dict[ActantRole, Ref],
        weight: float,
        properties: dict[str, Property] | None = None,
        meta: dict[str, object] | None = None,
        uid: str | None = None,
        deduplicate: bool = True,
        count_occurrence: bool = True,
    ) -> tuple[Hypernode, bool]:
        effective_meta = dict(meta or {})
        if not deduplicate:
            effective_meta["dedup_exempt"] = True
        candidate = Hypernode(
            uid or self.uid.new(RefKind.N),
            weight,
            template,
            actants,
            properties or {},
            effective_meta,
        )
        canonical_template = validate_hypernode(self.store, candidate)
        signature = hypernode_signature(candidate, canonical_template)

        if deduplicate:
            existing = self.store.find_hypernode_by_signature(domain, signature)
            if existing is not None:
                if not count_occurrence:
                    return existing, False
                occurrence = int(existing.meta.get("occurrence_count", 1)) + 1
                updated = replace(existing, meta={**dict(existing.meta), "occurrence_count": occurrence})
                self.store._state.domains[domain][existing.uid] = updated
                return updated, False

        initial_occurrence = 1 if count_occurrence else 0
        candidate = replace(candidate, meta={"occurrence_count": initial_occurrence, **dict(candidate.meta)})
        self.store._insert_element(domain, candidate, RefKind.N)
        if deduplicate:
            self.store._register_n_signature(domain, signature, candidate.uid)
        return candidate, True

    # ----- L -----
    def add_link(
        self,
        relation_id: str,
        source: Ref,
        target: Ref,
        weight: float,
        uid: str | None = None,
    ) -> Link:
        validate_ref_exists(self.store, source)
        validate_ref_exists(self.store, target)
        link = Link(uid or self.uid.new(RefKind.L), relation_id, weight, source, target)
        self.store._insert_link(link)
        return link

    def ensure_link(
        self,
        relation_id: str,
        source: Ref,
        target: Ref,
        weight: float,
    ) -> tuple[Link, bool]:
        validate_ref_exists(self.store, source)
        validate_ref_exists(self.store, target)
        existing = self.store.find_link(relation_id, source.uid, target.uid)
        if existing is not None:
            return existing, False
        return self.add_link(relation_id, source, target, weight), True

    def edit_link(self, link: Link) -> Link:
        if not self.store.has_uid(link.uid) or self.store.kind_of(link.uid) is not RefKind.L:
            raise KeyError(link.uid)
        validate_ref_exists(self.store, link.source)
        validate_ref_exists(self.store, link.target)
        current = self.store.get_link(link.uid)
        if (
            current.relation_id != link.relation_id
            or current.source != link.source
            or current.target != link.target
        ):
            raise ValueError("L relation/endpoints are immutable in MVP; create a new L instead")
        self.store._replace_link(link)
        return link

    def add_element(self, domain: Domain, element):
        """Normative addElement facade over typed canonical constructors."""
        if isinstance(element, SemanticEntity):
            return self.add_entity(domain, dict(element.properties), dict(element.meta), uid=element.uid)
        if isinstance(element, FunctionSymbol):
            return self.add_function(domain, element.function_id, element.operands, uid=element.uid)
        if isinstance(element, Group):
            return self.add_group(domain, element.members, dict(element.properties), dict(element.meta), uid=element.uid)
        if isinstance(element, Template):
            return self.add_template(domain, element.predicate, element.roles, uid=element.uid)
        if isinstance(element, Hypernode):
            return self.add_hypernode(
                domain, element.template, dict(element.actants), element.weight,
                dict(element.properties), dict(element.meta), uid=element.uid
            )[0]
        raise TypeError(f"Unsupported canonical element type: {type(element).__name__}")


    # ----- normative edit operations -----
    def edit_abstract_symbol(self, uid: str, forms: set[str] | frozenset[str]) -> AbstractSymbol:
        symbol = AbstractSymbol(uid, frozenset(forms))
        if self.store.kind_of(uid) is not RefKind.S:
            raise TypeError(f"{uid} is not an abstract symbol")
        self.store._replace_symbol(symbol)
        return symbol

    def edit_element(self, domain: Domain, element):
        if not self.store.has_uid(element.uid):
            raise KeyError(element.uid)
        if self.store.domain_of(element.uid) is not domain:
            raise ValueError(f"Element {element.uid} does not belong to {domain.value}")
        kind = _KIND_BY_TYPE.get(type(element))
        if kind is None:
            raise TypeError(f"Unsupported canonical element type: {type(element).__name__}")
        if isinstance(element, Template):
            validate_ref_exists(self.store, element.predicate)
            current = self.store.get_template(element.uid)
            if element.predicate != current.predicate:
                raise ValueError("T predicate reference is immutable; create a new T instead")
            if not set(current.roles).issubset(set(element.roles)):
                raise ValueError("T roles may only grow monotonically; role removal is forbidden")
        elif isinstance(element, Hypernode):
            validate_hypernode(self.store, element)
        elif isinstance(element, FunctionSymbol):
            for ref in element.operands:
                validate_ref_exists(self.store, ref)
        elif isinstance(element, Group):
            for ref in element.members:
                validate_ref_exists(self.store, ref)
        self.store._replace_element(domain, element, kind)
        return element

    def expand_template_roles(
        self,
        template_uid: str,
        roles: tuple[ActantRole, ...],
    ) -> Template:
        """Monotonically add roles to one canonical T without changing its UID.

        This is the canonical write primitive for controlled T valency evolution.
        It never removes roles and never changes the predicate reference. Existing N
        remain valid because a concrete hypernode may fill any subset of T roles.
        """
        current = self.store.get_template(template_uid)
        requested = set(current.roles) | set(roles)
        ordered = tuple(role for role in ActantRole if role in requested)
        if ordered == current.roles:
            return current
        domain = self.store.domain_of(template_uid)
        if domain is None:
            raise ValueError(f"Template {template_uid} has no semantic domain")
        return self.edit_element(domain, replace(current, roles=ordered))

    def add_property(self, uid: str, prop: Property):
        element = self.store.get_element_any_domain(uid)
        if not isinstance(element, (SemanticEntity, Group, Hypernode)):
            raise TypeError("Pr is supported only by m/k/N")
        if prop.name in element.properties:
            raise ValueError(f"Property already exists: {uid}.{prop.name}")
        domain = self.store.domain_of(uid)
        assert domain is not None
        updated = replace(element, properties={**dict(element.properties), prop.name: prop})
        return self.edit_element(domain, updated)

    def edit_property(self, uid: str, prop: Property):
        element = self.store.get_element_any_domain(uid)
        if not isinstance(element, (SemanticEntity, Group, Hypernode)):
            raise TypeError("Pr is supported only by m/k/N")
        if prop.name not in element.properties:
            raise KeyError(f"Property does not exist: {uid}.{prop.name}")
        domain = self.store.domain_of(uid)
        assert domain is not None
        updated = replace(element, properties={**dict(element.properties), prop.name: prop})
        return self.edit_element(domain, updated)

    def add_meta_property(self, uid: str, name: str, value: object):
        element = self.store.get_element_any_domain(uid)
        if not isinstance(element, (SemanticEntity, Group, Hypernode)):
            raise TypeError("Mt is supported only by m/k/N")
        if name in element.meta:
            raise ValueError(f"Meta-property already exists: {uid}.{name}")
        domain = self.store.domain_of(uid)
        assert domain is not None
        updated = replace(element, meta={**dict(element.meta), name: value})
        return self.edit_element(domain, updated)

    def edit_meta_property(self, uid: str, name: str, value: object):
        element = self.store.get_element_any_domain(uid)
        if not isinstance(element, (SemanticEntity, Group, Hypernode)):
            raise TypeError("Mt is supported only by m/k/N")
        if name not in element.meta:
            raise KeyError(f"Meta-property does not exist: {uid}.{name}")
        domain = self.store.domain_of(uid)
        assert domain is not None
        updated = replace(element, meta={**dict(element.meta), name: value})
        return self.edit_element(domain, updated)

    def ensure_function(
        self,
        domain: Domain,
        function_id: str,
        operands: tuple[Ref, ...],
    ) -> tuple[FunctionSymbol, bool]:
        normalized = function_id.upper()
        for element in self.store.elements(domain):
            if (
                isinstance(element, FunctionSymbol)
                and element.function_id.upper() == normalized
                and element.operands == operands
            ):
                return element, False
        return self.add_function(domain, normalized, operands), True

    # ----- normative query operations -----
    def get_abstract_symbol(self, uid: str) -> AbstractSymbol | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.S:
            return None
        return self.store.get_symbol(uid)

    def find_abstract_symbols(self, forms: set[str] | frozenset[str]) -> tuple[AbstractSymbol, ...]:
        found: dict[str, AbstractSymbol] = {}
        for form in forms:
            symbol = self.store.find_symbol_by_form(form)
            if symbol is not None:
                found[symbol.uid] = symbol
        return tuple(found[uid] for uid in sorted(found))

    def _references_in_element(self, element) -> tuple[Ref, ...]:
        if isinstance(element, Template):
            return (element.predicate,)
        if isinstance(element, Hypernode):
            return (element.template, *element.actants.values())
        if isinstance(element, FunctionSymbol):
            return element.operands
        if isinstance(element, Group):
            return element.members
        return ()

    def _reference_exists_in_domains(self, target: Ref, domains: tuple[Domain, ...] | None = None) -> bool:
        selected = domains or tuple(Domain)
        for domain in selected:
            for element in self.store.elements(domain):
                if target in self._references_in_element(element):
                    return True
        return False

    def get_s_reference(self, uid: str, domains: tuple[Domain, ...] | None = None) -> Ref | None:
        ref = Ref(uid, RefKind.S)
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.S:
            return None
        return ref if self._reference_exists_in_domains(ref, domains) else None

    def find_s_references(self, uid: str, domains: tuple[Domain, ...] | None = None) -> tuple[Ref, ...]:
        ref = self.get_s_reference(uid, domains)
        return (ref,) if ref is not None else ()

    def get_m_reference(self, uid: str, domains: tuple[Domain, ...] | None = None) -> Ref | None:
        ref = Ref(uid, RefKind.M)
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.M:
            return None
        return ref if self._reference_exists_in_domains(ref, domains) else None

    def find_m_references(self, uid: str, domains: tuple[Domain, ...] | None = None) -> tuple[Ref, ...]:
        ref = self.get_m_reference(uid, domains)
        return (ref,) if ref is not None else ()

    def get_symbol(self, uid: str, domains: tuple[Domain, ...] | None = None) -> SemanticEntity | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.M:
            return None
        domain = self.store.domain_of(uid)
        if domain is None or (domains is not None and domain not in domains):
            return None
        element = self.store.get_element(domain, uid)
        return element if isinstance(element, SemanticEntity) else None

    def find_symbols(
        self,
        properties: dict[str, object],
        domains: tuple[Domain, ...] | None = None,
    ) -> tuple[SemanticEntity, ...]:
        selected = set(domains or tuple(Domain))
        out: list[SemanticEntity] = []
        for domain in selected:
            for element in self.store.elements(domain):
                if not isinstance(element, SemanticEntity):
                    continue
                if all(
                    name in element.properties and element.properties[name].value == value
                    for name, value in properties.items()
                ):
                    out.append(element)
        return tuple(sorted(out, key=lambda e: e.uid))

    def get_list(self, uid: str, domains: tuple[Domain, ...] | None = None) -> Group | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.K:
            return None
        domain = self.store.domain_of(uid)
        if domain is None or (domains is not None and domain not in domains):
            return None
        element = self.store.get_element(domain, uid)
        return element if isinstance(element, Group) else None

    def find_lists(self, member: Ref, domains: tuple[Domain, ...] | None = None) -> tuple[Group, ...]:
        selected = set(domains or tuple(Domain))
        return tuple(
            sorted(
                (g for g in self.store.groups_containing(member.uid) if self.store.domain_of(g.uid) in selected),
                key=lambda g: g.uid,
            )
        )

    def get_template(self, uid: str, domains: tuple[Domain, ...] | None = None) -> Template | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.T:
            return None
        domain = self.store.domain_of(uid)
        if domain is None or (domains is not None and domain not in domains):
            return None
        return self.store.get_template(uid)

    def get_hypernode(self, uid: str, domains: tuple[Domain, ...] | None = None) -> Hypernode | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.N:
            return None
        domain = self.store.domain_of(uid)
        if domain is None or (domains is not None and domain not in domains):
            return None
        return self.store.get_hypernode(uid)

    def find_hypernodes(
        self,
        operand: Ref,
        domains: tuple[Domain, ...] | None = None,
    ) -> tuple[Hypernode, ...]:
        selected = set(domains or tuple(Domain))
        out: dict[str, Hypernode] = {}
        if operand.kind is RefKind.T:
            for domain in selected:
                for element in self.store.elements(domain):
                    if isinstance(element, Hypernode) and element.template.uid == operand.uid:
                        out[element.uid] = element
        else:
            for node in self.store.hypernodes_for_actant(operand.uid):
                if self.store.domain_of(node.uid) in selected:
                    out[node.uid] = node
        return tuple(out[uid] for uid in sorted(out))

    def find_roles(
        self,
        role: ActantRole,
        value: Ref,
        domains: tuple[Domain, ...] | None = None,
    ) -> tuple[Hypernode, ...]:
        selected = set(domains or tuple(Domain))
        out = []
        for node in self.store.hypernodes_for_actant(value.uid):
            if self.store.domain_of(node.uid) not in selected:
                continue
            if node.actants.get(role) == value:
                out.append(node)
        return tuple(sorted(out, key=lambda n: n.uid))

    def get_link(self, uid: str) -> Link | None:
        if not self.store.has_uid(uid) or self.store.kind_of(uid) is not RefKind.L:
            return None
        return self.store.get_link(uid)

    def find_links(self, element: Ref) -> tuple[Link, ...]:
        by_uid = {link.uid: link for link in (*self.store.outgoing_links(element.uid), *self.store.incoming_links(element.uid))}
        return tuple(by_uid[uid] for uid in sorted(by_uid))

    # ----- canonical reads -----
    def ref(self, uid: str) -> Ref:
        return Ref(uid, self.store.kind_of(uid))


class AHCoreTransaction:
    def __init__(self, parent_core: AHCore) -> None:
        self.parent_core = parent_core
        self._tx = AHTransaction(parent_core.store)
        self.core = AHCore(self._tx.store, parent_core.uid)

    def __enter__(self) -> AHCore:
        return self.core

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self._tx.commit()
        return False
