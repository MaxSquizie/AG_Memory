from __future__ import annotations

from dataclasses import dataclass

from ah.bootstrap import RuntimeServices
from ah.model import Domain, Property, Ref, SemanticEntity


@dataclass(frozen=True, slots=True)
class ManualNodeRequest:
    kind: str
    text: str
    domain: Domain | None = None
    aliases: tuple[str, ...] = ()
    duplicate_policy: str = "reuse_same_domain"
    selected_uid: str | None = None
    link_relation_id: str | None = None
    link_direction: str = "selected_to_new"
    link_weight: float = 0.25
    seed_amount: float | None = None


@dataclass(frozen=True, slots=True)
class ManualNodeResult:
    ref: Ref
    created: bool
    link_uid: str | None = None
    link_created: bool = False
    other_domain_matches: tuple[str, ...] = ()


class ManualNodeManager:
    """Operator-facing composition of canonical AH operations.

    Duplicate policy follows the architecture rather than treating display names as
    primary keys:
      * S is global/non-domain and a wordform can belong to only one S. Existing S is
        reused and missing forms are merged into it.
      * m names are only resolution cues. Default GUI behavior reuses one exact
        same-domain candidate to prevent accidental duplicates, but an operator can
        explicitly request a new UID. Equal names in other C/P/H domains never block
        creation in the selected domain.

    The whole canonical mutation (node/form update + optional L) is copy-on-write
    transactional. A validation/link error cannot leave a half-created node behind.
    """

    SUPPORTED_KINDS = {"S", "M"}
    DUPLICATE_POLICIES = {"reuse_same_domain", "reuse_any_domain", "create_new"}

    def __init__(self, services: RuntimeServices) -> None:
        self.services = services

    def create(self, request: ManualNodeRequest) -> ManualNodeResult:
        kind = request.kind.strip().upper()
        if kind not in self.SUPPORTED_KINDS:
            raise ValueError("Manual GUI manager currently supports only S and m")
        text = request.text.strip()
        if not text:
            raise ValueError("Node text/name must be non-empty")
        if request.duplicate_policy not in self.DUPLICATE_POLICIES:
            raise ValueError(f"Unknown duplicate policy: {request.duplicate_policy}")
        if not 0.0 <= request.link_weight <= 1.0:
            raise ValueError("Link weight must be in [0, 1]")
        if request.seed_amount is not None and request.seed_amount < 0:
            raise ValueError("Seed amount must be >= 0")
        if request.link_direction not in {"selected_to_new", "new_to_selected"}:
            raise ValueError("Unknown link direction")

        relation = (request.link_relation_id or "").strip()
        aliases = tuple(dict.fromkeys(a.strip() for a in request.aliases if a.strip()))
        other_domain_matches: tuple[str, ...] = ()

        with self.services.operation_lock:
            # Validate selected endpoint against the parent snapshot before opening the
            # COW transaction so error messages are immediate and no UID is consumed.
            if relation:
                if not request.selected_uid:
                    raise ValueError("Choose a node on canvas before creating a relation")
                if not self.services.core.store.has_uid(request.selected_uid):
                    raise KeyError(request.selected_uid)

            with self.services.core.transaction() as core:
                selected_ref = core.ref(request.selected_uid) if relation else None

                if kind == "S":
                    created_obj, created = self._resolve_or_create_symbol(core, text)
                else:
                    if request.domain is None:
                        raise ValueError("m requires C/P/H domain")
                    all_matches = core.store.find_entities_by_name(text)
                    same_domain = tuple(
                        entity
                        for entity in all_matches
                        if core.store.domain_of(entity.uid) is request.domain
                    )
                    other_domain_matches = tuple(
                        entity.uid
                        for entity in all_matches
                        if core.store.domain_of(entity.uid) is not request.domain
                    )
                    created_obj, created = self._resolve_or_create_entity(
                        core,
                        request.domain,
                        text,
                        aliases,
                        same_domain,
                        all_matches,
                        request.duplicate_policy,
                    )

                created_ref = core.ref(created_obj.uid)
                link_uid = None
                link_created = False
                if relation:
                    assert selected_ref is not None
                    if request.link_direction == "selected_to_new":
                        source, target = selected_ref, created_ref
                    else:
                        source, target = created_ref, selected_ref
                    link, link_created = core.ensure_link(
                        relation, source, target, request.link_weight
                    )
                    link_uid = link.uid

            # Runtime seed is intentionally outside the canonical COW transaction. It
            # is applied only after a successful commit and therefore can never point
            # at a rolled-back UID.
            if request.seed_amount is not None and request.seed_amount > 0:
                self.services.ignition.seed(created_ref, request.seed_amount)

        return ManualNodeResult(
            created_ref,
            created,
            link_uid,
            link_created,
            other_domain_matches,
        )

    @staticmethod
    def _resolve_or_create_symbol(core, text: str):
        forms = tuple(
            dict.fromkeys(
                value.strip()
                for value in text.replace(";", ",").split(",")
                if value.strip()
            )
        )
        if not forms:
            raise ValueError("S requires at least one wordform")

        candidate_sets = [
            {symbol.uid for symbol in core.store.find_symbols_by_form(form)}
            for form in forms
        ]
        known_sets = [uids for uids in candidate_sets if uids]
        if not known_sets:
            return core.add_abstract_symbol(set(forms)), True

        common = set.intersection(*known_sets)
        if len(common) > 1:
            raise ValueError(
                "Requested wordforms are homographic across multiple existing S nodes "
                f"({', '.join(sorted(common))}); add a distinguishing paradigm form."
            )
        if len(common) == 1:
            symbol = core.store.get_symbol(next(iter(common)))
            for form in forms:
                if form not in symbol.forms:
                    symbol = core.add_symbol_form(symbol.uid, form)
            return symbol, False

        # At least two supplied forms point only to disjoint existing paradigms.
        # Do not infer that those S nodes should be merged merely because the GUI
        # request listed them together.
        owners = sorted(set().union(*known_sets))
        raise ValueError(
            "Requested wordforms do not identify one existing S node "
            f"({', '.join(owners)}); resolve the lexical identity explicitly."
        )

    @staticmethod
    def _resolve_or_create_entity(
        core,
        domain: Domain,
        text: str,
        aliases: tuple[str, ...],
        same_domain: tuple[SemanticEntity, ...],
        all_matches: tuple[SemanticEntity, ...],
        duplicate_policy: str,
    ):
        if duplicate_policy == "reuse_any_domain" and all_matches:
            if len(all_matches) > 1:
                details = ", ".join(
                    f"{entity.uid}@{core.store.domain_of(entity.uid).value}"
                    for entity in all_matches
                )
                raise ValueError(
                    f"Name {text!r} resolves to {len(all_matches)} m nodes across C/P/H: "
                    f"{details}. Name is not an identity key; choose a specific identity "
                    "or create a new UID explicitly."
                )
            entity = all_matches[0]
            return ManualNodeManager._merge_aliases(core, entity, aliases), False

        if duplicate_policy == "reuse_same_domain" and same_domain:
            if len(same_domain) > 1:
                uids = ", ".join(entity.uid for entity in same_domain)
                raise ValueError(
                    f"Name {text!r} resolves to {len(same_domain)} m nodes in domain "
                    f"{domain.value}: {uids}. Name is not an identity key; choose "
                    "'create new UID' for an intentional namesake or resolve the "
                    "existing identity explicitly."
                )
            entity = same_domain[0]
            return ManualNodeManager._merge_aliases(core, entity, aliases), False

        props = {"name": Property("name", text, "str")}
        if aliases:
            props["aliases"] = Property("aliases", aliases, "list[str]")
        return core.add_entity(domain, props), True

    @staticmethod
    def _merge_aliases(core, entity: SemanticEntity, aliases: tuple[str, ...]) -> SemanticEntity:
        if not aliases:
            return entity
        current_prop = entity.properties.get("aliases")
        current: tuple[str, ...] = ()
        if current_prop is not None:
            raw = current_prop.value
            if isinstance(raw, str):
                current = (raw,)
            elif isinstance(raw, (list, tuple, set, frozenset)):
                current = tuple(str(v) for v in raw)
        merged = tuple(dict.fromkeys((*current, *aliases)))
        if merged == current:
            return entity
        prop = Property("aliases", merged, "list[str]")
        if current_prop is None:
            return core.add_property(entity.uid, prop)
        return core.edit_property(entity.uid, prop)
