from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

from ah.core import AHCore
from ah.model import ActantRole, Domain, Property, Ref, RefKind, Template

from .errors import CorpusError


_ROLE_ALIASES = {
    "AUXILIARY": "AUXILLIARY",
    "HOW TO": "HOW-TO",
    "HOWTO": "HOW-TO",
}

_SECTION_DOMAIN = {
    "symbols": None,
    "common": Domain.C,
    "private": Domain.P,
    "history": Domain.H,
}


def parse_actant_role(raw: str) -> ActantRole:
    key = " ".join(str(raw).strip().replace("_", "-").split()).upper()
    key = _ROLE_ALIASES.get(key, key)
    try:
        return ActantRole(key)
    except ValueError as exc:
        raise CorpusError(f"Unknown actant role: {raw}") from exc


def parse_domain(raw: str | None, default: Domain = Domain.C) -> Domain:
    if raw is None or not str(raw).strip():
        return default
    try:
        return Domain(str(raw).strip().upper())
    except ValueError as exc:
        raise CorpusError(f"Unknown domain: {raw}") from exc


def parse_section_domain(section: str) -> Domain | None:
    key = section.strip().casefold()
    if key not in _SECTION_DOMAIN:
        raise CorpusError(
            f"Unknown project section {section!r}; use symbols, common, private, or history"
        )
    return _SECTION_DOMAIN[key]


@dataclass
class CorpusImportResult:
    symbols_created: int = 0
    symbols_reused: int = 0
    entities_created: int = 0
    entities_reused: int = 0
    templates_created: int = 0
    templates_reused: int = 0
    facts_created: int = 0
    facts_reused: int = 0
    links_created: int = 0
    links_reused: int = 0
    aliases: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbols_created": self.symbols_created,
            "symbols_reused": self.symbols_reused,
            "entities_created": self.entities_created,
            "entities_reused": self.entities_reused,
            "templates_created": self.templates_created,
            "templates_reused": self.templates_reused,
            "facts_created": self.facts_created,
            "facts_reused": self.facts_reused,
            "links_created": self.links_created,
            "links_reused": self.links_reused,
            "aliases": dict(self.aliases),
        }


class ColdCorpusWriter:
    """Write canonical AH structures without Ignition seeds or ticks.

    New nodes start at x=0, so they stay out of Workspace until a later user
    mention or query actually recalls them.
    """

    def __init__(
        self,
        core: AHCore,
        *,
        domain: Domain = Domain.C,
        fact_weight: float = 0.4,
        link_weight: float = 0.2,
    ) -> None:
        self.core = core
        self.domain = domain
        self.fact_weight = float(fact_weight)
        self.link_weight = float(link_weight)
        self.aliases: dict[str, Ref] = {}
        self.image_data: dict[str, str] = {}
        self.result = CorpusImportResult()

    def bind(self, name: str, ref: Ref) -> None:
        label = name.strip()
        if not label:
            raise CorpusError("Alias name must be non-empty")
        self.aliases[label] = ref
        self.aliases[label.casefold()] = ref
        self.result.aliases[label] = ref.uid

    def resolve(self, raw: str) -> Ref:
        label = raw.strip()
        if not label:
            raise CorpusError("Empty reference")
        if label.startswith("@"):
            uid = label[1:]
            if not self.core.store.has_uid(uid):
                raise CorpusError(f"Unknown UID: {uid}")
            return self.core.ref(uid)
        if label in self.aliases:
            return self.aliases[label]
        folded = label.casefold()
        if folded in self.aliases:
            return self.aliases[folded]
        matches = self.core.store.find_entities_by_name(label, self.domain)
        if len(matches) == 1:
            ref = self.core.ref(matches[0].uid)
            self.bind(label, ref)
            return ref
        if len(matches) > 1:
            uids = ", ".join(item.uid for item in matches)
            raise CorpusError(f"Ambiguous entity name {label!r}: {uids}")
        symbols = self.core.store.find_symbols_by_form(label)
        if len(symbols) == 1:
            ref = Ref(symbols[0].uid, RefKind.S)
            self.bind(label, ref)
            return ref
        if len(symbols) > 1:
            uids = ", ".join(item.uid for item in symbols)
            raise CorpusError(f"Ambiguous symbol form {label!r}: {uids}")
        raise CorpusError(f"Unknown name {label!r}; declare it as an entity, symbol, or alias first")

    def record_image(self, name: str, data: str) -> None:
        text = data.strip()
        if not text:
            raise CorpusError(f"image {name!r} has empty data")
        self.image_data[name.strip()] = text

    def ensure_symbol(self, forms: set[str] | frozenset[str], *, alias: str | None = None):
        cleaned = {form.strip() for form in forms if str(form).strip()}
        if not cleaned:
            raise CorpusError("Symbol needs at least one word form")
        existing = None
        for form in sorted(cleaned):
            matches = self.core.store.find_symbols_by_form(form)
            if len(matches) > 1:
                raise CorpusError(f"Ambiguous symbol form {form!r}")
            if matches:
                if existing is not None and existing.uid != matches[0].uid:
                    raise CorpusError(
                        f"Forms {sorted(cleaned)} map to more than one existing symbol"
                    )
                existing = matches[0]
        if existing is None:
            symbol = self.core.add_abstract_symbol(cleaned)
            self.result.symbols_created += 1
        else:
            symbol = existing
            self.result.symbols_reused += 1
            for form in cleaned:
                symbol = self.core.add_symbol_form(symbol.uid, form)
        ref = Ref(symbol.uid, RefKind.S)
        for form in cleaned:
            self.bind(form, ref)
        if alias:
            self.bind(alias, ref)
        return symbol

    def ensure_entity(self, name: str, *, alias: str | None = None, domain: Domain | None = None):
        label = name.strip()
        if not label:
            raise CorpusError("Entity name must be non-empty")
        target_domain = domain or self.domain
        lookup_keys = [key for key in (alias, label) if key]
        for key in lookup_keys:
            if key in self.aliases:
                ref = self.aliases[key]
                if ref.kind is not RefKind.M:
                    raise CorpusError(f"Alias {key!r} is not an entity")
                self.result.entities_reused += 1
                return self.core.store.get_element_any_domain(ref.uid)
        matches = self.core.store.find_entities_by_name(label, target_domain)
        if len(matches) > 1:
            uids = ", ".join(item.uid for item in matches)
            raise CorpusError(f"Ambiguous entity name {label!r}: {uids}")
        if matches:
            entity = matches[0]
            self.result.entities_reused += 1
        else:
            entity = self.core.add_entity(
                target_domain,
                {"name": Property("name", label, "str")},
            )
            self.result.entities_created += 1
        ref = self.core.ref(entity.uid)
        self.bind(label, ref)
        if alias:
            self.bind(alias, ref)
        return entity

    def ensure_template(self, predicate: str, roles: tuple[ActantRole, ...], *, alias: str | None = None):
        if not roles:
            raise CorpusError("Template needs at least one actant role")
        pred_ref = self._predicate_ref(predicate)
        for template in self.core.store.find_templates_by_predicate(pred_ref.uid):
            if template.roles == roles:
                self.result.templates_reused += 1
                ref = self.core.ref(template.uid)
                if alias:
                    self.bind(alias, ref)
                self.bind(predicate, pred_ref)
                return template
        template = self.core.add_template(self.domain, pred_ref, roles)
        self.result.templates_created += 1
        ref = self.core.ref(template.uid)
        if alias:
            self.bind(alias, ref)
        return template

    def add_fact(
        self,
        actants: dict[ActantRole, str],
        *,
        predicate: str | None = None,
        template: str | None = None,
        weight: float | None = None,
        alias: str | None = None,
    ):
        template_obj = self._resolve_template(predicate=predicate, template=template, actants=actants)
        filled: dict[ActantRole, Ref] = {}
        for role, raw in actants.items():
            filled[role] = self._actant_ref(raw)
        node, created = self.core.add_hypernode(
            self.domain,
            self.core.ref(template_obj.uid),
            filled,
            float(self.fact_weight if weight is None else weight),
        )
        if created:
            self.result.facts_created += 1
        else:
            self.result.facts_reused += 1
        if alias:
            self.bind(alias, self.core.ref(node.uid))
        return node

    def add_link(
        self,
        relation: str,
        source: str,
        target: str,
        *,
        weight: float | None = None,
        alias: str | None = None,
    ):
        relation_id = relation.strip()
        if not relation_id:
            raise CorpusError("Link needs a relation type")
        canonical = relation_id.replace("-", "_")
        if canonical.casefold() == "isa":
            relation_id = "IS-A"
        else:
            relation_id = relation_id.upper()
        link, created = self.core.ensure_link(
            relation_id,
            self.resolve(source),
            self.resolve(target),
            float(self.link_weight if weight is None else weight),
        )
        if created:
            self.result.links_created += 1
        else:
            self.result.links_reused += 1
        if alias:
            self.bind(alias, Ref(link.uid, RefKind.L))
        return link

    def _predicate_ref(self, predicate: str) -> Ref:
        label = predicate.strip()
        if label in self.aliases or label.casefold() in self.aliases:
            ref = self.aliases.get(label) or self.aliases[label.casefold()]
            if ref.kind is RefKind.S:
                return ref
            raise CorpusError(f"Predicate {predicate!r} must refer to a symbol")
        symbol = self.ensure_symbol({label}, alias=label)
        return Ref(symbol.uid, RefKind.S)

    def _resolve_template(
        self,
        *,
        predicate: str | None,
        template: str | None,
        actants: dict[ActantRole, str],
    ) -> Template:
        if template:
            ref = self.resolve(template)
            if ref.kind is not RefKind.T:
                raise CorpusError(f"{template!r} is not a template")
            obj = self.core.store.get_element_any_domain(ref.uid)
            if not isinstance(obj, Template):
                raise CorpusError(f"{template!r} is not a template")
            return obj
        if not predicate:
            raise CorpusError("Fact needs predicate= or template=")
        pred_ref = self._predicate_ref(predicate)
        filled_roles = set(actants)
        matches = [
            item
            for item in self.core.store.find_templates_by_predicate(pred_ref.uid)
            if filled_roles <= set(item.roles)
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise CorpusError(
                f"Predicate {predicate!r} has several templates that fit this fact; "
                "pass template= explicitly"
            )
        return self.ensure_template(predicate, tuple(actants.keys()))

    def _actant_ref(self, raw: str) -> Ref:
        label = raw.strip()
        try:
            return self.resolve(label)
        except CorpusError:
            entity = self.ensure_entity(label)
            return self.core.ref(entity.uid)


def import_json_payload(
    core: AHCore,
    payload: dict[str, Any],
    *,
    default_domain: Domain = Domain.C,
) -> CorpusImportResult:
    if not isinstance(payload, dict):
        raise CorpusError("JSON corpus must be an object")
    domain = parse_domain(payload.get("domain"), default_domain)
    writer = ColdCorpusWriter(
        core,
        domain=domain,
        fact_weight=float(payload.get("weight", 0.4)),
        link_weight=float(payload.get("link_weight", 0.2)),
    )
    for item in payload.get("symbols") or ():
        if isinstance(item, str):
            writer.ensure_symbol({item}, alias=item)
            continue
        if not isinstance(item, dict):
            raise CorpusError("symbols entries must be strings or objects")
        forms = item.get("forms") or item.get("form")
        if isinstance(forms, str):
            form_set = {part.strip() for part in forms.split(",") if part.strip()}
        elif isinstance(forms, (list, tuple)):
            form_set = {str(part).strip() for part in forms if str(part).strip()}
        else:
            raise CorpusError("symbol.forms must be a string or list")
        writer.ensure_symbol(form_set, alias=item.get("id") or item.get("name"))
    for item in payload.get("entities") or ():
        if isinstance(item, str):
            writer.ensure_entity(item)
            continue
        if not isinstance(item, dict) or "name" not in item:
            raise CorpusError("entities entries need name")
        writer.ensure_entity(
            str(item["name"]),
            alias=item.get("id"),
            domain=parse_domain(item.get("domain"), domain),
        )
    for item in payload.get("templates") or ():
        if not isinstance(item, dict):
            raise CorpusError("templates entries must be objects")
        predicate = item.get("predicate") or item.get("symbol")
        if not predicate:
            raise CorpusError("template needs predicate")
        raw_roles = item.get("roles") or item.get("actants") or ()
        if isinstance(raw_roles, str):
            roles = tuple(parse_actant_role(part) for part in raw_roles.replace(",", " ").split() if part)
        else:
            roles = tuple(parse_actant_role(part) for part in raw_roles)
        writer.ensure_template(str(predicate), roles, alias=item.get("id") or item.get("name"))
    for item in payload.get("facts") or ():
        if not isinstance(item, dict):
            raise CorpusError("facts entries must be objects")
        actants: dict[ActantRole, str] = {}
        reserved = {
            "predicate", "template", "weight", "id", "name", "domain",
            "roles", "actants", "symbol",
        }
        raw_actants = item.get("actants")
        if isinstance(raw_actants, dict):
            for key, value in raw_actants.items():
                actants[parse_actant_role(str(key))] = str(value)
        for key, value in item.items():
            if key in reserved:
                continue
            actants[parse_actant_role(str(key))] = str(value)
        writer.add_fact(
            actants,
            predicate=None if item.get("template") else item.get("predicate"),
            template=item.get("template"),
            weight=item.get("weight"),
            alias=item.get("id") or item.get("name"),
        )
    for item in payload.get("links") or ():
        if not isinstance(item, dict):
            raise CorpusError("links entries must be objects")
        relation = item.get("relation") or item.get("type") or item.get("id")
        source = item.get("from") or item.get("source")
        target = item.get("to") or item.get("target")
        if not relation or not source or not target:
            raise CorpusError("link needs relation, from, and to")
        writer.add_link(
            str(relation),
            str(source),
            str(target),
            weight=item.get("weight"),
            alias=item.get("name"),
        )
    return writer.result


def import_json_file(
    core: AHCore,
    path: Path,
    *,
    default_domain: Domain = Domain.C,
) -> CorpusImportResult:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorpusError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CorpusError(f"{path} must contain a JSON object")
    return import_json_payload(core, payload, default_domain=default_domain)


def max_excitation(core: AHCore) -> float:
    return max((state.excitation for _, state in core.store.runtime_items()), default=0.0)
